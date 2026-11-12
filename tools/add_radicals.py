"""Set the radical (部首) column of kanji_top1000.tsv and kanji_extra.tsv
and the radicals column of verbs.tsv, and add any radical they use that
radicals.tsv lacks.

verbs.tsv's 9th column lists every kanji in the verb as `kanji:no|form`,
space-separated (手伝う -> `手:64|手 伝:9|亻`); kanji-less verbs get none.

Each kanji gets its classical (Kangxi) radical from KANJIDIC2, written as
`number|form` in column 9, e.g. 海 -> `85|氵`. The form is the shape the
radical takes inside that kanji: KANJIDIC2 only gives the number, so the
positional variants Japanese names separately (氵 さんずい vs 水 みず) come
from KRADFILE, which lists each kanji's visible parts. KRADFILE spells some
parts with a stand-in kanji (it predates Unicode's radical characters):
汁 means 氵, 化 means 亻, 込 means 辶, and so on (VARIANTS below).
Variants that are rare or render badly in common fonts (𠆢, ⺌, ⺮, 飠) are
left out, so those kanji show the radical's main form.

radicals.tsv has one row per (number, form) used, with the Japanese name
and an English meaning. New rows get the Unicode Kangxi radical name as
their meaning and a blank name, to fill in by hand; existing rows are never
changed, since they carry hand edits.

Sources (pinned, downloaded into tools/cache/): KANJIDIC2 and KRADFILE,
(c) EDRDG, CC BY-SA 4.0, via jmdict-simplified (same release as
check_data.py). Radical meanings: Unicode character names (Python's
unicodedata).

Usage:
  python3 tools/add_radicals.py           # list the changes it would make
  python3 tools/add_radicals.py --write   # apply them
Then run `python3 main.py --seed-kanji --dry-run` to see the card changes.
"""

import collections
import json
import sys
import unicodedata
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_data import fetch, SOURCES, JMDICT_TAG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KANJI_FILES = [ROOT / "kanji_top1000.tsv", ROOT / "kanji_extra.tsv"]
RADICAL_FILE = ROOT / "radicals.tsv"
RADICAL_COLUMN = 8  # 0-based: the 9th column
VERB_FILE = ROOT / "verbs.tsv"
VERB_RADICAL_COLUMN = 8  # 0-based: the 9th column

_TAG = JMDICT_TAG.replace("+", "%2B")
_BASE = f"https://github.com/scriptin/jmdict-simplified/releases/download/{_TAG}/"
SOURCES.update({
    "kanjidic2-en.zip": f"{_BASE}kanjidic2-en-{_TAG}.json.zip",
    "kradfile.zip": f"{_BASE}kradfile-{_TAG}.json.zip",
})

# Radical number -> [(form shown on the card, KRADFILE parts that mean it)].
# A kanji whose KRADFILE parts include one of the parts gets that form;
# otherwise it gets the main form (the Kangxi radical itself).
VARIANTS = {
    9: [("亻", {"化"})],
    18: [("刂", {"刈"})],
    61: [("忄", {"忙"})],
    64: [("扌", {"扎"})],
    66: [("攵", {"攵"})],
    85: [("氵", {"汁"})],
    86: [("灬", {"杰"})],
    94: [("犭", {"犯"})],
    96: [("王", {"王"})],
    113: [("礻", {"礼"})],
    122: [("罒", {"買", "罒"})],
    125: [("耂", {"老"})],
    130: [("月", {"月"})],
    140: [("艹", {"艾"})],
    145: [("衤", {"初"})],
    162: [("辶", {"込"})],
    163: [("阝", {"邦"})],
    170: [("阝", {"阡"})],
}
# Main forms where Unicode's Kangxi character isn't the one Japanese uses.
# Unicode's Kangxi radicals are traditional forms (戶 靑 黑 齒 黃); Japanese
# writes 戸 青 黒 歯 黄.
MAIN_FORMS = {63: "戸", 66: "攴", 125: "老", 130: "肉", 140: "艸", 162: "辵", 163: "邑",
              170: "阜", 174: "青", 201: "黄", 203: "黒", 211: "歯"}


def load_json_zip(name):
    with zipfile.ZipFile(fetch(name)) as z:
        member = next(n for n in z.namelist() if n.endswith(".json"))
        return json.loads(z.read(member))


def main_form(no):
    """The ordinary kanji for Kangxi radical `no` (U+2F00 is radical 1)."""
    return MAIN_FORMS.get(no) or unicodedata.normalize("NFKC", chr(0x2F00 + no - 1))


def unicode_meaning(no):
    return unicodedata.name(chr(0x2F00 + no - 1)).removeprefix("KANGXI RADICAL ").lower()


