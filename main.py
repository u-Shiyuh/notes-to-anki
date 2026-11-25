#!/usr/bin/env python3
"""
main.py

Seeds Japanese study decks into Anki via AnkiConnect.

NOTION SYNC IS DISABLED (2026-11-06): the Notion ledger is outdated and
Anki is now the source of truth, so running the sync would overwrite newer
Anki cards with stale Notion text. Running without a --seed-* option exits
with an error. The sync code is kept; set NOTION_SYNC_ENABLED = True to
bring it back. The Notion setup steps below only apply then.

Originally: syncs your Notion "Language Learning Ledger" database into
Anki, reading rows via the Notion API.

Also supports a one-time seed of the FULL hiragana + katakana charts
(gojuon, dakuten/handakuten, and yoon combos) into their own Anki
decks, for kana recognition practice separate from the Notion ledger,
and a seed of the 1000 most frequent kanji (kanji_top1000.tsv) plus the
JLPT N5/N4 kanji outside them (kanji_extra.tsv), a seed of the verbs
from the user's reviewer book (verbs.tsv), and a seed of the JLPT N5/N4
words other than verbs (words.tsv).

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
   (Notion sync, disabled; only with NOTION_SYNC_ENABLED = True:)
   python3 main.py                 # sync the Notion ledger into Anki
   python3 main.py --dry-run       # preview the Notion sync only
   python3 main.py --no-update     # only add new notes, don't touch existing ones
   python3 main.py --prune         # also delete cards whose Notion row is gone

   python3 main.py --seed-kana                # one-time: add all hiragana + katakana
   python3 main.py --seed-kana --dry-run       # preview the kana seed only
   python3 main.py --seed-kana --no-update     # only add new kana, don't fix existing ones

   python3 main.py --seed-kanji               # add the 1000 most frequent kanji + N5/N4
   python3 main.py --seed-kanji --dry-run     # preview the kanji seed only

   python3 main.py --seed-verbs               # add the reviewer book's verbs (verbs.tsv)
   python3 main.py --seed-verbs --dry-run     # preview the verb seed only

   python3 main.py --seed-words               # add the JLPT N5/N4 words (words.tsv)
   python3 main.py --seed-words --dry-run     # preview the word seed only

   python3 main.py --seed-numbers             # add numbers, counters, times, dates (numbers.tsv)
   python3 main.py --seed-numbers --dry-run   # preview the numbers seed only

   python3 main.py --seed-lookalikes          # add look-alike pairs of studied kanji
   python3 main.py --seed-lookalikes --dry-run  # preview (needs Anki open)

   python3 main.py --seed-sentences           # add Tatoeba sentences (sentences.tsv)
   python3 main.py --seed-sentences --dry-run # preview the sentence seed only

   python3 main.py --order                    # kanji met in studied words first, then
                                              # the kanji the next words need; words
                                              # whose kanji are studied first;
                                              # verbs too, godan and ichidan
                                              # alternating
   python3 main.py --order --dry-run          # just report what would move

   python3 main.py --seed-words --profile verge   # work on another Anki profile
       Every run uses the profile "User 1" (DEFAULT_PROFILE, or the
       NOTES_TO_ANKI_PROFILE env var) unless --profile names another; it
       opens that profile first and reopens the previous one at the end.

Safe to re-run any time. Each mode only looks at its own notes: the kana
seed at Nihongo::Kana::*, the kanji seed at its own (unlinked) notes in
Nihongo::Core Kanji, the verb seed at Nihongo::Verbs, the word seed at
Nihongo::Words, the ledger sync at the other Nihongo notes. A Notion Vocab
row whose word is in words.tsv or verbs.tsv is skipped, and that seed takes
over its card (keeping its review history). Ledger
Kanji rows also go to Nihongo::Core Kanji. The kanji seed skips kanji
that already have a ledger card, and when a ledger Kanji row is added for
a seeded kanji, the sync takes over that card (keeping its review
history) rather than creating a second one.
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
import contextlib
import functools
import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
except ImportError:  # only the (disabled) Notion sync needs .env
    def load_dotenv():
        pass

# Loads variables from a .env file (same folder as this script) into the
# environment. Create a .env file next to this script with:
#
#   NOTION_TOKEN=your_secret_here
#   NOTION_DATABASE_ID=your_database_id_here
#
load_dotenv()

# The Notion ledger is outdated (2026-11-06); Anki is the source of truth.
# The sync would overwrite newer Anki cards with stale Notion text, so it's
# off. Flip to True only once Notion is brought up to date.
NOTION_SYNC_ENABLED = False

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

# Card look, applied to NOTE_TYPE by ensure_card_style(). The Front field
# stays raw text (it's a matching key), so the template wraps it: short
# fronts (kana, kanji, words) are large; long ones (sentences) are tagged
# `long` by the script and shown smaller so they don't wrap too much.
CARD_FRONT = (
    '<div class="front">{{Front}}</div>\n'
    '<script>document.querySelectorAll(".front").forEach(function (e) {'
    ' if (e.textContent.trim().length > 8) e.classList.add("long"); });</script>'
)
CARD_BACK = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}"
CARD_CSS = """.card {
    font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic UI",
        "Yu Gothic", "Meiryo", "Noto Sans JP", sans-serif;
    font-size: 22px;
    line-height: 1.5;
    text-align: center;
    color: black;
    background-color: white;
}
.front { font-size: 2.6em; line-height: 1.3; margin: 0.3em 0; }
.front.long { font-size: 1.5em; }
"""

# Ledger notes are tagged notion_<page id without dashes>. That tag, not
# the Front text, is what links a card to its Notion row.
LINK_TAG_PREFIX = "notion_"

# Each mode only matches (and may only change) notes inside its own scope,
# so a ledger card "は" and the hiragana card "は" never overwrite each other.
# Core Kanji is shared: ledger Kanji rows live there too (TYPE_DECKS), told
# apart from the seed's notes by their link tag. ("\_" is a literal "_" in
# Anki searches, where a bare "_" matches any character.)
KANJI_DECK = f"{DECK_ROOT}::Core Kanji"
VERB_DECK = f"{DECK_ROOT}::Verbs"
WORD_DECK = f"{DECK_ROOT}::Words"
NUMBER_DECK = f"{DECK_ROOT}::Numbers & Time"
LOOKALIKE_DECK = f"{DECK_ROOT}::Kanji Look-alikes"
SENTENCE_DECK = f"{DECK_ROOT}::Sentences"
VOCAB_DECK = f"{DECK_ROOT}::Vocab"
# Fast lanes (2026-11-14, user's request): new cards wait here, with their own
# daily limit, instead of deep in their home deck's queue; --order moves them
# in and, once mature, back home (same note, history kept). LESSON_DECK: new
# Words/Verbs/Core Kanji cards a lesson in references.tsv mentions, and the
# kanji of those words; BASICS_DECK: other new N5/N4 kanji.
LESSON_DECK = f"{DECK_ROOT}::Lessons"
BASICS_DECK = f"{DECK_ROOT}::Kanji N5-N4"
BASICS_LEVELS = ("5", "4")
MATURE_DAYS = 21                # Anki's "mature": interval of 21 days or more
# Home deck -> its lanes: a seed treats a card in one of them as in place.
# Every study deck a lesson can mention belongs here (a future deck too), with
# the tag its seed gives every note, so its lane cards stay in its seed's scope.
LANES = {KANJI_DECK: (LESSON_DECK, BASICS_DECK), WORD_DECK: (LESSON_DECK,),
         VERB_DECK: (LESSON_DECK,), NUMBER_DECK: (LESSON_DECK,)}
LANE_HOME_TAGS = {WORD_DECK: "word", VERB_DECK: "verb", KANJI_DECK: "core_kanji",
                  NUMBER_DECK: "numbers"}


def deck_query(deck):
    """Anki search for a home deck's cards, including those in its lanes."""
    if deck not in LANES:
        return f'"deck:{deck}"'
    tag = LANE_HOME_TAGS[deck]
    lanes = " OR ".join(f'("deck:{lane}" tag:{tag})' for lane in LANES[deck])
    return f'("deck:{deck}" OR {lanes})'


_LINKED = "tag:" + LINK_TAG_PREFIX.replace("_", "\\_") + "*"
KANA_SCOPE = f'"deck:{DECK_ROOT}::Kana"'
KANJI_SCOPE = f'{deck_query(KANJI_DECK)} -{_LINKED}'
VERB_SCOPE = deck_query(VERB_DECK)
WORD_SCOPE = deck_query(WORD_DECK)
NUMBER_SCOPE = deck_query(NUMBER_DECK)
LOOKALIKE_SCOPE = f'"deck:{LOOKALIKE_DECK}"'
SENTENCE_SCOPE = f'"deck:{SENTENCE_DECK}"'
VOCAB_SCOPE = f'"deck:{VOCAB_DECK}"'
LEDGER_SCOPE = (f'"deck:{DECK_ROOT}" -"deck:{DECK_ROOT}::Kana" -{VERB_SCOPE} '
                f'-{WORD_SCOPE} -{NUMBER_SCOPE} -{LOOKALIKE_SCOPE} -{SENTENCE_SCOPE} -"deck:{LESSON_DECK}" -"deck:{BASICS_DECK}" '
                f'(-"deck:{KANJI_DECK}" OR {_LINKED})')

# Ledger rows go to Nihongo::<Type>, except these. The kanji seed skips
# kanji that already have a ledger card, and a new ledger Kanji row takes
# over (adopts) the seed's card for its kanji instead of duplicating it.
TYPE_DECKS = {"Kanji": KANJI_DECK}
LEDGER_KANJI_SCOPE = f'"deck:{DECK_ROOT}" {_LINKED} tag:kanji'

