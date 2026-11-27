"""Set the parts column (10th) of kanji_top1000.tsv and kanji_extra.tsv:
the components a kanji is visibly built from, space-separated, e.g.
読 -> `言 ~売`, 海 -> `氵 ~毎`, 休 -> `亻 木`. A leading `~` marks the
part KanjiVG says gives the sound (kvg:phon); the card shows its on'yomi.

The parts are KanjiVG's top-level elements: the first named groups under
the kanji (a group without a name, like 読's bottom half inside 売, is
looked into for its named groups). A part KanjiVG splits in two around
another (衣 in 裏) is listed once. Radical-supplement characters become
their ordinary form (⻌ -> 辶, FORMS); a part no common font has (𠂊, ⺍)
is replaced by its own named parts, or left out if it has none. A kanji with fewer than two parts
(日, 人: just strokes, or one element) gets none, so its card shows no line.

The card shows each part with a short meaning, looked up in main.py:
radicals.tsv first, then the part's own Core Kanji row, then parts.tsv.
parts.tsv holds the other parts (宛, 吾, 袁...): this tool appends any
missing one with KANJIDIC2's first meaning (blank if it has none, e.g. マ)
and its main on and kun readings in hiragana (kun: the first one that is a
word on its own, not う.る or -ごと). It only fills blank cells of existing
rows, which may carry hand edits.

Sources (pinned, downloaded into tools/cache/): KanjiVG, (c) Ulrich Apel,
CC BY-SA 3.0, https://github.com/KanjiVG/kanjivg (release KANJIVG_TAG);
KANJIDIC2, (c) EDRDG, CC BY-SA 4.0 (same release as add_radicals.py).

Usage:
  python3 tools/add_parts.py           # list the changes it would make
  python3 tools/add_parts.py --write   # apply them
Then run `python3 main.py --seed-kanji --dry-run` to see the card changes.
"""

import gzip
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_data import fetch, SOURCES  # noqa: E402
from add_radicals import load_json_zip  # noqa: E402  (registers kanjidic2-en.zip)

ROOT = Path(__file__).resolve().parent.parent
KANJI_FILES = [ROOT / "kanji_top1000.tsv", ROOT / "kanji_extra.tsv"]
PARTS_COLUMN = 9  # 0-based: the 10th column
PARTS_FILE = ROOT / "parts.tsv"
PARTS_HEADER = """\
# Meanings of kanji parts that are neither a radical (radicals.tsv) nor a
#   Core Kanji, for the "Parts:" line on Core Kanji cards.
# Columns: part, meaning (short; edit by hand), on, kun (main readings, in
#   hiragana; kun only if one is a word on its own).
# Rows are appended by tools/add_parts.py with KANJIDIC2's first meaning,
#   (c) EDRDG, CC BY-SA 4.0, https://www.edrdg.org/wiki/index.php/KANJIDIC_Project
"""

KANJIVG_TAG = "20260714"  # bump deliberately
SOURCES["kanjivg.xml.gz"] = ("https://github.com/KanjiVG/kanjivg/releases/download/"
                             f"r{KANJIVG_TAG}/kanjivg-{KANJIVG_TAG}.xml.gz")

KVG = "{http://kanjivg.tagaini.net}"

# KanjiVG writes some parts with CJK radical-supplement characters, which
# many fonts lack; show the ordinary form instead. 飠 becomes 食, as on the
# radical line (radicals.tsv has no 飠 row). 2026-11-27: also lookalikes.
FORMS = {"⻌": "辶", "⻖": "阝", "⻏": "阝", "⺨": "犭", "⺤": "爫", "⺕": "彐",
         "⺦": "丬", "⻞": "食", "飠": "食", "⺷": "羊",
         # Shapes no common font has, shown as the katakana they look like
         # (as KRADFILE does): 友's 𠂇 as ナ, 色's 𠂊 as ク; 足's 龰 as 止.
         "𠂇": "ナ", "𠂊": "ク", "龰": "止"}


def radical_forms():
    with open(ROOT / "radicals.tsv", encoding="utf-8") as f:
        return {line.split("\t")[1] for line in f if line.strip() and not line.startswith("#")}


def shown(part, extra):
    """Whether a card can show `part`: a radicals.tsv form, a kanji in the
    kanji files, katakana, or a JIS X 0208 character (which every Japanese
    font has). Rare ones (𠂊, 㑒, ⺍, KanjiVG's CDP-xxxx stand-ins) aren't."""
    if part in extra or (len(part) == 1 and "\u30a0" <= part <= "\u30ff"):
        return True
    try:
        part.encode("cp932")
        return len(part) == 1
    except UnicodeEncodeError:
        return False


def named_parts(group, extra):
    """The named groups directly under `group`, looking through unnamed ones
    and ones a card can't show (their own named parts are used instead).
    A part found that way is listed once (検: 木 人 一 口), unless that leaves
    one part: 品 is 口 口 口, 三 is 一 一 一 (2026-11-27)."""
    once = _named(group, extra, True)
    return once if len(once) >= 2 else _named(group, extra, False)


