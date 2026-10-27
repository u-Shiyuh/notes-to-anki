#!/usr/bin/env python3
"""
main.py

Syncs your Notion "Language Learning Ledger" database into Anki.
Reads database rows directly via the Notion API (no toggle-block
workaround needed) and pushes them into Anki via AnkiConnect.

Also supports a one-time seed of the FULL hiragana + katakana charts
(gojuon, dakuten/handakuten, and yoon combos) into their own Anki
decks, for kana recognition practice separate from the Notion ledger,
and a seed of the 1000 most frequent kanji (kanji_top1000.tsv).

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

5. Install the Python dependency:
   pip install python-dotenv

6. Create a .env file in the same folder as this script:
   NOTION_TOKEN=your_secret_here
   NOTION_DATABASE_ID=your_database_id_here

USAGE
-----
   python3 main.py                 # sync the Notion ledger into Anki
   python3 main.py --dry-run       # preview the Notion sync only
   python3 main.py --no-update     # only add new notes, don't touch existing ones
   python3 main.py --prune         # also delete cards whose Notion row is gone

   python3 main.py --seed-kana                # one-time: add all hiragana + katakana
   python3 main.py --seed-kana --dry-run       # preview the kana seed only
   python3 main.py --seed-kana --no-update     # only add new kana, don't fix existing ones

   python3 main.py --seed-kanji               # add the 1000 most frequent kanji
   python3 main.py --seed-kanji --dry-run     # preview the kanji seed only

Safe to re-run any time. Each mode only looks at its own decks: the kana
seed at Nihongo::Kana::*, the kanji seed at Nihongo::Core Kanji, the
ledger sync at the other Nihongo decks. The kanji seed skips kanji that
already have a card in Nihongo::Kanji, and when a ledger Kanji row is
added for a seeded kanji, the sync moves that card into Nihongo::Kanji
(keeping its review history) rather than creating a second one.
Ledger notes carry a notion_<page id> tag linking them to their row, so
renaming an Item updates its card instead of creating a new one (older
untagged notes are matched by Front text once, then tagged).

By default (updating is ON), anything not yet in Anki is added, and
anything already there has its fields, deck and tags brought in line
with the Notion ledger / the kana tables below. Tags you add yourself
are left alone. Pass --no-update to fall back to add-only behaviour.
With Anki open, --dry-run also lists exactly what would change.
"""

import os
import re
import sys
import html
import json
import time
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

NOTION_API_VERSION = "2025-09-03"
NOTION_API_BASE = "https://api.notion.com/v1"
# Rate limits (429) and server errors are retried with backoff.
NOTION_RETRY_STATUS = {429, 500, 502, 503, 504}
NOTION_MAX_ATTEMPTS = 5
ANKICONNECT_URL = "http://127.0.0.1:8765"

DECK_ROOT = "Nihongo"
NOTE_TYPE = "Basic"

# Each mode only matches (and may only change) notes inside its own decks,
# so a ledger card "は" and the hiragana card "は" never overwrite each other.
KANJI_DECK = f"{DECK_ROOT}::Core Kanji"
KANA_SCOPE = f'"deck:{DECK_ROOT}::Kana"'
KANJI_SCOPE = f'"deck:{KANJI_DECK}"'
LEDGER_SCOPE = f'"deck:{DECK_ROOT}" -"deck:{DECK_ROOT}::Kana" -"deck:{KANJI_DECK}"'

# The ledger's Kanji deck. The kanji seed skips kanji that already have a
# card here, and a ledger Kanji row takes over (adopts) the Core Kanji card
# for the same kanji instead of duplicating it.
LEDGER_KANJI_DECK = f"{DECK_ROOT}::Kanji"
LEDGER_KANJI_SCOPE = f'"deck:{LEDGER_KANJI_DECK}"'

# The 1000 most frequent kanji, generated from KANJIDIC2 (see its header).
KANJI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "kanji_top1000.tsv")

# Ledger notes are tagged notion_<page id without dashes>. That tag, not
# the Front text, is what links a card to its Notion row.
LINK_TAG_PREFIX = "notion_"