# The 1000 most frequent kanji, generated from KANJIDIC2 (see its header).
KANJI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "kanji_top1000.tsv")
# Kanji outside the top 1000, same columns: JLPT N5/N4 kanji the top 1000
# misses, and ledger kanji. The seed adds them after the top 1000.
KANJI_EXTRA_FILE = os.path.join(os.path.dirname(KANJI_FILE), "kanji_extra.tsv")
# Radicals (部首) the kanji files' 9th column points to, by number and form.
RADICAL_FILE = os.path.join(os.path.dirname(KANJI_FILE), "radicals.tsv")
PARTS_FILE = os.path.join(os.path.dirname(KANJI_FILE), "parts.tsv")
# Verbs from the reviewer book, in book order (see its header).
VERB_FILE = os.path.join(os.path.dirname(KANJI_FILE), "verbs.tsv")
# JLPT N5/N4 words (no verbs), in study order (see its header).
WORD_FILE = os.path.join(os.path.dirname(KANJI_FILE), "words.tsv")
# words.tsv's topic column becomes a tag, e.g. topic_body (Custom Study by tag).
TOPIC_TAG_PREFIX = "topic_"
NUMBER_FILE = os.path.join(os.path.dirname(KANJI_FILE), "numbers.tsv")
# Look-alike kanji pairs (tools/add_lookalikes.py); seeded once both are studied.
LOOKALIKE_FILE = os.path.join(os.path.dirname(KANJI_FILE), "lookalikes.tsv")
# Study-source references (study/profile.md): Fronts per lesson, tagged ref::<ref>.
REFERENCE_FILE = os.path.join(os.path.dirname(KANJI_FILE), "references.tsv")
REF_TAG_PREFIX = "ref::"

# Per-profile settings (added 2026-11-21, for the friend's profile): an Anki
# profile can have users/<profile>/user.json; anki_profile() loads it for the
# run. Without one (the user's own profile) the defaults apply, so nothing
# changes for them. Keys:
#   ref_sources  which ref:: sources a card may carry, by first part ("jlpt",
#                "tatoeba", "verb_book", "cg"...); null = all. Leaving out a
#                book also drops its references.tsv lessons, so no Lessons lane.
#   order        "adaptive": --order runs the fast lanes and the review-based
#                steps; "default": it follows default_order.tsv instead.
USERS_DIR = os.path.join(os.path.dirname(KANJI_FILE), "users")
USER_DEFAULTS = {"ref_sources": None, "order": "adaptive"}
USER_ORDERS = ("adaptive", "default")
USER = dict(USER_DEFAULTS)