def _named(group, extra, once):
    out = []
    for child in group.findall("g"):
        name = child.get(KVG + "element")
        name = FORMS.get(name, name)
        if name and shown(name, extra):
            name = ("~" if child.get(KVG + "phon") else "") + name
            # A part split around another (kvg:part 1, 2) is listed once.
            if not (child.get(KVG + "part")
                    and name.lstrip("~") in {o.lstrip("~") for o in out}):
                out.append(name)
        else:
            bare = {o.lstrip("~") for o in out}
            out += [p for p in _named(child, extra, once)
                    if not once or p.lstrip("~") not in bare]
    return out


def load_parts(extra):
    """Kanji -> its top-level parts, from KanjiVG."""
    with gzip.open(fetch("kanjivg.xml.gz")) as f:
        root = ET.parse(f).getroot()
    out = {}
    for kanji in root.findall("kanji"):
        top = kanji.find("g")
        name = top.get(KVG + "element") if top is not None else None
        if name and "-" not in kanji.get("id", ""):  # skip variant drawings
            parts = [p for p in named_parts(top, extra) if p.lstrip("~") != name]
            out[name] = parts if len(parts) >= 2 else []
    return out


def first_meaning(char):
    """KANJIDIC2's first English meaning of a character entry, or ""."""
    for group in ((char or {}).get("readingMeaning") or {}).get("groups", []):
        for m in group.get("meanings", []):
            if m.get("lang") == "en":  # "short thread radical (no. 52)" -> "short thread"
                return re.sub(r"\s*radical \(no\.? ?\d+\)$", "", m["value"])
    return ""


def _readings(char, kind):
    return [r["value"] for g in ((char or {}).get("readingMeaning") or {}).get("groups", [])
            for r in g.get("readings", []) if r["type"] == kind]


def hiragana(text):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def main_on(char):
    """KANJIDIC2's first on reading, in hiragana, or ""."""
    return next((hiragana(r) for r in _readings(char, "ja_on")), "")


def main_kun(char):
    """KANJIDIC2's first kun reading that is a word on its own, or ""."""
    return next((r for r in _readings(char, "ja_kun") if "." not in r and "-" not in r), "")


def main(argv):
    write = "--write" in argv
    kanji = {line.split("\t")[1] for path in KANJI_FILES
             for line in path.read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#")}
    parts = load_parts(radical_forms() | kanji)
    missing = []
    for path in KANJI_FILES:
        lines = path.read_text(encoding="utf-8").split("\n")
        changed = 0
        for i, line in enumerate(lines):
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if cols[1] not in parts:
                missing.append(cols[1])
            value = " ".join(parts.get(cols[1], []))
            cols += [""] * (PARTS_COLUMN + 1 - len(cols))
            if cols[PARTS_COLUMN] != value:
                print(f"{path.name}: {cols[1]} {cols[PARTS_COLUMN] or '-'} -> {value or '-'}")
                cols[PARTS_COLUMN] = value
                lines[i] = "\t".join(cols)
                changed += 1
        print(f"{path.name}: {changed} line(s) to change")
        if write and changed:
            path.write_text("\n".join(lines), encoding="utf-8")
    if missing:
        print(f"Not in KanjiVG (no parts): {' '.join(missing)}")

    # Parts the card can't name from radicals.tsv or a Core Kanji row.
    known = radical_forms() | kanji
    rows = {}  # part -> [part, meaning, on, kun]
    header = PARTS_HEADER
    if PARTS_FILE.exists():
        text = PARTS_FILE.read_text(encoding="utf-8")
        header = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
        for line in text.splitlines():
            if line and not line.startswith("#"):
                cols = line.split("\t") + [""] * 3
                rows[cols[0]] = cols[:4]
    for path in KANJI_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                for part in parts.get(line.split("\t")[1], []):
                    part = part.lstrip("~")
                    if part not in known and part not in rows:
                        rows[part] = [part, None, "", ""]
    kd = {c["literal"]: c for c in load_json_zip("kanjidic2-en.zip")["characters"]}
    changed = 0
    for part, cols in rows.items():
        new = [part, first_meaning(kd.get(part)) if cols[1] is None else cols[1],
               cols[2] or main_on(kd.get(part)), cols[3] or main_kun(kd.get(part))]
        if new != cols:
            print(f"parts.tsv: {part} {' / '.join(c or '-' for c in new[1:])}")
            rows[part] = new
            changed += 1
    print(f"parts.tsv: {changed} row(s) to add or fill")
    if write and changed:
        PARTS_FILE.write_text(header + "".join("\t".join(r) + "\n" for r in rows.values()),
                              encoding="utf-8")
    if not write:
        print("Dry run; pass --write to apply.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