# Tags the script owns. On update, a note's tags matching these (or any tag
# the current batch produces) are removed when no longer wanted; every
# other tag on the note is the user's and is left alone.
TYPE_TAGS = {"kanji", "vocab", "grammar", "grammar_drill"}
_LESSON_TAG = re.compile(r"lesson\d+(\.\d+)?", re.IGNORECASE)

# How many AnkiConnect actions to send per "multi" request.
ANKI_MULTI_CHUNK = 200

# Only ledger rows in this language are synced (rows with no Language set
# are kept). Rows whose Item starts with SKIP_PREFIX are never synced.
LANGUAGE = "Japanese"
SKIP_PREFIX = "IGNORE"

# In the ledger, " — " separates the core reading/meaning from side notes,
# e.g. "き(く) kun / ぶん on — 新聞(しんぶん) is N5 vocab".
NOTE_SEP = " — "


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

# Anki's duplicate check is per deck, not per collection: otherwise the
# ledger card "は" and the hiragana card "は" couldn't both exist.
NOTE_OPTIONS = {"allowDuplicate": False, "duplicateScope": "deck"}


def kana_note(kana, romaji, kana_type):
    """Build an AnkiConnect note dict for a single kana character."""
    return {
        "deckName": f"{DECK_ROOT}::Kana::{kana_type}",
        "modelName": NOTE_TYPE,
        "fields": {"Front": kana, "Back": romaji},
        "tags": ["kana", kana_type.lower()],
        "options": NOTE_OPTIONS,
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
        preview_changes(notes, KANA_SCOPE, update=update)
        return

    add_or_update_notes(notes, KANA_SCOPE, update=update)


# ---------------------------------------------------------------------------
# Core kanji seed — the 1000 most frequent kanji, from kanji_top1000.tsv
# ---------------------------------------------------------------------------

def load_kanji():
    """Rows of KANJI_FILE as dicts, in frequency order."""
    rows = []
    try:
        with open(KANJI_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                rank, kanji, strokes, jlpt, meanings, on, kun = \
                    line.rstrip("\n").split("\t")
                rows.append({"rank": rank, "kanji": kanji, "strokes": strokes,
                             "jlpt": jlpt, "meanings": meanings.split("; "),
                             "on": on, "kun": kun})
    except OSError as e:
        print(f"Could not read the kanji list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


def kanji_readings(label, readings):
    """One "On:"/"Kun:" line. The most common reading (marked * in
    KANJI_FILE, always first, or the only one) is bold; the rest are faded."""
    esc = html.escape
    items = readings.split("、")
    line = f"{label}: "
    if items[0].startswith("*") or len(items) == 1:
        line += f"<b>{esc(items.pop(0).lstrip('*'))}</b>"
        if items:
            line += f'<span style="opacity:0.65">、{esc("、".join(items))}</span>'
    else:
        line += esc("、".join(items))
    return _LINE.format(line)


def kanji_note(row):
    """Build an AnkiConnect note dict for one Core Kanji row."""
    esc = html.escape
    parts = [_HEADLINE.format(esc(", ".join(row["meanings"])))]
    if row["on"]:
        parts.append(kanji_readings("On", row["on"]))
    if row["kun"]:
        parts.append(kanji_readings("Kun", row["kun"]))
    facts = [f"{row['strokes']} stroke" + ("" if row["strokes"] == "1" else "s")]
    if row["jlpt"]:
        facts.append(f"JLPT N{row['jlpt']}")
    facts.append(f"#{row['rank']} by frequency")
    parts.append(_NOTE.format(esc(" · ".join(facts))))

    tags = ["kanji", "core_kanji"]
    if row["jlpt"]:
        tags.append(f"jlpt_n{row['jlpt']}")
    return {
        "deckName": KANJI_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": row["kanji"], "Back": "".join(parts)},
        "tags": tags,
        "options": NOTE_OPTIONS,
    }


def without_ledger_kanji(notes):
    """Drop kanji that already have a card in the ledger's Kanji deck."""
    have = {_field(info, "Front").strip() for info in find_notes(LEDGER_KANJI_SCOPE)}
    kept = [n for n in notes if n["fields"]["Front"] not in have]
    skipped = [n["fields"]["Front"] for n in notes if n["fields"]["Front"] in have]
    if skipped:
        print(f"Skipping {len(skipped)} kanji already in {LEDGER_KANJI_DECK}: "
              + " ".join(skipped))
    return kept


def seed_kanji(dry_run=False, update=True):
    """Seed the Core Kanji deck (safe to re-run). Notes are added in
    frequency order, so Anki introduces the most common kanji first."""
    notes = [kanji_note(row) for row in load_kanji()]

    if dry_run:
        print(f"Would ensure deck {KANJI_DECK} and seed up to {len(notes)} kanji.")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        if anki_available():
            notes = without_ledger_kanji(notes)
        preview_changes(notes, KANJI_SCOPE, update=update)
        return

    notes = without_ledger_kanji(notes)
    add_or_update_notes(notes, KANJI_SCOPE, update=update)


# ---------------------------------------------------------------------------
# Notion ledger sync
# ---------------------------------------------------------------------------

def _retry_after(headers):
    try:
        return max(float(headers.get("Retry-After")), 0)
    except (TypeError, ValueError):
        return None


def notion_request(path, method="GET", body=None):
    """Call the Notion API. Rate limits, server errors and network failures
    are retried with backoff; anything else (or running out of attempts)
    exits the run."""
    url = f"{NOTION_API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for attempt in range(1, NOTION_MAX_ATTEMPTS + 1):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
        req.add_header("Notion-Version", NOTION_API_VERSION)
        req.add_header("Content-Type", "application/json")
        last_try = attempt == NOTION_MAX_ATTEMPTS
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            if e.code not in NOTION_RETRY_STATUS or last_try:
                print(f"Notion API error {e.code}: {detail}", file=sys.stderr)
                sys.exit(1)
            reason = f"HTTP {e.code}"
            wait = _retry_after(e.headers)
        except (urllib.error.URLError, OSError) as e:
            if last_try:
                print(f"Could not reach the Notion API: {e}", file=sys.stderr)
                sys.exit(1)
            reason = str(getattr(e, "reason", e))
            wait = None
        if wait is None:
            wait = 2 ** (attempt - 1)
        print(f"Notion request failed ({reason}); retrying in {wait:g}s...",
              file=sys.stderr)
        time.sleep(wait)


def fetch_all_rows():
    """Every row of the ledger. Since Notion API 2025-09-03 a database holds
    one or more data sources, and rows are queried per data source."""
    database = notion_request(f"/databases/{NOTION_DATABASE_ID}")
    sources = database.get("data_sources") or []
    if not sources:
        print("The Notion database has no data sources to read.", file=sys.stderr)
        sys.exit(1)
    rows = []
    for source in sources:
        body = {"page_size": 100}
        while True:
            result = notion_request(f"/data_sources/{source['id']}/query", "POST", body)
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


# Sentence breaks for grammar explanations: a period followed by whitespace,
# except after common abbreviations like "e.g." and "vs.".
_SENTENCE_BREAK = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<!vs\.)(?<!etc\.)(?<=\.)\s+")

_HEADLINE = '<div style="font-size:1.3em"><b>{}</b></div>'
_LINE = "<div>{}</div>"
_NOTE = '<div style="font-size:0.8em; opacity:0.65; margin-top:0.4em">{}</div>'


def split_note(text):
    """Split "core — side note" into (core, note); note is "" if absent.
    Only a separator outside parentheses counts, so asides like
    "noon (the pivot — NOT afternoon)" stay in one piece."""
    depth = 0
    for i, ch in enumerate(text):
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth = max(depth - 1, 0)
        elif depth == 0 and text.startswith(NOTE_SEP, i):
            return text[:i].strip(), text[i + len(NOTE_SEP):].strip()
    return text.strip(), ""


def sentences(text):
    return [s for s in _SENTENCE_BREAK.split(text.strip()) if s]


def format_back(item_type, readings, meaning):
    """Render the Back field as HTML: meaning first as a headline, then
    readings, then any side notes in smaller, faded text."""
    esc = html.escape
    parts = []

    if item_type == "Grammar":
        # Grammar rows are prose: first sentence as the headline, the rest
        # one sentence per line so the explanation is scannable on review.
        lines = sentences(meaning) + sentences(readings)
        if lines:
            parts.append(_HEADLINE.format(esc(lines[0])))
            parts.extend(_LINE.format(esc(s)) for s in lines[1:])
        return "".join(parts)

    meaning_core, meaning_note = split_note(meaning)
    readings_core, readings_note = split_note(readings)
    # Some Kanji rows (e.g. 万/千/百) hold a prose explanation in Meaning:
    # headline its first sentence and put the rest on their own lines.
    meaning_lines = sentences(meaning_core)
    if meaning_lines:
        parts.append(_HEADLINE.format(esc(meaning_lines[0])))
        parts.extend(_LINE.format(esc(s)) for s in meaning_lines[1:])
    if readings_core:
        parts.append(_LINE.format(esc(readings_core)))
    for note in (readings_note, meaning_note):
        if note:
            parts.append(_NOTE.format(esc(note)))
    return "".join(parts)


def skip_reason(page):
    """Return why a ledger row shouldn't become a card, or None to sync it."""
    props = page["properties"]
    item = get_prop(props, "Item", "title").strip()
    language = get_prop(props, "Language", "select")
    if not item:
        return "empty Item"
    if item.upper().startswith(SKIP_PREFIX):
        return f"marked {SKIP_PREFIX}"
    if language and language != LANGUAGE:
        return f"Language is {language}"
    return None


def row_to_note(page):
    props = page["properties"]
    item = get_prop(props, "Item", "title")
    meaning = get_prop(props, "Meaning", "rich_text")
    readings = get_prop(props, "Readings", "rich_text")
    item_type = get_prop(props, "Type", "select") or "Vocab"
    lesson = get_prop(props, "Lesson", "number")

    back = format_back(item_type, readings, meaning)

    deck = f"{DECK_ROOT}::{item_type}"
    tags = [f"lesson{lesson}"] if lesson else []
    # Anki tags can't contain spaces: "Grammar Drill" -> "grammar_drill".
    tags.append(item_type.lower().replace(" ", "_"))
    tags.append(link_tag(page["id"]))

    return {
        "deckName": deck,
        "modelName": NOTE_TYPE,
        "fields": {"Front": item, "Back": back},
        "tags": tags,
        "options": NOTE_OPTIONS,
    }


def link_tag(page_id):
    return LINK_TAG_PREFIX + page_id.replace("-", "").lower()


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


def anki_available():
    """True if AnkiConnect answers. --dry-run uses this so it still works
    with Anki closed."""
    data = json.dumps({"action": "version", "version": 6}).encode("utf-8")
    req = urllib.request.Request(ANKICONNECT_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        return False


def anki_multi(calls):
    """Run [(action, params), ...] in order, batched through AnkiConnect's
    "multi" action. Errors are printed; returns how many calls failed."""
    failed = 0
    for i in range(0, len(calls), ANKI_MULTI_CHUNK):
        chunk = calls[i:i + ANKI_MULTI_CHUNK]
        actions = [{"action": a, "version": 6, "params": p} for a, p in chunk]
        results = anki_request("multi", actions=actions)
        if results is None:
            failed += len(chunk)
            continue
        for (action, _), r in zip(chunk, results):
            error = r.get("error") if isinstance(r, dict) else None
            if error:
                print(f"AnkiConnect error on {action}: {error}", file=sys.stderr)
                failed += 1
    return failed


def _field(info, name):
    return info.get("fields", {}).get(name, {}).get("value", "")


def _note_link(tags):
    """The notion_<page id> tag among `tags`, lowercased, or None."""
    for t in tags:
        if t.lower().startswith(LINK_TAG_PREFIX):
            return t.lower()
    return None


_STYLE_ATTR = re.compile(r'style="([^"]*)"')


def same_html(a, b):
    """Compare field HTML loosely, so a note isn't rewritten on every run
    just because Anki stored it with different entities, whitespace or
    style formatting."""
    def norm(s):
        s = _STYLE_ATTR.sub(
            lambda m: 'style="%s"' % re.sub(r"\s+", "", m.group(1)).rstrip(";"), s)
        return re.sub(r"\s+", " ", html.unescape(s)).strip()
    return norm(a) == norm(b)


def find_notes(scope):
    """notesInfo for every NOTE_TYPE note matching the Anki search `scope`."""
    ids = anki_request("findNotes", query=f'note:"{NOTE_TYPE}" {scope}') or []
    return (anki_request("notesInfo", notes=ids) or []) if ids else []


def plan_changes(notes, scope, update=True, prune=False, adopt=None):
    """Work out what syncing `notes` would change in Anki. Read-only.

    Only notes of NOTE_TYPE inside `scope` (an Anki search) are considered.
    An incoming note matches the existing note carrying the same link tag
    (notion_<page id>); failing that, an existing note without a link tag
    and with the same Front. Each existing note is matched at most once.

    update=False: matched notes are left exactly as they are.
    prune=True: linked notes whose row is gone are marked for deletion.
    adopt=(other scope, deck): an incoming note for `deck` that matched
    nothing may take over the note with the same Front in the other scope
    (it's then moved into `deck`, keeping its review history).
    """
    plan = {"add": [], "rejected": [], "update": [], "move": [], "retag": [],
            "delete": [], "unlinked": [], "unchanged": 0, "kept": 0}

    # Two incoming notes with the same deck and Front can't both exist in
    # Anki (and would keep overwriting one card), so only the first is used.
    seen = set()
    unique = []
    for n in notes:
        key = (n["deckName"], n["fields"]["Front"])
        if key in seen:
            plan["rejected"].append((n, "another row has the same Item and Type"))
            continue
        seen.add(key)
        unique.append(n)

    by_link, by_front = {}, {}
    for info in find_notes(scope):
        link = _note_link(info.get("tags", []))
        if link:
            by_link.setdefault(link, info)
        else:
            by_front.setdefault(_field(info, "Front"), info)

    adopt_deck, adoptable = None, {}
    if adopt and any(n["deckName"] == adopt[1] for n in unique):
        adopt_deck = adopt[1]
        for info in find_notes(adopt[0]):
            adoptable.setdefault(_field(info, "Front").strip(), info)

    matched = []
    for n in unique:
        link = _note_link(n["tags"])
        info = by_link.pop(link, None) if link else None
        if info is None:
            info = by_front.pop(n["fields"]["Front"], None)
        if info is None and n["deckName"] == adopt_deck:
            info = adoptable.pop(n["fields"]["Front"].strip(), None)
        if info is None:
            plan["add"].append(n)
        elif update:
            matched.append((n, info))
        else:
            plan["kept"] += 1

    if prune:
        # Linked notes left over belong to rows that are gone (or now
        # skipped). Unlinked leftovers may be hand-made, so never delete them.
        plan["delete"] = list(by_link.values())
        plan["unlinked"] = list(by_front.values())

    # Which deck each matched card is in, to catch Type changes.
    card_ids = [c for _, info in matched for c in info.get("cards", [])]
    deck_of = {}
    if card_ids:
        for deck, cards in (anki_request("getDecks", cards=card_ids) or {}).items():
            for c in cards:
                deck_of[c] = deck

    owned = TYPE_TAGS | {t.lower() for n in unique for t in n["tags"]}
    for n, info in matched:
        changed = False
        if not (same_html(_field(info, "Front"), n["fields"]["Front"])
                and same_html(_field(info, "Back"), n["fields"]["Back"])):
            plan["update"].append((n, info))
            changed = True

        stray = [c for c in info.get("cards", [])
                 if deck_of.get(c, n["deckName"]) != n["deckName"]]
        if stray:
            plan["move"].append((n, info, stray, deck_of[stray[0]]))
            changed = True

        current = {t.lower() for t in info.get("tags", [])}
        wanted = {t.lower() for t in n["tags"]}
        add = [t for t in n["tags"] if t.lower() not in current]
        remove = [t for t in info.get("tags", [])
                  if t.lower() not in wanted
                  and (t.lower() in owned or _LESSON_TAG.fullmatch(t)
                       or t.lower().startswith(LINK_TAG_PREFIX))]
        if add or remove:
            plan["retag"].append((n, info, add, remove))
            changed = True

        if not changed:
            plan["unchanged"] += 1

    # Ask Anki up front which new notes it will accept, so the counts are
    # right and one bad note can't fail the whole addNotes batch.
    if plan["add"]:
        checks = anki_request("canAddNotesWithErrorDetail", notes=plan["add"])
        if checks is None:
            checks = [{"canAdd": True}] * len(plan["add"])
        addable = []
        for n, check in zip(plan["add"], checks):
            # A missing deck is fine: the run creates it before adding.
            if check.get("canAdd") or (check.get("error") or "").startswith(
                    "deck was not found"):
                addable.append(n)
            else:
                plan["rejected"].append((n, check.get("error") or "rejected by Anki"))
        plan["add"] = addable

    return plan


def print_plan(plan, limit=15):
    """List each pending change, at most `limit` lines per kind."""
    def show(title, lines):
        if not lines:
            return
        print(f"{title} ({len(lines)}):")
        for line in lines[:limit]:
            print("  " + line)
        if len(lines) > limit:
            print(f"  ... and {len(lines) - limit} more")

    def front(n):
        return n["fields"]["Front"]

    def renamed(n, info):
        old = _field(info, "Front")
        return front(n) if same_html(old, front(n)) else f"{old} -> {front(n)}"

    show("New", [f"{front(n)}  [{n['deckName']}]" for n in plan["add"]])
    show("Text changed", [renamed(n, info) for n, info in plan["update"]])
    show("Moved", [f"{front(n)}: {old} -> {n['deckName']}"
                   for n, _, _, old in plan["move"]])
    show("Tags changed", [
        f"{front(n)}: " + " ".join([f"+{t}" for t in add] + [f"-{t}" for t in rm])
        for n, _, add, rm in plan["retag"]])
    show("Deleted (no longer in the ledger)",
         [_field(info, "Front") for info in plan["delete"]])
    show("Not added", [f"{front(n)}: {reason}" for n, reason in plan["rejected"]])
    show("Not linked to a Notion row, so left alone",
         [_field(info, "Front") for info in plan["unlinked"]])


def summarize(plan, dry_run, added=None):
    prefix = "Would add" if dry_run else "Added"
    added = len(plan["add"]) if added is None else added
    text = (f"{prefix} {added} new notes. "
            f"Text changed: {len(plan['update'])}, moved: {len(plan['move'])}, "
            f"tags changed: {len(plan['retag'])}, deleted: {len(plan['delete'])}. "
            f"{plan['unchanged']} already up to date.")
    if plan["kept"]:
        text += f" {plan['kept']} already in Anki and left as is (--no-update)."
    return text


def preview_changes(notes, scope, update=True, prune=False, adopt=None):
    """--dry-run: show what a real run would change, if Anki is open."""
    if not anki_available():
        print("\nAnki isn't open, so this preview can't show what would "
              "change in Anki.")
        return
    plan = plan_changes(notes, scope, update=update, prune=prune, adopt=adopt)
    print()
    print_plan(plan)
    print(summarize(plan, dry_run=True))


def add_or_update_notes(notes, scope, update=True, prune=False, adopt=None):
    """Bring the Anki notes in `scope` in line with `notes` (dicts with
    deckName, modelName, fields, tags, options). See plan_changes for how
    notes are matched and what update/prune/adopt do."""
    plan = plan_changes(notes, scope, update=update, prune=prune, adopt=adopt)
    print_plan(plan)

    decks = {n["deckName"] for n in plan["add"]}
    decks |= {n["deckName"] for n, _, _, _ in plan["move"]}
    calls = [("createDeck", {"deck": d}) for d in sorted(decks)]
    for n, info in plan["update"]:
        calls.append(("updateNoteFields",
                      {"note": {"id": info["noteId"], "fields": n["fields"]}}))
    for n, _, cards, _ in plan["move"]:
        calls.append(("changeDeck", {"cards": cards, "deck": n["deckName"]}))
    for n, info, add, remove in plan["retag"]:
        if add:
            calls.append(("addTags", {"notes": [info["noteId"]], "tags": " ".join(add)}))
        if remove:
            calls.append(("removeTags",
                          {"notes": [info["noteId"]], "tags": " ".join(remove)}))
    if plan["delete"]:
        calls.append(("deleteNotes", {"notes": [i["noteId"] for i in plan["delete"]]}))
    failed = anki_multi(calls)

    added = 0
    if plan["add"]:
        results = anki_request("addNotes", notes=plan["add"])
        if results is None:
            failed += 1
        else:
            added = sum(1 for r in results if r is not None)

    print(summarize(plan, dry_run=False, added=added))
    if failed:
        print(f"{failed} Anki requests failed; see the errors above.", file=sys.stderr)


def sync_ledger(dry_run=False, update=True, prune=False):
    if "paste_your" in NOTION_TOKEN.lower() or "paste_your" in NOTION_DATABASE_ID.lower():
        print(
            "Set NOTION_TOKEN and NOTION_DATABASE_ID (env vars, or edit "
            "the top of this script) before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Fetching rows from Notion...")
    pages = fetch_all_rows()
    print(f"Found {len(pages)} rows in the ledger.")

    notes = []
    for p in pages:
        reason = skip_reason(p)
        if reason:
            item = get_prop(p["properties"], "Item", "title") or "(untitled)"
            print(f"Skipping {item!r}: {reason}")
            continue
        notes.append(row_to_note(p))
    decks = sorted(set(n["deckName"] for n in notes))

    if dry_run:
        print(f"Would ensure {len(decks)} decks: {decks}")
        print(f"Would sync {len(notes)} notes.")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, LEDGER_SCOPE, update=update, prune=prune,
                        adopt=(KANJI_SCOPE, LEDGER_KANJI_DECK))
        return

    add_or_update_notes(notes, LEDGER_SCOPE, update=update, prune=prune,
                        adopt=(KANJI_SCOPE, LEDGER_KANJI_DECK))


def preview_html(back):
    """Rough plain-text rendering of a Back field for --dry-run output."""
    text = re.sub(r"</div>", "\n", back)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return "\n".join("    " + line for line in text.splitlines() if line)


def main():
    # Windows consoles default to cp1252, which can't print kana.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be synced/seeded without changing Anki "
             "(with Anki open, also lists every change it would make)",
    )
    parser.add_argument(
        "--seed-kana", action="store_true",
        help="One-time seed of the full hiragana + katakana charts into "
             "Nihongo::Kana::Hiragana / Nihongo::Kana::Katakana, instead of "
             "syncing the Notion ledger",
    )
    parser.add_argument(
        "--seed-kanji", action="store_true",
        help="Seed the 1000 most frequent kanji into Nihongo::Core Kanji "
             "(skipping any already in Nihongo::Kanji), instead of syncing "
             "the Notion ledger",
    )
    parser.add_argument(
        "--no-update", dest="update", action="store_false",
        help="Only add new notes; leave existing notes untouched even if "
             "their content has changed (updating is ON by default)",
    )
    parser.add_argument(
        "--prune", action="store_true",
        help="Also delete ledger notes whose Notion row was deleted or is now "
             "skipped (deletes their review history too; try --dry-run first)",
    )
    parser.set_defaults(update=True)
    args = parser.parse_args()

    if args.seed_kana and args.seed_kanji:
        parser.error("--seed-kana and --seed-kanji are separate runs")
    if args.prune and (args.seed_kana or args.seed_kanji):
        parser.error("--prune only applies to the ledger sync, not the seeds")
    if args.prune and not args.update:
        parser.error("--prune can't be combined with --no-update")

    if args.seed_kana:
        seed_kana(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_kanji:
        seed_kanji(dry_run=args.dry_run, update=args.update)
        return

    sync_ledger(dry_run=args.dry_run, update=args.update, prune=args.prune)


if __name__ == "__main__":
    main()