def load_user(profile):
    """users/<profile>/user.json over USER_DEFAULTS ("about" is a free note)."""
    settings = dict(USER_DEFAULTS)
    path = os.path.join(USERS_DIR, profile, "user.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            settings.update(json.load(f))
    unknown = set(settings) - set(USER_DEFAULTS) - {"about"}
    if unknown or settings["order"] not in USER_ORDERS:
        print(f"{path}: unknown key(s) {sorted(unknown)} or order "
              f"{settings['order']!r} (use {', '.join(USER_ORDERS)}).", file=sys.stderr)
        sys.exit(1)
    return settings


def use_user(profile):
    """Make `profile`'s settings the ones this run uses."""
    USER.clear()
    USER.update(load_user(profile))
    references.cache_clear()


def ref_allowed(tag):
    """True if this profile's ref_sources lets a card carry ref:: tag `tag`."""
    sources = USER["ref_sources"]
    return sources is None or tag[len(REF_TAG_PREFIX):].split("::")[0] in sources
# Tatoeba example sentences readable with studied cards (tools/add_sentences.py).
SENTENCE_FILE = os.path.join(os.path.dirname(KANJI_FILE), "sentences.tsv")

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
# Core kanji seed — the 1000 most frequent kanji, from kanji_top1000.tsv,
# then the N5/N4 kanji outside them, from kanji_extra.tsv
# ---------------------------------------------------------------------------

def load_kanji(path=KANJI_FILE):
    """Rows of a kanji TSV (KANJI_FILE by default) as dicts, in file order."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t")
                cols += [""] * (10 - len(cols))
                rank, kanji, strokes, jlpt, meanings, on, kun, example, radical, parts = cols[:10]
                rows.append({"rank": rank, "kanji": kanji, "strokes": strokes,
                             "jlpt": jlpt, "meanings": meanings.split("; "),
                             "on": on, "kun": kun,
                             "example": example.split("|") if example else None,
                             "radical": radical, "parts": parts.split()})
    except OSError as e:
        print(f"Could not read the kanji list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


@functools.cache
def core_kanji():
    """KANJI_FILE and KANJI_EXTRA_FILE rows keyed by kanji (loaded once)."""
    rows = load_kanji() + load_kanji(KANJI_EXTRA_FILE)
    return {row["kanji"]: row for row in rows}


def kanji_key(front):
    """The kanji a Kanji card is about: its Front up to the first space, so
    a ledger Item like "万 (man, 10000)" still counts as 万."""
    return (front.split() or [""])[0]


def kanji_readings(label, readings):
    """One "On:"/"Kun:" line. The readings marked * in KANJI_FILE are bold:
    the most common one (always first), then any other reading a learned
    word or verb uses (後 あと). The rest are faded. With no common
    reading, the readings are all rare, so all are faded, even a lone one
    (万's よろず)."""
    esc = html.escape
    items = readings.split("、")
    bold = []
    while items and items[0].startswith("*"):
        bold.append(items.pop(0).lstrip("*"))
    line, sep = f"{label}: ", ""
    if bold:
        line += f"<b>{esc('、'.join(bold))}</b>"
        sep = "、"
    if items:
        line += f'<span style="opacity:0.65">{sep}{esc("、".join(items))}</span>'
    return _LINE.format(line)


def example_word(word, kana, gloss, level):
    """The line under "On:" that pairs the on'yomi with a common word,
    and the word's own JLPT level if it has one."""
    esc = html.escape
    gloss += f" · {level}" if level else ""
    return _LINE.format(f"e.g. {esc(word)} ({esc(kana)}) "
                        f'<span style="opacity:0.65">{esc(gloss)}</span>')


@functools.cache
def radicals():
    """RADICAL_FILE rows keyed by "number|form" (the kanji files' 9th column)."""
    out = {}
    try:
        with open(RADICAL_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                no, form, name, meaning = line.rstrip("\n").split("\t")[:4]
                out[f"{no}|{form}"] = {"form": form, "name": name, "meaning": meaning}
    except OSError as e:
        print(f"Could not read the radical list: {e}", file=sys.stderr)
        sys.exit(1)
    return out


def radical_line(row):
    """The faded "Radical:" line, or "" when the kanji has none. A kanji
    that is its own radical (日, 白) says so (since 2026-11-14, user's
    request; before, the line was hidden). Exits on a radical missing from
    RADICAL_FILE."""
    if not row["radical"]:
        return ""
    rad = radicals().get(row["radical"])
    if rad is None:
        print(f"Kanji {row['kanji']}: radical {row['radical']} is not in "
              f"{os.path.basename(RADICAL_FILE)} (run tools/add_radicals.py --write)",
              file=sys.stderr)
        sys.exit(1)
    own = " (this kanji is a radical itself)" if rad["form"] == row["kanji"] else ""
    return _NOTE.format(html.escape(f"Radical: {radical_text(rad)}{own}"))


@functools.cache
def part_info():
    """PARTS_FILE rows for the parts that are neither a radical nor a Core
    Kanji: part -> (meaning, on, kun), readings in hiragana (宛 -> address,
    えん, あて)."""
    out = {}
    try:
        with open(PARTS_FILE, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t") + [""] * 3
                out[cols[0]] = tuple(cols[1:4])
    except OSError as e:
        print(f"Could not read the parts list: {e}", file=sys.stderr)
        sys.exit(1)
    return out


def _kanji_readings(row):
    """A Core Kanji row's main on'yomi (in hiragana) and its first kun'yomi
    that is a word on its own (てら, not う(る) or -ごと); starred first."""
    def first(text):
        items = [r for r in text.split("、") if r]
        items.sort(key=lambda r: not r.startswith("*"))
        return [r.lstrip("*") for r in items]
    on = next(iter(first(row["on"])), "")
    kun = next((r for r in first(row["kun"]) if "(" not in r and "-" not in r), "")
    return _hiragana(on), kun


def parts_text(row):
    """The text of a kanji's Parts line (2026-11-25, user's request): the components
    the kanji is built from (KanjiVG, via tools/add_parts.py), each with its
    reading in hiragana and a short meaning, e.g. "言 げん speech · 売 ばい
    sell (sound)". The sound part (`~` in the parts column, KanjiVG's
    kvg:phon) shows its on'yomi, a hint at the kanji's own; other parts show
    their radical name (氵 さんずい) or, failing that, their kun'yomi word
    (寺 てら), else their on'yomi. Meanings: radicals.tsv, then the part's
    own Core Kanji row, then PARTS_FILE. "" when the row has no parts (a
    kanji that is one simple shape)."""
    by_form = {}
    for key, rad in radicals().items():
        by_form.setdefault(rad["form"], {})[key] = rad
    shown = []
    for i, part in enumerate(row["parts"]):
        sound = part.startswith("~")
        part = part.lstrip("~")
        rads = by_form.get(part, {})
        if row["radical"] in rads:  # 月 and 阝 are two radicals each
            rad = rads[row["radical"]]
        elif part == "阝":  # on the left: 170 hill; on the right: 163 village
            rad = rads.get("170|阝" if i == 0 else "163|阝")
        else:
            rad = next(iter(rads.values()), None)
        if part in core_kanji():
            own = core_kanji()[part]
            on, kun = _kanji_readings(own)
            meaning = own["meanings"][0]
        else:
            meaning, on, kun = part_info().get(part, ("", "", ""))
        if rad:
            meaning = rad["meaning"]
        if sound:
            reading = on or kun or (rad or {}).get("name", "")
        else:
            reading = (rad or {}).get("name", "") or kun or on
        text = " ".join(x for x in (part, reading, meaning.split(";")[0]) if x)
        shown.append(text + (" (sound)" if sound else ""))
    return " · ".join(shown)


def parts_line(row):
    """The faded "Parts:" line of a Core Kanji card (2026-11-25, user's
    request); see parts_text. "" for a kanji that is one simple shape."""
    if not row["parts"]:
        return ""
    return _NOTE.format(html.escape("Parts: " + parts_text(row)))


def parts_lines(kanji):
    """The Parts line for a word-type card (2026-11-25, user's request: same
    as Core Kanji, on every deck): "Parts: …" for one kanji, or "Parts: 時:
    … ／ 間: …" for several, each from its Core Kanji row. Kanji that are one
    simple shape (日) or have no row are left out; "" when none are left."""
    rows = [core_kanji().get(k) for k in dict.fromkeys(kanji)]
    rows = [r for r in rows if r and r["parts"]]
    if not rows:
        return ""
    if len(rows) == 1 and len(set(kanji)) == 1:
        return _NOTE.format(html.escape("Parts: " + parts_text(rows[0])))
    text = " ／ ".join(f"{r['kanji']}: {parts_text(r)}" for r in rows)
    return _NOTE.format(html.escape("Parts: " + text))


def radical_text(rad):
    """A radicals() row as "氵 さんずい · water"."""
    return " · ".join(x for x in (f"{rad['form']} {rad['name']}".strip(), rad["meaning"]) if x)


def kanji_back(row, headline=None, notes=()):
    """The Core Kanji Back layout for one KANJI_FILE row. The ledger passes
    its own Meaning as `headline` (HTML) and its side notes as `notes`."""
    esc = html.escape
    parts = [headline or _HEADLINE.format(esc(", ".join(row["meanings"])))]
    if row["on"]:
        parts.append(kanji_readings("On", row["on"]))
    if row["example"]:
        parts.append(example_word(*row["example"]))
    if row["kun"]:
        parts.append(kanji_readings("Kun", row["kun"]))
    for note in notes:
        parts.append(_NOTE.format(esc(note)))
    parts.append(radical_line(row))
    parts.append(parts_line(row))
    facts = [f"{row['strokes']} stroke" + ("" if row["strokes"] == "1" else "s")]
    if row["jlpt"]:
        facts.append(f"JLPT N{row['jlpt']}")
    facts.append(f"#{row['rank']} by frequency")
    parts.append(_NOTE.format(esc(" · ".join(facts))))
    return "".join(parts)


@functools.cache
def kanji_topics():
    """Topic of each one-kanji word whose Core Kanji card teaches it (頭 →
    body): the word seed skips those words, so their kanji card carries the
    words.tsv topic instead."""
    return {r["word"]: r["topic"] for r in load_words()
            if r["topic"] and kanji_card_covers(r)}


@functools.cache
def kanji_word_notes():
    """Note of each one-kanji word whose Core Kanji card teaches it (父 →
    "your own father..."): the word seed skips those words, so their kanji
    card shows the words.tsv note instead (since 2026-11-14, user's request)."""
    return {r["word"]: r["note"] for r in load_words()
            if r["note"] and kanji_card_covers(r)}


@functools.lru_cache(maxsize=None)
def references():
    """REFERENCE_FILE as {front: [ref tag, ...]}, tags in file order."""
    refs = {}
    if not os.path.exists(REFERENCE_FILE):
        return refs
    with open(REFERENCE_FILE, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            ref, _, fronts = line.rstrip("\n").partition("\t")
            if ref == "ref":
                continue
            for front in fronts.split():
                tag = REF_TAG_PREFIX + ref.strip()
                if not ref_allowed(tag):
                    continue
                if tag not in refs.setdefault(front, []):
                    refs[front].append(tag)
    return refs


def ref_tags(front, *sources):
    """The ref:: tags of a card: the given sources (e.g. "jlpt::n5", skipping
    blanks), then REFERENCE_FILE's lessons that mention its Front."""
    tags = [REF_TAG_PREFIX + s for s in sources if s and ref_allowed(REF_TAG_PREFIX + s)]
    return tags + [t for t in references().get(front, []) if t not in tags]


def verb_source(section):
    """ref:: source of a verbs.tsv section: the reviewer book's numbered sections,
    JLPT N5 for `extra`; other sections (cg) are covered by REFERENCE_FILE."""
    if section.isdigit():
        return f"verb_book::s{section}"
    return "jlpt::n5" if section == "extra" else ""


def kanji_note(row):
    """Build an AnkiConnect note dict for one Core Kanji row."""
    tags = ["kanji", "core_kanji"]
    if row["jlpt"]:
        tags.append(f"jlpt_n{row['jlpt']}")
    if row["kanji"] in kanji_topics():
        tags.append(TOPIC_TAG_PREFIX + kanji_topics()[row["kanji"]])
    tags += ref_tags(row["kanji"], row["jlpt"] and f"jlpt::n{row['jlpt']}")
    return {
        "deckName": KANJI_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": row["kanji"],
                   "Back": kanji_back(row, notes=[n for n in [kanji_word_notes().get(row["kanji"])] if n])},
        "tags": tags,
        "options": NOTE_OPTIONS,
    }


def without_ledger_kanji(notes):
    """Drop kanji that already have a ledger Kanji card (in Core Kanji, or
    still in another deck before the ledger sync moves it there)."""
    have = {kanji_key(_field(info, "Front")) for info in find_notes(LEDGER_KANJI_SCOPE)}
    kept = [n for n in notes if n["fields"]["Front"] not in have]
    skipped = [n["fields"]["Front"] for n in notes if n["fields"]["Front"] in have]
    if skipped:
        print(f"Skipping {len(skipped)} kanji that have a card from the Notion "
              "ledger: " + " ".join(skipped))
    return kept


def seed_kanji(dry_run=False, update=True):
    """Seed the Core Kanji deck (safe to re-run). Notes are added in
    frequency order, so Anki introduces the most common kanji first; the
    extra N5/N4 kanji follow the top 1000."""
    notes = [kanji_note(row) for row in core_kanji().values()]

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
# Verb seed — the reviewer book's verbs, from verbs.tsv, in book order
# ---------------------------------------------------------------------------

VERB_GROUPS = {"godan": "Godan (group 1)", "ichidan": "Ichidan (group 2)",
               "irregular": "Irregular (group 3)"}
# Before ます, a godan verb's final u-row kana becomes its i-row partner;
# before ない, its a-row partner (う → わ).
_GODAN_STEM = dict(zip("うくぐすつぬぶむる", "いきぎしちにびみり"))
_GODAN_NAI = dict(zip("うくぐすつぬぶむる", "わかがさたなばまら"))
# The godan た-form ending, by the dictionary form's last kana (the te-form
# song): 書く → 書いた, 飲む → 飲んだ, 待つ → 待った. て-forms swap た/だ for て/で.
_GODAN_TA = {"う": "った", "つ": "った", "る": "った", "む": "んだ", "ぶ": "んだ",
             "ぬ": "んだ", "く": "いた", "ぐ": "いだ", "す": "した"}
# Irregular endings: (dictionary form, ます-stem, ない-stem, た-form). 来る is
# written in kanji, so its changing reading (きます, こない) doesn't show.
_IRREGULAR = [("する", "し", "し", "した"), ("来る", "来", "来", "来た"),
              ("くる", "き", "こ", "きた")]


def load_verbs(path=VERB_FILE):
    """Rows of VERB_FILE as dicts, in file order. Exits on a row whose
    forms can't be built (unknown group, wrong ending, or an irregular verb
    that isn't a する/来る verb)."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if line.startswith("#") or not line.strip():
                    continue
                # Trailing blank columns may have lost their tabs to an editor.
                cols = line.rstrip("\n").split("\t")
                section, no, word, kana, meaning, group, masu, note, rads = \
                    (cols + [""] * 9)[:9]
                row = {"section": section, "no": no, "word": word,
                       "kana": kana, "meaning": meaning, "group": group,
                       "masu": masu, "note": note,
                       "radicals": [r.split(":", 1) for r in rads.split()]}
                try:
                    conjugations(row)
                except (KeyError, ValueError, StopIteration):
                    print(f"{path}:{lineno}: can't build the forms of {word} "
                          f"({group or 'no group'})", file=sys.stderr)
                    sys.exit(1)
                rows.append(row)
    except OSError as e:
        print(f"Could not read the verb list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


def conjugations(row):
    """The verb's ます, ない, た and て forms, as a dict in that order.
    Raises KeyError/ValueError/StopIteration if the group and ending don't
    fit. Exceptions: 行く (and verbs ending in it, 連れていく) → 行った/行って;
    ある → ない. A masu column in the file overrides the ます-form."""
    word, group = row["word"], row["group"]
    if group == "godan":
        last, base = word[-1], word[:-1]
        masu = base + _GODAN_STEM[last] + "ます"
        nai = "ない" if word == "ある" else base + _GODAN_NAI[last] + "ない"
        ta = base + ("った" if word.endswith(("行く", "いく")) else _GODAN_TA[last])
    elif group == "ichidan":
        if not word.endswith("る"):
            raise ValueError(word)
        masu, nai, ta = word[:-1] + "ます", word[:-1] + "ない", word[:-1] + "た"
    elif group == "irregular":
        dic, stem, nai_stem, ta_form = next(e for e in _IRREGULAR if word.endswith(e[0]))
        base = word[:-len(dic)]
        masu, nai, ta = base + stem + "ます", base + nai_stem + "ない", base + ta_form
    else:
        raise KeyError(group)
    te = ta[:-1] + ("て" if ta[-1] == "た" else "で")
    return {"ます": row["masu"] or masu, "ない": nai, "た": ta, "て": te}


def masu_form(row):
    """The polite ます-form: godan 書く → 書きます, ichidan 食べる → 食べます."""
    return conjugations(row)["ます"]


def conjugation_lines(row):
    """Two lines: ます and ない forms, then た and て, each after a faded label."""
    forms = list(conjugations(row).items())
    label = '<span style="opacity:0.65">{}</span> {}'
    return "".join(
        _LINE.format("　".join(label.format(html.escape(k), html.escape(v))
                              for k, v in pair))
        for pair in (forms[:2], forms[2:]))


def radicals_lines(items, label):
    """The faded radical (部首) line for (kanji, "no|form") pairs: "Radical:
    扌 てへん · hand", or with several "Radicals: 手: 手 て · hand ／ 伝: 亻
    にんべん · person". Unlike on kanji cards, a kanji that is its own
    radical (行) is still shown. "" when there are no kanji. Exits on a
    radical missing from RADICAL_FILE (`label` names the card)."""
    texts = []
    for kanji, key in items:
        rad = radicals().get(key)
        if rad is None:
            print(f"{label}: radical {key} is not in "
                  f"{os.path.basename(RADICAL_FILE)} (run tools/add_radicals.py --write)",
                  file=sys.stderr)
            sys.exit(1)
        texts.append((kanji, radical_text(rad)))
    if not texts:
        return ""
    if len(texts) == 1:
        return _NOTE.format(html.escape(f"Radical: {texts[0][1]}"))
    text = " ／ ".join(f"{k}: {t}" for k, t in texts)
    return _NOTE.format(html.escape(f"Radicals: {text}"))


def verb_radicals_line(row):
    """A verb's radical line, from VERB_FILE's own radicals column."""
    return radicals_lines(row["radicals"], f"Verb {row['word']}")


def text_radicals_line(text, label):
    """The radical line for a Words or Numbers & Time card, each kanji's
    radical taken from its Core Kanji row (every card word's kanji has one
    since 2026-11-12; tools/add_kanji_extra.py adds rows for new ones).
    A kanji used twice is listed once; 々 is skipped. Exits on a kanji
    with no Core Kanji row or no radical."""
    items = []
    for k in dict.fromkeys(_KANJI_CHAR.findall(text)):
        row = core_kanji().get(k)
        if not row or not row["radical"]:
            print(f"{label}: kanji {k} has no Core Kanji row with a radical "
                  "(run tools/add_kanji_extra.py --write, then tools/add_radicals.py --write)",
                  file=sys.stderr)
            sys.exit(1)
        items.append((k, row["radical"]))
    return radicals_lines(items, label)


def verb_back(row):
    """Back layout: meaning, reading (unless the word is all kana), the
    ます/ない/た/て forms, then the file's note, the radicals and the group
    in small, faded text."""
    esc = html.escape
    parts = [_HEADLINE.format(esc(row["meaning"]))]
    if row["kana"] != row["word"]:
        parts.append(_LINE.format(esc(row["kana"])))
    parts.append(conjugation_lines(row))
    if row["note"]:
        parts.append(_NOTE.format(esc(row["note"])))
    parts.append(verb_radicals_line(row))
    parts.append(parts_lines([k for k, _ in row["radicals"]]))
    facts = [VERB_GROUPS[row["group"]]]
    if row["group"] == "godan":
        facts.append(f"ends in {row['word'][-1]}")
    parts.append(_NOTE.format(esc(" · ".join(facts))))
    return "".join(parts)


def verb_note(row):
    """Build an AnkiConnect note dict for one VERB_FILE row."""
    return {
        "deckName": VERB_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": row["word"], "Back": verb_back(row)},
        "tags": ["verb", row["group"], f"section{row['section']}"]
                + ref_tags(row["word"], verb_source(row["section"])),
        "options": NOTE_OPTIONS,
    }


def seed_verbs(dry_run=False, update=True):
    """Seed Nihongo::Verbs from VERB_FILE (safe to re-run). Notes are added
    in book order, so Anki introduces them in that order."""
    notes = [verb_note(row) for row in load_verbs()]

    if dry_run:
        print(f"Would ensure deck {VERB_DECK} and seed {len(notes)} verbs.")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, VERB_SCOPE, update=update,
                        adopt=(VOCAB_SCOPE, VERB_DECK, str.strip))
        return

    add_or_update_notes(notes, VERB_SCOPE, update=update,
                        adopt=(VOCAB_SCOPE, VERB_DECK, str.strip))


# ---------------------------------------------------------------------------
# Word seed — JLPT N5/N4 words (no verbs), from words.tsv, in study order
# ---------------------------------------------------------------------------

# Tags for the file's types; any other type is tagged as written, with "_"
# for spaces.
WORD_TYPE_TAGS = {"い-adjective": "i_adjective", "な-adjective": "na_adjective",
                  "noun (+する)": "suru_noun", "する-verb": "suru_verb",
                  "pre-noun word": "pre_noun", "noun (grammar)": "noun"}
_KATAKANA = re.compile(r"[ァ-ヺ]")


def load_words(path=WORD_FILE):
    """Rows of WORD_FILE as dicts, in file order."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t")
                level, word, kana, meaning, typ, note, topic = (cols + [""] * 7)[:7]
                rows.append({"level": level, "word": word, "kana": kana,
                             "meaning": meaning, "type": typ, "note": note,
                             "topic": topic})
    except OSError as e:
        print(f"Could not read the word list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


def _hiragana(text):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def kanji_card_covers(row):
    """True if the word is a single kanji whose Core Kanji card already
    teaches it: the word's reading is the card's main bold reading (the
    first *) on the On or Kun line. Other bold readings mark words learned
    on their own card (後 あと), so they don't count."""
    k = core_kanji().get(row["word"])
    if not k:
        return False
    bold = {_hiragana(re.sub(r"[*\-.()]", "", line.split("、")[0]))
            for line in (k["on"], k["kun"]) if line.startswith("*")}
    return _hiragana(row["kana"]) in bold


@functools.cache
def seeded_words():
    """WORD_FILE rows the word seed adds: all but verbs.tsv's verbs and the
    one-kanji words their Core Kanji card covers."""
    verbs = {v["word"] for v in load_verbs()}
    return [r for r in load_words()
            if r["word"] not in verbs and not kanji_card_covers(r)]


def word_back(row):
    """Back layout: meaning, reading (unless the word is all kana), then the
    file's note, the radicals and the JLPT level and type in small, faded
    text."""
    esc = html.escape
    parts = [_HEADLINE.format(esc(row["meaning"]))]
    if row["kana"] != row["word"]:
        parts.append(_LINE.format(esc(row["kana"])))
    if row["note"]:
        parts.append(_NOTE.format(esc(row["note"])))
    parts.append(text_radicals_line(row["word"], f"Word {row['word']}"))
    parts.append(parts_lines(_KANJI_CHAR.findall(row["word"])))
    facts = [row["level"].upper()] if row["level"] else []
    parts.append(_NOTE.format(esc(" · ".join(facts + [row["type"]]))))
    return "".join(parts)


def word_note(row):
    """Build an AnkiConnect note dict for one WORD_FILE row."""
    tags = ["word", WORD_TYPE_TAGS.get(row["type"], row["type"].replace(" ", "_"))]
    if row["level"]:
        tags.append(f"jlpt_{row['level']}")
    if _KATAKANA.search(row["word"]):
        tags.append("katakana")
    if row["topic"]:
        tags.append(TOPIC_TAG_PREFIX + row["topic"])
    tags += ref_tags(row["word"], row["level"] and f"jlpt::{row['level']}")
    return {
        "deckName": WORD_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": row["word"], "Back": word_back(row)},
        "tags": tags,
        "options": NOTE_OPTIONS,
    }


def seed_words(dry_run=False, update=True):
    """Seed Nihongo::Words from WORD_FILE (safe to re-run), in file order. A
    word that has a ledger card in Nihongo::Vocab takes it over (keeping its
    review history) instead of adding a second card."""
    rows = seeded_words()
    skipped = len(load_words()) - len(rows)
    notes = [word_note(row) for row in rows]
    adopt = (VOCAB_SCOPE, WORD_DECK, str.strip)

    if dry_run:
        print(f"Would ensure deck {WORD_DECK} and seed {len(notes)} words "
              f"({skipped} skipped: verbs.tsv verbs and words their Core Kanji "
              "card covers).")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, WORD_SCOPE, update=update, adopt=adopt)
        return

    add_or_update_notes(notes, WORD_SCOPE, update=update, adopt=adopt)


# ---------------------------------------------------------------------------
# Numbers & time seed
# ---------------------------------------------------------------------------

NUMBER_GROUPS = ("number", "price", "people", "age", "counter", "clock",
                 "duration", "date", "month", "year", "phrase")


def load_numbers(path=NUMBER_FILE):
    """Rows of NUMBER_FILE as dicts, in file order."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t")
                group, front, kana, meaning, note = (cols + [""] * 5)[:5]
                if group not in NUMBER_GROUPS or not (front and kana and meaning):
                    print(f"{os.path.basename(path)}:{n}: needs a known group, "
                          "a front, a reading and a meaning", file=sys.stderr)
                    sys.exit(1)
                rows.append({"group": group, "front": front, "kana": kana,
                             "meaning": meaning, "note": note})
    except OSError as e:
        print(f"Could not read the numbers list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


def number_back(row):
    """Back layout: the reading as the headline (reading it is the skill),
    the meaning, then the note, the radicals and the group in small, faded
    text."""
    esc = html.escape
    return "".join([_HEADLINE.format(esc(row["kana"])),
                    _LINE.format(esc(row["meaning"])),
                    _NOTE.format(esc(row["note"])) if row["note"] else "",
                    text_radicals_line(row["front"], f"Number {row['front']}"),
                    parts_lines(_KANJI_CHAR.findall(row["front"])),
                    _NOTE.format(esc(row["group"]))])


def number_note(row):
    """Build an AnkiConnect note dict for one NUMBER_FILE row."""
    return {
        "deckName": NUMBER_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": row["front"], "Back": number_back(row)},
        "tags": ["numbers", row["group"]] + ref_tags(row["front"]),
        "options": NOTE_OPTIONS,
    }


def seed_numbers(dry_run=False, update=True):
    """Seed Nihongo::Numbers & Time from NUMBER_FILE (safe to re-run), in file
    order: numbers, prices, people, ages, counters, clock times, durations,
    dates, months and phrases."""
    notes = [number_note(row) for row in load_numbers()]

    if dry_run:
        print(f"Would ensure deck {NUMBER_DECK} and seed {len(notes)} cards.")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, NUMBER_SCOPE, update=update)
        return

    add_or_update_notes(notes, NUMBER_SCOPE, update=update)


# ---------------------------------------------------------------------------
# Sentence seed: Tatoeba sentences made of studied words
# ---------------------------------------------------------------------------

def load_sentences(path=SENTENCE_FILE):
    """Rows of SENTENCE_FILE as dicts, in file order. `words` is a list of
    (front, surface) pairs; surface is "" when the sentence uses the front
    as is."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t")
                if cols[0] == "id":
                    continue
                sid, japanese, english, words, grammar, note = (cols + [""] * 6)[:6]
                if not (sid and japanese and english):
                    print(f"{os.path.basename(path)}:{n}: needs an id, the Japanese "
                          "and the English", file=sys.stderr)
                    sys.exit(1)
                pairs = []
                for w in words.split():
                    front, _, surface = w.partition("{")
                    pairs.append((front, surface.rstrip("}")))
                rows.append({"id": sid, "japanese": japanese, "english": english,
                             "words": pairs, "grammar": grammar.split(), "note": note})
    except OSError as e:
        print(f"Could not read the sentence list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


@functools.cache
def _word_glosses():
    """Front -> (kana, meaning) from words.tsv and verbs.tsv; 勉強する also
    gives 勉強."""
    out = {}
    for r in load_words() + load_verbs():
        out.setdefault(r["word"], (r["kana"], r["meaning"]))
        if r["word"].endswith("する") and len(r["word"]) > 2:
            out.setdefault(r["word"][:-2], (r["kana"][:-2], r["meaning"]))
    return out


def sentence_word_line(front, surface):
    """"行こう → 行く いく · to go" (the arrow only when the sentence changes
    the word's form)."""
    kana, meaning = _word_glosses().get(front, ("", ""))
    head = f"{surface} → {front}" if surface and surface != front else front
    reading = f" {kana}" if kana and kana != front else ""
    return f"{head}{reading}" + (f" · {meaning}" if meaning else "")


def sentence_back(row):
    """Back layout: the English as the headline, one line per word (form
    used, dictionary form, reading, meaning), then the note, the grammar
    words and the Tatoeba attribution in small, faded text."""
    esc = html.escape
    parts = [_HEADLINE.format(esc(row["english"]))]
    parts += [_LINE.format(esc(sentence_word_line(f, s))) for f, s in row["words"]]
    if row["note"]:
        parts.append(_NOTE.format(esc(row["note"])))
    if row["grammar"]:
        parts.append(_NOTE.format(esc("Grammar: " + " ".join(row["grammar"]))))
    jpn_id = row["id"].split("_")[0]
    parts.append(_NOTE.format(esc(f"Tatoeba #{jpn_id} · CC BY 2.0 FR")))
    return "".join(parts)


def sentence_note(row):
    """Build an AnkiConnect note dict for one SENTENCE_FILE row."""
    return {
        "deckName": SENTENCE_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": row["japanese"], "Back": sentence_back(row)},
        "tags": ["sentence"] + ref_tags(row["japanese"], "tatoeba"),
        "options": NOTE_OPTIONS,
    }


def seed_sentences(dry_run=False, update=True):
    """Seed Nihongo::Sentences from SENTENCE_FILE (safe to re-run), in file
    order. tools/add_sentences.py appends the sentences newly readable."""
    notes = [sentence_note(row) for row in load_sentences() if row["note"] != "skip"]

    if dry_run:
        print(f"Would ensure deck {SENTENCE_DECK} and seed {len(notes)} sentences.")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, SENTENCE_SCOPE, update=update)
        return

    add_or_update_notes(notes, SENTENCE_SCOPE, update=update)


# ---------------------------------------------------------------------------
# Kanji look-alikes seed: pairs of studied Core Kanji that look alike
# ---------------------------------------------------------------------------

def load_lookalikes(path=LOOKALIKE_FILE):
    """Rows of LOOKALIKE_FILE as dicts, in file order. Exits on a kanji with
    no Core Kanji row."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t")
                a, b, same, a_only, b_only = (cols + [""] * 5)[:5]
                if a not in core_kanji() or b not in core_kanji():
                    print(f"{os.path.basename(path)}:{n}: {a} or {b} has no Core Kanji "
                          "row (run tools/add_lookalikes.py --write)", file=sys.stderr)
                    sys.exit(1)
                rows.append({"a": a, "b": b, "same": same.split(),
                             "a_only": a_only.split(), "b_only": b_only.split()})
    except OSError as e:
        print(f"Could not read the look-alike list: {e}", file=sys.stderr)
        sys.exit(1)
    return rows


def studied_kanji():
    """Kanji whose Core Kanji card has been studied (isn't new)."""
    _require_anki()
    cards = anki_request("findCards", query=f'{deck_query(KANJI_DECK)} -is:new') or []
    infos = anki_request("cardsInfo", cards=cards) or []
    return {kanji_key(_field(c, "Front")) for c in infos}


def main_readings(row):
    """The bold (*) On and Kun readings of a Core Kanji row, as one line;
    the first reading when none is bold."""
    out = []
    for label, line in (("On", row["on"]), ("Kun", row["kun"])):
        bold = []
        for r in line.split("、") if line else []:
            if not r.startswith("*"):
                break
            bold.append(r.lstrip("*"))
        if bold:
            out.append(f"{label}: <b>{html.escape('、'.join(bold))}</b>")
    if not out:
        first = (row["on"] or row["kun"]).split("、")[0].lstrip("*")
        out.append(html.escape(first))
    return _LINE.format("　".join(out))


_SINGLE_STROKES = {"一", "丨", "ノ", "丶", "亅", "乙", "⺄"}


def _telling_parts(kanji, parts):
    """The parts worth naming in "Differs": single strokes are dropped when
    a bigger part is there too (年's 干 𠂉, not ノ 一), and a kanji isn't
    named as its own part (日 vs 月 is just the kanji)."""
    big = [p for p in parts if p not in _SINGLE_STROKES]
    return [p for p in (big or parts) if p != kanji]


def lookalike_back(row):
    """Back layout: for each kanji, the kanji with its first two meanings,
    its main readings and its radical (faded, shown even when the kanji is
    its own radical); then a faded line with the parts both share and the
    parts that tell them apart."""
    esc = html.escape
    parts = []
    for k in (row["a"], row["b"]):
        kr = core_kanji()[k]
        parts.append(_LINE.format(f'<span style="font-size:1.6em"><b>{esc(k)}</b></span>'
                                  f'　{esc(", ".join(kr["meanings"][:2]))}'))
        parts.append(main_readings(kr))
        parts.append(radicals_lines([(k, kr["radical"])], f"Look-alike {k}"))
        parts.append(parts_line(kr))
    facts = []
    if row["same"]:
        facts.append("Same: " + " ".join(row["same"]))
    if not row["a_only"] and not row["b_only"]:
        facts.append("Same parts, different arrangement")
    else:
        sides = [(k, _telling_parts(k, ps)) for k, ps in
                 ((row["a"], row["a_only"]), (row["b"], row["b_only"]))]
        sides = [(k, ps) for k, ps in sides if ps]
        if len(sides) == 2:
            facts.append("Differs: " + ", ".join(f"{k} has {' '.join(ps)}" for k, ps in sides))
        elif sides:
            facts.append(f"Differs: only {sides[0][0]} has {' '.join(sides[0][1])}")
    if facts:
        parts.append(_NOTE.format(esc(" · ".join(facts))))
    return "".join(parts)


def lookalike_note(row):
    """Build an AnkiConnect note dict for one LOOKALIKE_FILE row."""
    return {
        "deckName": LOOKALIKE_DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": f"{row['a']}・{row['b']}", "Back": lookalike_back(row)},
        "tags": ["lookalike"],
        "options": NOTE_OPTIONS,
    }


def seed_lookalikes(dry_run=False, update=True):
    """Seed Nihongo::Kanji Look-alikes with the LOOKALIKE_FILE pairs whose
    two kanji are both studied on Core Kanji (safe to re-run; each run adds
    the pairs newly studied kanji complete). Needs Anki open, even with
    --dry-run, to know which kanji are studied."""
    studied = studied_kanji()
    rows = load_lookalikes()
    notes = [lookalike_note(r) for r in rows if r["a"] in studied and r["b"] in studied]

    if dry_run:
        print(f"Would ensure deck {LOOKALIKE_DECK} and seed {len(notes)} pairs "
              f"(of {len(rows)}; the rest wait until both kanji are studied).")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, LOOKALIKE_SCOPE, update=update)
        return

    add_or_update_notes(notes, LOOKALIKE_SCOPE, update=update)


# ---------------------------------------------------------------------------
# Study order: words whose kanji you've studied, kanji you've met in words
# ---------------------------------------------------------------------------

READY_TAG = "kanji_ready"       # new Words card whose kanji are all studied
SEEN_TAG = "word_seen"          # new Core Kanji card met in a studied word
NEXT_TAG = "word_next"          # new Core Kanji card the next new words need
NEXT_KANJI = 50                 # how many of those (5 days at 10 new a day)
_KANJI_CHAR = re.compile(r"[\u4e00-\u9fff]")
HELPER_URL = os.getenv("NOTES_TO_ANKI_HELPER_URL", "http://127.0.0.1:8766")
STUDIED_WORD_DECKS = (WORD_DECK, VERB_DECK, NUMBER_DECK)


def helper_request(action, **params):
    """Call the notes-to-anki helper add-on (anki_addon/). Returns its result,
    or None if the add-on isn't installed or Anki is closed."""
    body = json.dumps({"action": action, "params": params}).encode("utf-8")
    req = urllib.request.Request(HELPER_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            reply = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if reply.get("error"):
        print(f"Helper add-on error on {action}: {reply['error']}", file=sys.stderr)
        return None
    return reply.get("result")


def _new_cards(deck):
    cards = anki_request("cardsInfo", cards=anki_request(
        "findCards", query=f'"deck:{deck}" is:new') or []) or []
    return sorted(cards, key=lambda c: c["due"])


# Sentences: Tatoeba (CC BY 2.0 FR) via EDRDG's examples.utf.gz, downloaded by
# tools/readable_sentences.py into tools/cache/ (gitignored). Optional: --order
# skips the sentence step when the file isn't there.
EXAMPLES_FILE = os.path.join(os.path.dirname(WORD_FILE), "tools", "cache", "examples.utf.gz")
UNLOCK_TAG = "unlocks"          # new Words card that makes the most sentences readable
UNLOCK_WORDS = 20               # how many
SENTENCE_GRAMMAR = set("は が を に で と も の へ や か よ ね な".split()) | {
    "から", "まで", "より", "だ", "です", "ですか", "でしょう", "けど", "けれど"}
_KANA_ONLY = re.compile(r"^[\u3041-\u309f\u30a0-\u30ffー]+$")
_B_TOKEN = re.compile(r"^([^(\[{~|]+)(?:\(([^)#][^)]*)\))?")
_B_SURFACE = re.compile(r"\{([^}]+)\}")


def example_sentences(path=EXAMPLES_FILE):
    """Yield (japanese, english, ids, [(headword, reading, surface)]) for each
    indexed Tatoeba sentence (an A line followed by its B line)."""
    import gzip
    with gzip.open(path, "rt", encoding="utf-8") as f:
        a = None
        for line in f:
            if line.startswith("A: "):
                a = line[3:].rstrip("\n")
            elif line.startswith("B: ") and a:
                jpn, _, rest = a.partition("\t")
                eng, _, ids = rest.partition("#ID=")
                words = []
                for tok in line[3:].split():
                    m = _B_TOKEN.match(tok)
                    if m:
                        sm = _B_SURFACE.search(tok)
                        words.append((m.group(1), m.group(2) or "", sm.group(1) if sm else ""))
                yield jpn, eng.strip(), ids, words
                a = None


class WordSet:
    """Words (Fronts and their kana) that a sentence word can match: by
    Front; by kana when the sentence writes it in kana (何処{どこ}); or by
    reading for a kana-only Front (事(こと) matches こと)."""

    def __init__(self, items):
        self.by_front, self.by_kana = {}, {}
        for front, kana in items:
            self.by_front.setdefault(front, front)
            if kana:
                self.by_kana.setdefault(kana, front)
            if _KANA_ONLY.match(front):
                self.by_kana.setdefault(front, front)

    def find(self, word):
        head, reading, surface = word
        if head in self.by_front:
            return head
        for x in (head, surface):
            if x and _KANA_ONLY.match(x) and x in self.by_kana:
                return self.by_kana[x]
        if reading and reading in self.by_front:   # kana-only Front
            return reading
        return None


def studied_words():
    """WordSet of the studied Words and Verbs cards (勉強する also gives 勉強),
    plus the one-kanji words a studied Core Kanji card teaches (私, 彼)."""
    fronts = set()
    for deck in (WORD_DECK, VERB_DECK):
        for n in anki_request("notesInfo", notes=anki_request(
                "findNotes", query=f'{deck_query(deck)} -is:new') or []) or []:
            fronts.add(_field(n, "Front"))
    fronts |= {f[:-2] for f in fronts if f.endswith("する") and len(f) > 2}
    kanji = studied_kanji()
    fronts |= {r["word"] for r in load_words() if r["word"] in kanji and kanji_card_covers(r)}
    kana_of = {r["word"]: r["kana"] for r in load_words() + load_verbs()}
    return WordSet((f, kana_of.get(f, "")) for f in fronts)


def sentence_unlocks(known, candidates):
    """For each candidate Front, how many sentences it alone stands between
    you and (every other word known or SENTENCE_GRAMMAR)."""
    counts = {}
    for _, _, _, words in example_sentences():
        unknown = {w for w in words if w[0] not in SENTENCE_GRAMMAR and not known.find(w)}
        heads = {w[0] for w in unknown}
        if len(heads) == 1:
            front = candidates.find(next(iter(unknown)))
            if front:
                counts[front] = counts.get(front, 0) + 1
    return counts


def _tag_calls(deck, tag, group):
    """The addTags/removeTags calls that leave exactly `group`'s notes in
    `deck` tagged `tag`."""
    want = {c["note"] for c in group}
    tagged = set(anki_request("findNotes", query=f'"deck:{deck}" tag:{tag}') or [])
    add, remove = sorted(want - tagged), sorted(tagged - want)
    print(f"Tag {tag}: add {len(add)}, remove {len(remove)}.")
    calls = []
    if add:
        calls.append(("addTags", {"notes": add, "tags": tag}))
    if remove:
        calls.append(("removeTags", {"notes": remove, "tags": tag}))
    return calls


def _front_load(deck, groups, cards, dry_run):
    """Move groups of new cards to the front of `deck`'s new queue, in the
    order given; `groups` is [(tag, cards)], highest priority first. Each
    group is tagged with its tag (cards that left it are untagged) and keeps
    its cards' existing relative order. The move goes through the helper
    add-on (Anki's own Reposition: no review log entries, undoable); without
    it, the browser opens for a manual one."""
    order = [c["cardId"] for _, group in groups for c in group]
    in_front = [c["cardId"] for c in cards[:len(order)]] == order
    calls = [c for tag, group in groups for c in _tag_calls(deck, tag, group)]
    print("Already at the front." if in_front else "Not at the front yet.")
    if dry_run:
        return
    if anki_multi(calls):
        sys.exit(1)
    if in_front or not order:
        return
    # Each call puts its group first, so the last group goes first.
    for tag, group in reversed(groups):
        if not group:
            continue
        if helper_request("repositionNewCards", cards=[c["cardId"] for c in group],
                          start=0, step=1, shift=True) is None:
            break
    else:
        print(f"Moved {len(order)} card(s) to the front of {deck}.")
        return
    tags = " OR ".join(f"tag:{tag}" for tag, _ in groups)
    anki_request("guiBrowse", query=f'"deck:{deck}" is:new ({tags})',
                 reorderCards={"order": "ascending", "columnId": "cardDue"})
    print("The helper add-on isn't running (see README), so they're open in Anki's\n"
          "browser instead: Select All, then Cards > Reposition: start 0, step 1,\n"
          "randomize off, shift existing cards on.")


def _require_anki():
    if not anki_available():
        print("Anki isn't reachable; open Anki and run again.", file=sys.stderr)
        sys.exit(1)


def order_words(dry_run=False):
    """Put the new Words cards whose kanji all have a studied Core Kanji card
    (kana-only words count as ready) first. (Added 2026-11-11: 71% of the
    studied words used a kanji not yet studied.)"""
    _require_anki()
    known = {kanji_key(_field(n, "Front")) for n in anki_request(
        "notesInfo", notes=anki_request(
            "findNotes", query=f'{deck_query(KANJI_DECK)} -is:new') or [])}
    cards = _new_cards(WORD_DECK)
    ready = [c for c in cards
             if all(k in known for k in _KANJI_CHAR.findall(_field(c, "Front")))]
    unlock = set(unlock_words(cards))
    first = [c for c in ready if _field(c, "Front") in unlock]
    ready = [c for c in ready if _field(c, "Front") not in unlock]
    print(f"Words: {len(known)} kanji studied; {len(first) + len(ready)} new words "
          f"ready (kanji all studied, or kana only), "
          f"{len(cards) - len(first) - len(ready)} waiting.")
    if unlock:
        print(f"  {len(first)} of the {len(unlock)} words that unlock the most "
              f"sentences are ready and go first (the rest wait for a kanji).")
    print("  Next:", " ".join(_field(c, "Front") for c in (first + ready)[:12]))
    _front_load(WORD_DECK, [(UNLOCK_TAG, first), (READY_TAG, ready)], cards, dry_run)


@functools.lru_cache(maxsize=None)
def _unlock_words(fronts):
    if not os.path.exists(EXAMPLES_FILE):
        print("  (No Tatoeba sentences in tools/cache/; run "
              "tools/readable_sentences.py once to order by them.)")
        return ()
    kana_of = {r["word"]: r["kana"] for r in load_words()}
    # New Words cards, and one-kanji words taught by a new Core Kanji card.
    kanji = studied_kanji()
    fronts = set(fronts) | {r["word"] for r in load_words()
                            if r["word"] not in kanji and kanji_card_covers(r)}
    counts = sentence_unlocks(studied_words(), WordSet((f, kana_of.get(f, "")) for f in fronts))
    top = sorted(counts, key=lambda f: -counts[f])[:UNLOCK_WORDS]
    print("  Unlock the most sentences:",
          " ".join(f"{f} ({counts[f]})" for f in top))
    return tuple(top)


def unlock_words(word_cards):
    """The UNLOCK_WORDS words (Fronts) that would each make the most Tatoeba
    sentences readable: new Words cards, and one-kanji words a new Core Kanji
    card teaches (私, 彼). Added 2026-11-14 (user's request). Empty without
    the sentence file."""
    return _unlock_words(tuple(sorted(_field(c, "Front") for c in word_cards)))


def fill_lanes(dry_run=False):
    """Move cards between home decks and their fast lanes (LANES). A new card
    goes to LESSON_DECK if a lesson mentions it (references.tsv; for Core Kanji
    also a kanji inside a mentioned word), else a new N5/N4 kanji to
    BASICS_DECK, else it stays home. A mature card (interval >= MATURE_DAYS)
    goes home; a young one stays where it is. Runs first in --order. Moving
    keeps the note, its format and its review history."""
    _require_anki()
    mentioned = set(references())
    lesson_kanji = {k for f in mentioned for k in _KANJI_CHAR.findall(f)}
    jlpt = {k: r["jlpt"] for k, r in core_kanji().items()}

    def target(home, card):
        front = _field(card, "Front")
        if card["interval"] >= MATURE_DAYS:
            return home
        if card["type"] != 0:            # studied but young: stays put
            return card["deckName"]
        if home == KANJI_DECK:
            k = kanji_key(front)
            if k in mentioned or k in lesson_kanji:
                return LESSON_DECK
            return BASICS_DECK if jlpt.get(k) in BASICS_LEVELS else home
        return LESSON_DECK if front in mentioned else home

    lanes = sorted({lane for ls in LANES.values() for lane in ls})
    calls = [("createDeck", {"deck": d}) for d in lanes]
    moves = {}
    for home in LANES:
        query = deck_query(home) + (f" -{_LINKED}" if home == KANJI_DECK else "")
        cards = anki_request("cardsInfo", cards=anki_request(
            "findCards", query=query) or []) or []
        for c in cards:
            dest = target(home, c)
            if dest != c["deckName"]:
                moves.setdefault((c["deckName"], dest), []).append(c)
    for (src, dest), cs in sorted(moves.items()):
        cs.sort(key=lambda c: c["due"])
        print(f"{src} -> {dest}: {len(cs)} card(s)")
        print("  " + " ".join(_field(c, "Front") for c in cs[:60])
              + (" ..." if len(cs) > 60 else ""))
        calls.append(("changeDeck", {"cards": [c["cardId"] for c in cs], "deck": dest}))
    if not moves:
        print("Fast lanes: nothing to move.")
    if dry_run or not moves:
        return
    if anki_multi(calls):
        sys.exit(1)


def order_kanji(dry_run=False):
    """Put first the new Core Kanji cards whose kanji appear in a studied
    Words, Verbs or Numbers & Time card (tag word_seen; added 2026-11-11), so
    a kanji met in a word is learned next; then the NEXT_KANJI kanji the
    next new Words cards still need, in the order those words come up (tag
    word_next; added 2026-11-12, so kanji outside the frequency top 1,000,
    such as 猫 and 雪, don't wait behind it and hold their words back).
    Before all of them (2026-11-14, tag unlocks): the kanji that the words
    unlocking the most sentences (unlock_words) still need, so those words
    become ready within days."""
    _require_anki()
    seen = set()
    for deck in STUDIED_WORD_DECKS:
        for n in anki_request("notesInfo", notes=anki_request(
                "findNotes", query=f'{deck_query(deck)} -is:new') or []) or []:
            seen.update(_KANJI_CHAR.findall(_field(n, "Front")))
    cards = _new_cards(KANJI_DECK)
    by_kanji = {kanji_key(_field(c, "Front")): c for c in cards}
    new_words = _new_cards(WORD_DECK)
    unlock = set(unlock_words(new_words))
    first = {k for f in unlock for k in _KANJI_CHAR.findall(f) if k in by_kanji}
    unlocking = [c for c in cards if kanji_key(_field(c, "Front")) in first]
    ready = [c for c in cards if kanji_key(_field(c, "Front")) in seen - first]
    needed = []
    for w in new_words:
        for k in _KANJI_CHAR.findall(_field(w, "Front")):
            if k in by_kanji and k not in seen and k not in first and k not in needed:
                needed.append(k)
        if len(needed) >= NEXT_KANJI:
            break
    needed = set(needed[:NEXT_KANJI])
    nxt = [c for c in cards if kanji_key(_field(c, "Front")) in needed]
    print(f"Core Kanji: {len(unlocking)} new kanji the sentence-unlocking words "
          f"need, then {len(ready)} already met in studied words, then "
          f"{len(nxt)} the next new words need.")
    print("  Next:", " ".join(kanji_key(_field(c, "Front"))
                             for c in (unlocking + ready + nxt)[:20]))
    _front_load(KANJI_DECK, [(UNLOCK_TAG, unlocking), (SEEN_TAG, ready),
                             (NEXT_TAG, nxt)], cards, dry_run)


def _alternate(a, b):
    """a[0], b[0], a[1], b[1], ...; the longer list's rest at the end."""
    out = []
    for i in range(max(len(a), len(b))):
        out += a[i:i + 1] + b[i:i + 1]
    return out


ICHIDAN_LEAD = 5                # ichidan verbs first, until this many are studied


def order_verbs(dry_run=False):
    """Reorder the new Verbs cards (added 2026-11-14, user's request): verbs
    whose kanji all have a studied Core Kanji card (or kana-only) first, tag
    kanji_ready; then the rest. Within each part godan and ichidan verbs
    alternate, so a godan verb ending in る (帰る, 走る) is learned next to
    real ichidan ones; irregular verbs (する-verbs) keep their place at the
    end. Each group keeps its book order. Until ICHIDAN_LEAD ichidan verbs
    are studied, the missing ones go first (user's request, 2026-11-14,
    after 60 godan verbs and no ichidan). Needs the helper add-on, version
    2 (setNewOrder)."""
    _require_anki()
    known = studied_kanji()
    cards = _new_cards(VERB_DECK)
    group = {}
    for g in VERB_GROUPS:
        for cid in anki_request("findCards", query=f'"deck:{VERB_DECK}" is:new tag:{g}') or []:
            group[cid] = g

    def ready(c):
        return all(k in known for k in _KANJI_CHAR.findall(_field(c, "Front")))

    def part(cs, g):
        return [c for c in cs if group.get(c["cardId"]) == g]

    first = [c for c in cards if group.get(c["cardId"]) != "irregular" and ready(c)]
    rest = [c for c in cards if group.get(c["cardId"]) != "irregular" and not ready(c)]
    studied = len(anki_request("findCards", query=f'{deck_query(VERB_DECK)} -is:new tag:ichidan') or [])
    ichidan = part(first, "ichidan") + part(rest, "ichidan")
    lead = ichidan[:max(0, ICHIDAN_LEAD - studied)]
    led = {c["cardId"] for c in lead}
    first = [c for c in first if c["cardId"] not in led]
    rest = [c for c in rest if c["cardId"] not in led]
    order = (lead + _alternate(part(first, "godan"), part(first, "ichidan"))
             + _alternate(part(rest, "godan"), part(rest, "ichidan")))
    first = [c for c in order[:len(lead) + len(first)] if ready(c)]
    picked = {c["cardId"] for c in order}
    order += [c for c in cards if c["cardId"] not in picked]  # irregular, untagged
    if lead:
        print(f"Verbs: {studied} ichidan verb(s) studied, so {len(lead)} go first.")
    print(f"Verbs: {len(first)} new verbs ready (kanji all studied, or kana only), "
          f"{len(rest)} waiting, {len(cards) - len(first) - len(rest)} irregular last; "
          f"godan and ichidan alternate.")
    print("  Next:", " ".join(_field(c, "Front") for c in order[:16]))
    calls = _tag_calls(VERB_DECK, READY_TAG, first)
    in_order = [c["cardId"] for c in order] == [c["cardId"] for c in cards]
    print("Already in this order." if in_order else "Not in this order yet.")
    if dry_run:
        return
    if anki_multi(calls):
        sys.exit(1)
    if in_order:
        return
    if (helper_request("version") or 0) < 2:
        print("Verbs not reordered: this needs the helper add-on, version 2. It's\n"
              "installed as a link to anki_addon/, so restarting Anki loads it (on\n"
              "a computer without it, see README).", file=sys.stderr)
        return
    if helper_request("setNewOrder", cards=[c["cardId"] for c in order]) is not None:
        print(f"Reordered {len(order)} new verb(s).")


DEFAULT_ORDER_FILE = os.path.join(os.path.dirname(KANJI_FILE), "default_order.tsv")


def default_order():
    """DEFAULT_ORDER_FILE (tools/default_order.py) as {(deck, front): pos}."""
    pos = {}
    with open(DEFAULT_ORDER_FILE, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or line.startswith("pos\t") or not line.strip():
                continue
            p, _, deck, front = line.rstrip("\n").split("\t")[:4]
            pos[(f"{DECK_ROOT}::{deck}", front)] = int(p)
    return pos


def order_default(dry_run=False):
    """--order for a profile whose user.json says "order": "default" (added
    2026-11-21, the friend's profile): every deck's new cards follow
    default_order.tsv, with no fast lanes and no review-based steps. Cards
    the file doesn't list keep their order, after the listed ones. Needs the
    helper add-on, version 2 (setNewOrder)."""
    _require_anki()
    if not os.path.exists(DEFAULT_ORDER_FILE):
        print("default_order.tsv is missing; run tools/default_order.py --write.",
              file=sys.stderr)
        sys.exit(1)
    pos = default_order()
    helper = helper_request("version") or 0
    for deck in sorted({d for d, _ in pos}):
        cards = _new_cards(deck)
        if not cards:
            continue
        key = kanji_key if deck == KANJI_DECK else (lambda f: f)
        order = sorted(cards, key=lambda c: pos.get((deck, key(_field(c, "Front"))),
                                                    float("inf")))
        listed = sum((deck, key(_field(c, "Front"))) in pos for c in cards)
        same = [c["cardId"] for c in order] == [c["cardId"] for c in cards]
        print(f"{deck}: {len(cards)} new ({len(cards) - listed} not in the file), "
              + ("already in order." if same else "to reorder."))
        print("  Next:", " ".join(_field(c, "Front") for c in order[:16]))
        if dry_run or same:
            continue
        if helper < 2:
            print("  Not reordered: this needs the helper add-on, version 2 (restart "
                  "Anki, or see README).", file=sys.stderr)
            continue
        if helper_request("setNewOrder", cards=[c["cardId"] for c in order]) is not None:
            print(f"  Reordered {len(order)} new card(s).")


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


def format_back(item_type, readings, meaning, kanji_row=None):
    """Render the Back field as HTML: meaning first as a headline, then
    readings, then any side notes in smaller, faded text. A Kanji row whose
    kanji is in KANJI_FILE (`kanji_row`) gets the Core Kanji layout instead,
    keeping its own meaning and side notes but the file's readings."""
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
    if kanji_row:
        notes = [n for n in (readings_note, meaning_note) if n]
        return kanji_back(kanji_row, "".join(parts) or None, notes)
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

    kanji_row = core_kanji().get(kanji_key(item)) if item_type == "Kanji" else None
    back = format_back(item_type, readings, meaning, kanji_row)

    deck = TYPE_DECKS.get(item_type, f"{DECK_ROOT}::{item_type}")
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


# Anki profiles (added 2026-11-21): this Anki holds the user's profile and a
# friend's ("verge", logged into his own AnkiWeb account). AnkiConnect works on
# whichever profile is open, so every run that reaches Anki first opens the
# right one (--profile, else DEFAULT_PROFILE) and switches back at the end.
DEFAULT_PROFILE = os.getenv("NOTES_TO_ANKI_PROFILE", "User 1")
PROFILE_SWITCH_TIMEOUT = 90  # seconds; loadProfile returns before the profile is open
PROFILE_RETRY = 5            # seconds; Anki ignores loadProfile while it's busy (syncing)


def _anki_try(action, **params):
    """One AnkiConnect call that returns None instead of exiting when Anki
    doesn't answer or reports an error (it can pause while a profile loads)."""
    body = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKICONNECT_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return None if result.get("error") else result.get("result")


def switch_profile(name):
    """Open Anki profile `name` and wait until its collection answers.
    Returns the profile that was open before. Exits if the profile doesn't
    exist or doesn't open in time."""
    before = _anki_try("getActiveProfile")
    if before == name:
        return before
    profiles = _anki_try("getProfiles") or []
    if name not in profiles:
        print(f"Anki has no profile named {name!r} (profiles: "
              f"{', '.join(profiles) or 'none found'}).", file=sys.stderr)
        sys.exit(1)
    deadline = time.monotonic() + PROFILE_SWITCH_TIMEOUT
    asked = 0.0
    while time.monotonic() < deadline:
        if _anki_try("getActiveProfile") == name and _anki_try("deckNames") is not None:
            return before
        if time.monotonic() - asked >= PROFILE_RETRY:
            _anki_try("loadProfile", name=name)   # again if Anki was busy and ignored it
            asked = time.monotonic()
        time.sleep(0.5)
    print(f"Anki didn't open profile {name!r} within {PROFILE_SWITCH_TIMEOUT}s; "
          "close any open Anki dialogs and run again.", file=sys.stderr)
    sys.exit(1)


def choose_profile(requested=None):
    """The profile a run uses: `requested`, else DEFAULT_PROFILE when this Anki
    has it, else its only profile. None when AnkiConnect can't list profiles."""
    if requested:
        return requested
    profiles = _anki_try("getProfiles")
    if not profiles:
        return None
    if DEFAULT_PROFILE in profiles:
        return DEFAULT_PROFILE
    if len(profiles) == 1:
        return profiles[0]
    print(f"This Anki has several profiles ({', '.join(profiles)}) and none is "
          f"named {DEFAULT_PROFILE!r}; pass --profile <name> or set "
          "NOTES_TO_ANKI_PROFILE.", file=sys.stderr)
    sys.exit(1)


@contextlib.contextmanager
def anki_profile(requested=None):
    """Run the body with the chosen Anki profile open, then reopen the one
    that was open before. Does nothing when Anki isn't running (dry runs)."""
    if not anki_available():
        if requested:
            print(f"Anki isn't open; using profile {requested!r}'s settings only.",
                  file=sys.stderr)
        use_user(requested or DEFAULT_PROFILE)
        yield None
        return
    target = choose_profile(requested)
    if target:                       # None: AnkiConnect can't tell (keep settings)
        use_user(target)
    before = switch_profile(target) if target else None
    if target and before and before != target:
        print(f"Anki profile: {target} (was {before}; switching back at the end)")
    elif target:
        print(f"Anki profile: {target}")
    try:
        yield target
    finally:
        if target and before and before != target:
            switch_profile(before)


def profile_from_argv(argv):
    """The NAME of a `--profile NAME` in argv (for the tools without argparse)."""
    for i, a in enumerate(argv):
        if a == "--profile" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--profile="):
            return a.split("=", 1)[1]
    return None


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


def plan_changes(notes, scope, update=True, prune=False, adopt=None, keep=()):
    """Work out what syncing `notes` would change in Anki. Read-only.

    Only notes of NOTE_TYPE inside `scope` (an Anki search) are considered.
    An incoming note matches the existing note carrying the same link tag
    (notion_<page id>); failing that, an existing note without a link tag
    and with the same Front. Each existing note is matched at most once.

    update=False: matched notes are left exactly as they are.
    prune=True: linked notes whose row is gone are marked for deletion,
    except those whose link tag is in `keep`.
    adopt=(other scope, deck, key): an incoming note for `deck` that matched
    nothing may take over the note in the other scope whose stripped Front
    equals key(incoming Front) (it's then moved into `deck` and loses its
    link tag, keeping its review history).
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
        adopt_scope, adopt_deck, adopt_key = adopt
        for info in find_notes(adopt_scope):
            adoptable.setdefault(_field(info, "Front").strip(), info)

    matched = []
    for n in unique:
        link = _note_link(n["tags"])
        info = by_link.pop(link, None) if link else None
        if info is None:
            info = by_front.pop(n["fields"]["Front"], None)
        if info is None and n["deckName"] == adopt_deck:
            info = adoptable.pop(adopt_key(n["fields"]["Front"]), None)
        if info is None:
            plan["add"].append(n)
        elif update:
            matched.append((n, info))
        else:
            plan["kept"] += 1

    if prune:
        # Linked notes left over belong to rows that are gone (or now
        # skipped). Unlinked leftovers may be hand-made, so never delete them.
        plan["delete"] = [info for link, info in by_link.items() if link not in keep]
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

        home = (n["deckName"],) + LANES.get(n["deckName"], ())
        stray = [c for c in info.get("cards", [])
                 if deck_of.get(c, n["deckName"]) not in home]
        if stray:
            plan["move"].append((n, info, stray, deck_of[stray[0]]))
            changed = True

        current = {t.lower() for t in info.get("tags", [])}
        wanted = {t.lower() for t in n["tags"]}
        add = [t for t in n["tags"] if t.lower() not in current]
        remove = [t for t in info.get("tags", [])
                  if t.lower() not in wanted
                  and (t.lower() in owned or _LESSON_TAG.fullmatch(t)
                       or t.lower().startswith(TOPIC_TAG_PREFIX)
                       or t.lower().startswith(REF_TAG_PREFIX)
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


def ensure_card_style(dry_run=False):
    """Give NOTE_TYPE the CARD_* templates and styling. Idempotent."""
    templates = anki_request("modelTemplates", modelName=NOTE_TYPE)
    styling = anki_request("modelStyling", modelName=NOTE_TYPE)
    if templates is None or styling is None:
        return
    card = next(iter(templates), "Card 1")
    calls = []
    if templates.get(card) != {"Front": CARD_FRONT, "Back": CARD_BACK}:
        calls.append(("updateModelTemplates", {"model": {
            "name": NOTE_TYPE,
            "templates": {card: {"Front": CARD_FRONT, "Back": CARD_BACK}}}}))
    if styling.get("css") != CARD_CSS:
        calls.append(("updateModelStyling",
                      {"model": {"name": NOTE_TYPE, "css": CARD_CSS}}))
    if not calls:
        return
    verb = "Would update" if dry_run else "Updating"
    print(f"{verb} the '{NOTE_TYPE}' card look (bigger Front, Japanese font).")
    if not dry_run and anki_multi(calls):
        print("Updating the card look failed; see the errors above.",
              file=sys.stderr)


def preview_changes(notes, scope, update=True, prune=False, adopt=None, keep=()):
    """--dry-run: show what a real run would change, if Anki is open."""
    if not anki_available():
        print("\nAnki isn't open, so this preview can't show what would "
              "change in Anki.")
        return
    ensure_card_style(dry_run=True)
    plan = plan_changes(notes, scope, update=update, prune=prune, adopt=adopt,
                        keep=keep)
    print()
    print_plan(plan)
    print(summarize(plan, dry_run=True))


def add_or_update_notes(notes, scope, update=True, prune=False, adopt=None, keep=()):
    """Bring the Anki notes in `scope` in line with `notes` (dicts with
    deckName, modelName, fields, tags, options). See plan_changes for how
    notes are matched and what update/prune/adopt/keep do."""
    ensure_card_style()
    plan = plan_changes(notes, scope, update=update, prune=prune, adopt=adopt,
                        keep=keep)
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

    # Vocab rows for a word that words.tsv or verbs.tsv has are left to that
    # seed, which takes over their card; prune must not delete it meanwhile.
    in_files = ({r["word"] for r in seeded_words()}
                | {v["word"] for v in load_verbs()})
    notes, handed_over = [], set()
    for p in pages:
        reason = skip_reason(p)
        if reason:
            item = get_prop(p["properties"], "Item", "title") or "(untitled)"
            print(f"Skipping {item!r}: {reason}")
            continue
        note = row_to_note(p)
        if "vocab" in note["tags"] and note["fields"]["Front"].strip() in in_files:
            handed_over.add(link_tag(p["id"]))
            continue
        notes.append(note)
    if handed_over:
        print(f"Skipping {len(handed_over)} Vocab rows whose word is in "
              f"{os.path.basename(WORD_FILE)} or {os.path.basename(VERB_FILE)} "
              "(those seeds own their cards).")
    decks = sorted(set(n["deckName"] for n in notes))

    if dry_run:
        print(f"Would ensure {len(decks)} decks: {decks}")
        print(f"Would sync {len(notes)} notes.")
        for n in notes[:5]:
            print(f"\n[{n['deckName']}] {n['fields']['Front']}")
            print(preview_html(n["fields"]["Back"]))
        preview_changes(notes, LEDGER_SCOPE, update=update, prune=prune,
                        adopt=(KANJI_SCOPE, KANJI_DECK, kanji_key), keep=handed_over)
        return

    add_or_update_notes(notes, LEDGER_SCOPE, update=update, prune=prune,
                        adopt=(KANJI_SCOPE, KANJI_DECK, kanji_key), keep=handed_over)


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
             "Nihongo::Kana::Hiragana / Nihongo::Kana::Katakana",
    )
    parser.add_argument(
        "--seed-kanji", action="store_true",
        help="Seed the 1000 most frequent kanji, plus the N5/N4 kanji outside "
             "them, into Nihongo::Core Kanji "
             "(skipping any with a card from the ledger)",
    )
    parser.add_argument(
        "--seed-verbs", action="store_true",
        help="Seed the reviewer book's verbs (verbs.tsv) into Nihongo::Verbs, "
             "in book order",
    )
    parser.add_argument(
        "--seed-words", action="store_true",
        help="Seed the JLPT N5/N4 words (words.tsv) into Nihongo::Words, in "
             "study order",
    )
    parser.add_argument(
        "--seed-numbers", action="store_true",
        help="Seed the number, counter, time and date expressions "
             "(numbers.tsv) into Nihongo::Numbers & Time, in study order",
    )
    parser.add_argument(
        "--seed-lookalikes", action="store_true",
        help="Seed the look-alike kanji pairs (lookalikes.tsv) whose two "
             "kanji are both studied into Nihongo::Kanji Look-alikes",
    )
    parser.add_argument(
        "--seed-sentences", action="store_true",
        help="Seed the Tatoeba example sentences (sentences.tsv) into "
             "Nihongo::Sentences",
    )
    parser.add_argument(
        "--order", action="store_true",
        help="Move new lesson words/verbs to Nihongo::Lessons and new N5/N4 kanji "
             "to Nihongo::Kanji N5-N4 (studied ones back home); then move new "
             "Core Kanji cards met in studied words, then new Words whose kanji "
             "are all studied, to the front of their queues; order new Verbs the "
             "same way, alternating godan and ichidan",
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
    parser.add_argument(
        "--profile", metavar="NAME",
        help=f"Anki profile to work on (default: {DEFAULT_PROFILE!r}, or "
             "NOTES_TO_ANKI_PROFILE); it's opened for the run and the previous "
             "profile reopened afterwards",
    )
    parser.set_defaults(update=True)
    args = parser.parse_args()

    seeds = (args.seed_kana + args.seed_kanji + args.seed_verbs + args.seed_words
             + args.seed_numbers + args.seed_lookalikes + args.seed_sentences
             + args.order)
    if seeds > 1:
        parser.error("--seed-kana, --seed-kanji, --seed-verbs, --seed-words, "
                     "--seed-numbers, --seed-lookalikes, --seed-sentences and --order "
                     "are separate runs")
    if not seeds and not NOTION_SYNC_ENABLED:
        print("The Notion ledger sync is disabled: Notion is outdated and Anki "
              "is the source of truth (see NOTION_SYNC_ENABLED in main.py).\n"
              "Use --seed-kana, --seed-kanji, --seed-verbs, --seed-words, "
              "--seed-numbers, --seed-lookalikes or --seed-sentences.",
              file=sys.stderr)
        sys.exit(1)
    if args.prune and seeds:
        parser.error("--prune only applies to the ledger sync, not the seeds")
    if args.prune and not args.update:
        parser.error("--prune can't be combined with --no-update")

    with anki_profile(args.profile):
        _run(args)


def _run(args):
    if args.seed_kana:
        seed_kana(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_kanji:
        seed_kanji(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_verbs:
        seed_verbs(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_words:
        seed_words(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_numbers:
        seed_numbers(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_lookalikes:
        seed_lookalikes(dry_run=args.dry_run, update=args.update)
        return
    if args.seed_sentences:
        seed_sentences(dry_run=args.dry_run, update=args.update)
        return
    if args.order and USER["order"] == "default":
        order_default(dry_run=args.dry_run)
        return
    if args.order:
        fill_lanes(dry_run=args.dry_run)
        order_kanji(dry_run=args.dry_run)
        order_words(dry_run=args.dry_run)
        order_verbs(dry_run=args.dry_run)
        return

    sync_ledger(dry_run=args.dry_run, update=args.update, prune=args.prune)


if __name__ == "__main__":
    main()