def radical_of(kanji, numbers, parts):
    no = numbers[kanji]
    if kanji == main_form(no):
        return no, kanji
    for form, tokens in VARIANTS.get(no, []):
        if tokens & set(parts.get(kanji, [])):
            return no, form
    return no, main_form(no)


def read_radical_rows():
    rows = []
    if RADICAL_FILE.exists():
        for line in RADICAL_FILE.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                no, form = line.split("\t")[:2]
                rows.append((int(no), form))
    return rows


RADICAL_HEADER = """\
# Radicals (部首) used by the kanji in kanji_top1000.tsv and kanji_extra.tsv.
# One row per form: a radical's positional variants have their own names
#   (水 みず, 氵 さんずい). The kanji files' 9th column points here as `no|form`.
# Columns: no (Kangxi radical number, 1-214), form, name (Japanese, kana),
#   meaning (English), kanji (how many of the 1,017 kanji use this form;
#   set by tools/add_radicals.py, used to order a future radical deck).
# Which radical each kanji has: KANJIDIC2 (classical radical) and KRADFILE
#   (visible parts, which pick the form), (c) EDRDG, CC BY-SA 4.0,
#   https://www.edrdg.org/wiki/index.php/KANJIDIC_Project
# Meanings start from the Unicode Kangxi radical names and are edited by hand;
#   names are written by hand.
"""


def main(argv):
    write = "--write" in argv
    kd = load_json_zip("kanjidic2-en.zip")
    numbers = {c["literal"]: next(r["value"] for r in c["radicals"] if r["type"] == "classical")
               for c in kd["characters"]}
    parts = load_json_zip("kradfile.zip")["kanji"]

    used = collections.Counter()
    for path in KANJI_FILES:
        lines = path.read_text(encoding="utf-8").split("\n")
        changed = 0
        for i, line in enumerate(lines):
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            no, form = radical_of(cols[1], numbers, parts)
            used[(no, form)] += 1
            value = f"{no}|{form}"
            cols += [""] * (RADICAL_COLUMN + 1 - len(cols))
            if cols[RADICAL_COLUMN] != value:
                print(f"{path.name}: {cols[1]} {cols[RADICAL_COLUMN] or '-'} -> {value}")
                cols[RADICAL_COLUMN] = value
                lines[i] = "\t".join(cols)
                changed += 1
        print(f"{path.name}: {changed} line(s) to change")
        if write and changed:
            path.write_text("\n".join(lines), encoding="utf-8")

    # Verb kanji: their forms need a radicals.tsv row too, but they don't
    # count toward the kanji column (which counts the 1,017 kanji).
    verb_used = collections.Counter()
    lines = VERB_FILE.read_text(encoding="utf-8").split("\n")
    changed = 0
    for i, line in enumerate(lines):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        value = []
        for k in cols[2]:
            if k in numbers:
                no, form = radical_of(k, numbers, parts)
                verb_used[(no, form)] += 1
                value.append(f"{k}:{no}|{form}")
        value = " ".join(value)
        cols += [""] * (VERB_RADICAL_COLUMN + 1 - len(cols))
        if cols[VERB_RADICAL_COLUMN] != value:
            print(f"{VERB_FILE.name}: {cols[2]} {cols[VERB_RADICAL_COLUMN] or '-'} -> {value}")
            cols[VERB_RADICAL_COLUMN] = value
            lines[i] = "\t".join(cols)
            changed += 1
    print(f"{VERB_FILE.name}: {changed} line(s) to change")
    if write and changed:
        VERB_FILE.write_text("\n".join(lines), encoding="utf-8")

    existing = read_radical_rows()
    have = set(existing)
    new = sorted(k for k in set(used) | set(verb_used) if k not in have)
    for no, form in new:
        print(f"radicals.tsv: add {no} {form} ({unicode_meaning(no)}, {used[(no, form)]} kanji)")
    print(f"radicals.tsv: {len(new)} row(s) to add; {len(used)} forms used")

    # The kanji count column is derived, so it's refreshed on every row.
    if write:
        text = RADICAL_FILE.read_text(encoding="utf-8") if RADICAL_FILE.exists() else RADICAL_HEADER
        out = []
        for line in text.splitlines():
            if line and not line.startswith("#"):
                cols = line.split("\t")
                cols += [""] * (5 - len(cols))
                cols[4] = str(used.get((int(cols[0]), cols[1]), 0))
                line = "\t".join(cols)
            out.append(line)
        for no, form in new:
            out.append("\t".join([str(no), form, "", unicode_meaning(no), str(used[(no, form)])]))
        RADICAL_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    elif new or any(c for c in used):
        print("Dry run; pass --write to apply.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
