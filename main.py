#!/usr/bin/env python3
"""
notion_to_anki.py

Syncs your Notion "Language Learning Ledger" database into Anki.
Reads database rows directly via the Notion API (no toggle-block
workaround needed) and pushes them into Anki via AnkiConnect.

SETUP (one-time)
-----------------
1. Create a Notion integration:
   https://www.notion.so/my-integrations -> "New integration"
   Copy the "Internal Integration Secret" -> this is your NOTION_TOKEN.

2. Share your Language Learning Ledger database with that integration:
   Open the database in Notion -> "..." menu -> Connections -> add
   your integration.

3. Get the database ID:
   Open the database as a full page, copy the URL. The ID is the
   32-character string right after your workspace name and before
   the "?v=", e.g.:
   https://notion.so/myworkspace/f6b41903691... -> that's the ID.

4. Install AnkiConnect in Anki:
   Anki -> Tools -> Add-ons -> Get Add-ons -> paste code: 2055492159
   Restart Anki. Keep Anki OPEN whenever you run this script.

5. Install the Python dependencies:
   pip install requests python-dotenv --break-system-packages

6. Create a .env file in the same folder as this script:
   NOTION_TOKEN=your_secret_here
   NOTION_DATABASE_ID=your_database_id_here

USAGE
-----
   python3 main.py

Safe to re-run any time. Only rows not yet in Anki (matched by the
Front field text) get added; existing notes are left alone unless
you pass --update.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

from dotenv import load_dotenv

# Loads variables from a .env file (same folder as this script) into the
# environment. Create a .env file next to this script with:
#
#   NOTION_TOKEN=your_secret_here
#   NOTION_DATABASE_ID=your_database_id_here
#
load_dotenv()

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "PASTE_YOUR_NOTION_TOKEN_HERE")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "PASTE_YOUR_DATABASE_ID_HERE")

NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"
ANKICONNECT_URL = "http://127.0.0.1:8765"

DECK_ROOT = "Nihongo"
NOTE_TYPE = "Basic"


def notion_request(path, method="GET", body=None):
    url = f"{NOTION_API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", NOTION_API_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"Notion API error {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)


def fetch_all_rows():
    rows = []
    body = {"page_size": 100}
    while True:
        result = notion_request(f"/databases/{NOTION_DATABASE_ID}/query", "POST", body)
        rows.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        body["start_cursor"] = result["next_cursor"]
    return rows


def plain_text(rich_text_list):
    return "".join(t.get("plain_text", "") for t in rich_text_list or [])


def get_prop(props, name, kind):
    prop = props.get(name)
    if not prop:
        return ""
    if kind == "title":
        return plain_text(prop.get("title"))
    if kind == "rich_text":
        return plain_text(prop.get("rich_text"))
    if kind == "select":
        sel = prop.get("select")
        return sel.get("name") if sel else ""
    if kind == "number":
        val = prop.get("number")
        return "" if val is None else str(val)
    return ""


def row_to_note(page):
    props = page["properties"]
    item = get_prop(props, "Item", "title")
    meaning = get_prop(props, "Meaning", "rich_text")
    readings = get_prop(props, "Readings", "rich_text")
    item_type = get_prop(props, "Type", "select") or "Vocab"
    lesson = get_prop(props, "Lesson", "number")

    back_parts = []
    if readings:
        back_parts.append(readings)
    if meaning:
        back_parts.append(meaning)
    back = "<br>".join(back_parts)

    deck = f"{DECK_ROOT}::{item_type}"
    tags = [f"lesson{lesson}"] if lesson else []
    tags.append(item_type.lower())

    return {
        "deckName": deck,
        "modelName": NOTE_TYPE,
        "fields": {"Front": item, "Back": back},
        "tags": tags,
        "options": {"allowDuplicate": False},
        "_notion_page_id": page["id"],
    }


def anki_request(action, **params):
    body = {"action": action, "version": 6, "params": params}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(ANKICONNECT_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        print(
            "Could not reach AnkiConnect at http://127.0.0.1:8765 -- "
            "is Anki open with the AnkiConnect add-on installed?",
            file=sys.stderr,
        )
        sys.exit(1)
    if result.get("error"):
        print(f"AnkiConnect error on {action}: {result['error']}", file=sys.stderr)
    return result.get("result")


def ensure_deck(deck_name):
    anki_request("createDeck", deck=deck_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be synced without touching Anki",
    )
    args = parser.parse_args()

    if "PASTE_YOUR" in NOTION_TOKEN or "PASTE_YOUR" in NOTION_DATABASE_ID:
        print(
            "Set NOTION_TOKEN and NOTION_DATABASE_ID (env vars, or edit "
            "the top of this script) before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Fetching rows from Notion...")
    pages = fetch_all_rows()
    print(f"Found {len(pages)} rows in the ledger.")

    notes = [row_to_note(p) for p in pages]
    decks = sorted(set(n["deckName"] for n in notes))

    if args.dry_run:
        print(f"Would ensure {len(decks)} decks: {decks}")
        print(f"Would attempt to add {len(notes)} notes.")
        for n in notes[:5]:
            print(" -", n["fields"]["Front"], "->", n["deckName"])
        return

    for d in decks:
        ensure_deck(d)

    to_add = [{k: v for k, v in n.items() if not k.startswith("_")} for n in notes]
    results = anki_request("addNotes", notes=to_add)

    added = sum(1 for r in (results or []) if r is not None)
    skipped = len(notes) - added
    print(f"Done. Added {added} new notes. Skipped {skipped} (already in Anki).")


if __name__ == "__main__":
    main()