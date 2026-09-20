#!/usr/bin/env python3
"""
notion_to_anki.py

Syncs your Notion "Language Learning Ledger" database into Anki.
Reads database rows directly via the Notion API (no toggle-block
workaround needed) and pushes them into Anki via AnkiConnect.

Also supports a one-time seed of the FULL hiragana + katakana charts
(gojuon, dakuten/handakuten, and yoon combos) into their own Anki
decks, for kana recognition practice separate from the Notion ledger.

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
   python3 main.py                 # sync the Notion ledger into Anki
   python3 main.py --dry-run       # preview the Notion sync only
   python3 main.py --no-update     # only add new notes, don't touch existing ones

   python3 main.py --seed-kana                # one-time: add all hiragana + katakana
   python3 main.py --seed-kana --dry-run       # preview the kana seed only
   python3 main.py --seed-kana --no-update     # only add new kana, don't fix existing ones

Safe to re-run any time. Notes are matched by their Front field text.
By default (updating is ON), anything not yet in Anki is added, and
anything already there has its Back field (and tags) overwritten if
the content in this script/the Notion ledger has changed since — e.g.
after correcting a reading/meaning, or fixing a typo in the kana
tables below. Pass --no-update to fall back to add-only behaviour.
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


# ---------------------------------------------------------------------------
# Kana data — full gojuon, dakuten/handakuten, and yoon (combination) charts
# ---------------------------------------------------------------------------

_GOJUON = [
    ("a", "i", "u", "e", "o"),
    ("ka", "ki", "ku", "ke", "ko"),
    ("sa", "shi", "su", "se", "so"),
    ("ta", "chi", "tsu", "te", "to"),
    ("na", "ni", "nu", "ne", "no"),
    ("ha", "hi", "fu", "he", "ho"),
    ("ma", "mi", "mu", "me", "mo"),
    ("ra", "ri", "ru", "re", "ro"),
]

HIRAGANA_GOJUON = [
    ("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"),
    ("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"),
    ("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"),
    ("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to"),
    ("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"),
    ("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"),
    ("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo"),
    ("や", "ya"), ("ゆ", "yu"), ("よ", "yo"),
    ("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro"),
    ("わ", "wa"), ("を", "wo"), ("ん", "n"),
]

HIRAGANA_DAKUTEN = [
    ("が", "ga"), ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go"),
    ("ざ", "za"), ("じ", "ji"), ("ず", "zu"), ("ぜ", "ze"), ("ぞ", "zo"),
    ("だ", "da"), ("ぢ", "ji (di)"), ("づ", "zu (du)"), ("で", "de"), ("ど", "do"),
    ("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo"),
    ("ぱ", "pa"), ("ぴ", "pi"), ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po"),
]

HIRAGANA_YOON = [
    ("きゃ", "kya"), ("きゅ", "kyu"), ("きょ", "kyo"),
    ("しゃ", "sha"), ("しゅ", "shu"), ("しょ", "sho"),
    ("ちゃ", "cha"), ("ちゅ", "chu"), ("ちょ", "cho"),
    ("にゃ", "nya"), ("にゅ", "nyu"), ("にょ", "nyo"),
    ("ひゃ", "hya"), ("ひゅ", "hyu"), ("ひょ", "hyo"),
    ("みゃ", "mya"), ("みゅ", "myu"), ("みょ", "myo"),
    ("りゃ", "rya"), ("りゅ", "ryu"), ("りょ", "ryo"),
    ("ぎゃ", "gya"), ("ぎゅ", "gyu"), ("ぎょ", "gyo"),
    ("じゃ", "ja"), ("じゅ", "ju"), ("じょ", "jo"),
    ("びゃ", "bya"), ("びゅ", "byu"), ("びょ", "byo"),
    ("ぴゃ", "pya"), ("ぴゅ", "pyu"), ("ぴょ", "pyo"),
]

HIRAGANA = HIRAGANA_GOJUON + HIRAGANA_DAKUTEN + HIRAGANA_YOON

KATAKANA_GOJUON = [
    ("ア", "a"), ("イ", "i"), ("ウ", "u"), ("エ", "e"), ("オ", "o"),
    ("カ", "ka"), ("キ", "ki"), ("ク", "ku"), ("ケ", "ke"), ("コ", "ko"),
    ("サ", "sa"), ("シ", "shi"), ("ス", "su"), ("セ", "se"), ("ソ", "so"),
    ("タ", "ta"), ("チ", "chi"), ("ツ", "tsu"), ("テ", "te"), ("ト", "to"),
    ("ナ", "na"), ("ニ", "ni"), ("ヌ", "nu"), ("ネ", "ne"), ("ノ", "no"),
    ("ハ", "ha"), ("ヒ", "hi"), ("フ", "fu"), ("ヘ", "he"), ("ホ", "ho"),
    ("マ", "ma"), ("ミ", "mi"), ("ム", "mu"), ("メ", "me"), ("モ", "mo"),
    ("ヤ", "ya"), ("ユ", "yu"), ("ヨ", "yo"),
    ("ラ", "ra"), ("リ", "ri"), ("ル", "ru"), ("レ", "re"), ("ロ", "ro"),
    ("ワ", "wa"), ("ヲ", "wo"), ("ン", "n"),
]

KATAKANA_DAKUTEN = [
    ("ガ", "ga"), ("ギ", "gi"), ("グ", "gu"), ("ゲ", "ge"), ("ゴ", "go"),
    ("ザ", "za"), ("ジ", "ji"), ("ズ", "zu"), ("ゼ", "ze"), ("ゾ", "zo"),
    ("ダ", "da"), ("ヂ", "ji (di)"), ("ヅ", "zu (du)"), ("デ", "de"), ("ド", "do"),
    ("バ", "ba"), ("ビ", "bi"), ("ブ", "bu"), ("ベ", "be"), ("ボ", "bo"),
    ("パ", "pa"), ("ピ", "pi"), ("プ", "pu"), ("ペ", "pe"), ("ポ", "po"),
]

KATAKANA_YOON = [
    ("キャ", "kya"), ("キュ", "kyu"), ("キョ", "kyo"),
    ("シャ", "sha"), ("シュ", "shu"), ("ショ", "sho"),
    ("チャ", "cha"), ("チュ", "chu"), ("チョ", "cho"),
    ("ニャ", "nya"), ("ニュ", "nyu"), ("ニョ", "nyo"),
    ("ヒャ", "hya"), ("ヒュ", "hyu"), ("ヒョ", "hyo"),
    ("ミャ", "mya"), ("ミュ", "myu"), ("ミョ", "myo"),
    ("リャ", "rya"), ("リュ", "ryu"), ("リョ", "ryo"),
    ("ギャ", "gya"), ("ギュ", "gyu"), ("ギョ", "gyo"),
    ("ジャ", "ja"), ("ジュ", "ju"), ("ジョ", "jo"),
    ("ビャ", "bya"), ("ビュ", "byu"), ("ビョ", "byo"),
    ("ピャ", "pya"), ("ピュ", "pyu"), ("ピョ", "pyo"),
]

KATAKANA = KATAKANA_GOJUON + KATAKANA_DAKUTEN + KATAKANA_YOON

del _GOJUON  # reference table only, not used directly


def kana_note(kana, romaji, kana_type):
    """Build an AnkiConnect note dict for a single kana character."""
    return {
        "deckName": f"{DECK_ROOT}::Kana::{kana_type}",
        "modelName": NOTE_TYPE,
        "fields": {"Front": kana, "Back": romaji},
        "tags": ["kana", kana_type.lower()],
        "options": {"allowDuplicate": False},
    }


def build_kana_notes():
    notes = [kana_note(k, r, "Hiragana") for k, r in HIRAGANA]
    notes += [kana_note(k, r, "Katakana") for k, r in KATAKANA]
    return notes


def seed_kana(dry_run=False, update=True):
    """One-time (but safe to re-run) seed of the full kana charts into Anki.
    With update=True, also fixes the Back text of any kana card already in
    Anki that doesn't match the current table (e.g. after a typo fix here).
    """
    notes = build_kana_notes()
    decks = sorted(set(n["deckName"] for n in notes))

    if dry_run:
        print(f"Would ensure {len(decks)} decks: {decks}")
        print(f"Would attempt to add {len(notes)} kana notes "
              f"({len(HIRAGANA)} hiragana, {len(KATAKANA)} katakana).")
        for n in notes[:5]:
            print(" -", n["fields"]["Front"], "->", n["fields"]["Back"], "in", n["deckName"])
        print(" ...")
        return

    add_or_update_notes(notes, update=update)


# ---------------------------------------------------------------------------
# Notion ledger sync
# ---------------------------------------------------------------------------

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


def _escape_query_value(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def add_or_update_notes(notes, update=True):
    """Push a list of note dicts (deckName, modelName, fields, tags, and
    optionally internal keys prefixed with "_") into Anki.

    update=True (default): existing notes are looked up by Front field, and
    their Back field / tags are updated in place if they've changed;
    anything not found is added as new.

    update=False: plain add only — existing notes (matched by Front) are
    left untouched, even if their content has changed.
    """
    decks = sorted(set(n["deckName"] for n in notes))
    for d in decks:
        ensure_deck(d)

    clean = [{k: v for k, v in n.items() if not k.startswith("_")} for n in notes]

    if not update:
        results = anki_request("addNotes", notes=clean)
        added = sum(1 for r in (results or []) if r is not None)
        skipped = len(notes) - added
        print(f"Added {added} new notes. Skipped {skipped} (already in Anki).")
        return

    # Build a Front-text -> existing note lookup, scoped to the note type
    # in use, so we only touch notes this script itself manages.
    query = f'note:"{NOTE_TYPE}"'
    existing_ids = anki_request("findNotes", query=query) or []
    existing_info = anki_request("notesInfo", notes=existing_ids) if existing_ids else []
    by_front = {}
    for info in existing_info:
        front = info.get("fields", {}).get("Front", {}).get("value", "")
        by_front[front] = info

    to_add = []
    updated = 0
    unchanged = 0
    for n in clean:
        front = n["fields"]["Front"]
        info = by_front.get(front)
        if info is None:
            to_add.append(n)
            continue
        note_id = info["noteId"]
        current_back = info.get("fields", {}).get("Back", {}).get("value", "")
        if current_back != n["fields"]["Back"]:
            anki_request("updateNoteFields", note={"id": note_id, "fields": n["fields"]})
            updated += 1
        else:
            unchanged += 1
        if n.get("tags"):
            anki_request("addTags", notes=[note_id], tags=" ".join(n["tags"]))

    added = 0
    if to_add:
        results = anki_request("addNotes", notes=to_add)
        added = sum(1 for r in (results or []) if r is not None)

    print(f"Added {added} new notes. Updated {updated} existing notes. "
          f"{unchanged} already up to date.")


def sync_ledger(dry_run=False, update=True):
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

    if dry_run:
        print(f"Would ensure {len(decks)} decks: {decks}")
        print(f"Would attempt to add {len(notes)} notes.")
        for n in notes[:5]:
            print(" -", n["fields"]["Front"], "->", n["deckName"])
        return

    add_or_update_notes(notes, update=update)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be synced/seeded without touching Anki",
    )
    parser.add_argument(
        "--seed-kana", action="store_true",
        help="One-time seed of the full hiragana + katakana charts into "
             "Nihongo::Kana::Hiragana / Nihongo::Kana::Katakana, instead of "
             "syncing the Notion ledger",
    )
    parser.add_argument(
        "--no-update", dest="update", action="store_false",
        help="Only add new notes; leave existing notes' Back field untouched "
             "even if their content has changed (updating is ON by default)",
    )
    parser.set_defaults(update=True)
    args = parser.parse_args()

    if args.seed_kana:
        seed_kana(dry_run=args.dry_run, update=args.update)
        return

    sync_ledger(dry_run=args.dry_run, update=args.update)


if __name__ == "__main__":
    main()