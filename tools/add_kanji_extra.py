"""Add a kanji_extra.tsv row for every kanji a card word uses that has no Core
Kanji row yet.

Added 2026-11-12 (user's request). 180 kanji in words.tsv, verbs.tsv and
numbers.tsv (猫 机 雪 傘 晴 ...) had no Core Kanji card: they're outside the
newspaper top 1,000 and the JLPT N5/N4 kanji list, so `--order` could never
call the words that use them "ready". This writes their rows in the same
format as the rest of kanji_extra.tsv, then keeps the file's data rows sorted
by frequency rank (kanji with no rank last). Existing rows are never changed.

Afterwards, run (each previews without --write):
  python3 tools/add_radicals.py --write     # fills the radical column
  python3 tools/mark_readings.py --write    # bold readings, learned words
  python3 tools/dedupe_readings.py --write  # うし(ろ) vs うしろ
and fill any blank radical name it added to radicals.tsv by hand.

How each column is built (same sources as the file header lists):
  rank, strokes, jlpt (new levels), meanings (first 4; KANJIDIC2's English
    meanings, which keep capitals only for names like Japan): kanji-data /
    KANJIDIC2.
  on'yomi in katakana, kun'yomi with okurigana as あ(かり); prefix/suffix
    forms (-び) go after the others. The first reading WaniKani lists is
    marked * and moved first (mark_readings.py then refines it).
  example: the easiest JLPT word (N5 first, ... N1) that reads this kanji
    with one of its on'yomi (JmdictFurigana says which kana it carries), the
    main on'yomi winning ties, then list order; else a common JMdict word of
    2-3 kanji, preferring words whose kanji all have a Core Kanji row, then
    the main on'yomi, then shorter words, then JMdict order. JMdict has no
    frequency ranks, so this fallback can't be "most frequent". Blank if no
    on'yomi word exists (e.g. 込, a Japanese-made kanji).

Usage:
  python3 tools/add_kanji_extra.py           # list the rows it would add
  python3 tools/add_kanji_extra.py --write   # add them
"""

import csv
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_data import fetch, SOURCES, JLPT_COMMIT  # noqa: E402
import add_radicals  # noqa: E402,F401  (registers kanjidic2-en.zip)
import mark_readings  # noqa: E402,F401  (registers kanji-data.json, furigana.txt)
from mark_readings import hira, stem, sound_variants  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOP = ROOT / "kanji_top1000.tsv"
EXTRA = ROOT / "kanji_extra.tsv"
WORD_FILES = [(ROOT / "words.tsv", 1), (ROOT / "verbs.tsv", 2), (ROOT / "numbers.tsv", 1)]
LEVELS = ["n5", "n4", "n3", "n2", "n1"]
for _lv in LEVELS:
    SOURCES.setdefault(f"{_lv}.csv", "https://raw.githubusercontent.com/jamsinclair/"
                       f"open-anki-jlpt-decks/{JLPT_COMMIT}/src/{_lv}.csv")
KANJI = re.compile(r"[一-鿿々]")
ONLY_KANJI = re.compile(r"^[一-鿿]{2,3}$")


def data_rows(path):
    return [l.split("\t") for l in path.read_text(encoding="utf-8").split("\n")
            if l and not l.startswith("#")]


def missing_kanji(have):
    """Kanji the card words use with no row, in first-use order."""
    out = {}
    for path, col in WORD_FILES:
        for c in data_rows(path):
            for k in KANJI.findall(c[col]):
                if k not in have and k != "々":
                    out.setdefault(k, c[col])
    return out


def kata(text):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


def affix_last(readings):
    return [r for r in readings if not r.startswith("-") and not r.endswith("-")] + \
           [r for r in readings if r.startswith("-") or r.endswith("-")]


def mark_first(readings, wk):
    """Star the first reading WaniKani lists (stems: うし matches うし(ろ))."""
    for w in wk:
        w = w.lstrip("!^")
        hit = next((r for r in readings if stem(r) == hira(w)), None)
        if hit:
            readings.remove(hit)
            return ["*" + hit] + readings
    return readings


def gloss(meaning):
    """The first item of a comma/semicolon list, ignoring commas in brackets."""
    depth, out = 0, ""
    for ch in meaning:
        depth += ch in "([" and 1 or ch in ")]" and -1 or 0
        if ch in ",;" and depth == 0:
            break
        out += ch
    return out.strip()


def load_furigana():
    furi = {}
    with open(fetch("furigana.txt"), encoding="utf-8-sig") as f:
        for line in f:
            text, reading, parts = line.rstrip("\n").split("|")
            segs = {}
            for p in parts.split(";"):
                idx, kana = p.split(":")
                if "-" not in idx:
                    segs[int(idx)] = kana
            furi[(text, reading)] = segs
    return furi


def on_used(text, reading, k, ons, furi):
    """The on'yomi `k` has in this word, or None."""
    segs = furi.get((text, reading))
    if not segs:
        return None
    for i, ch in enumerate(text):
        if ch == k and i in segs:
            for r in ons:
                if segs[i] in sound_variants(stem(r)):
                    return r
    return None


def jlpt_words():
    out = []
    for n, lv in enumerate(LEVELS):
        with open(fetch(f"{lv}.csv"), encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f)):
                for text in r["expression"].split(";"):
                    for kana in r["reading"].split(";"):
                        out.append((n, i, text.strip(), kana.strip(), gloss(r["meaning"]), lv.upper()))
    return out


def common_words():
    with zipfile.ZipFile(fetch("jmdict.zip")) as z:
        words = json.loads(z.read(next(n for n in z.namelist() if n.endswith(".json"))))["words"]
    out = []
    for i, w in enumerate(words):
        for kf in w["kanji"]:
            if not kf["common"] or not ONLY_KANJI.match(kf["text"]):
                continue
            for kn in w["kana"]:
                if kn["common"] and (kn["appliesToKanji"] == ["*"] or kf["text"] in kn["appliesToKanji"]):
                    g = w["sense"][0]["gloss"][0]["text"] if w["sense"] and w["sense"][0]["gloss"] else ""
                    out.append((i, kf["text"], kn["text"], g))
                    break
    return out


def example(k, ons, furi, jlpt, common, have):
    main = ons[0].lstrip("*") if ons else None
    plain = [r.lstrip("*") for r in ons]
    best = None
    for n, i, text, kana, g, lv in jlpt:
        if k not in text or not KANJI.search(text):
            continue
        r = on_used(text, kana, k, plain, furi)
        if r:
            key = (n, r != main, i)
            if best is None or key < best[0]:
                best = (key, f"{text}|{kana}|{g}|{lv}")
    if best:
        return best[1]
    for i, text, kana, g in common:
        if k not in text:
            continue
        r = on_used(text, kana, k, plain, furi)
        if r:
            known = all(c in have or c == k for c in text)
            key = (not known, r != main, len(text), i)
            if best is None or key < best[0]:
                best = (key, f"{text}|{kana}|{g}|")
    return best[1] if best else ""


def main(argv):
    write = "--write" in argv
    top, extra = data_rows(TOP), data_rows(EXTRA)
    have = {c[1] for c in top + extra}
    todo = missing_kanji(have)
    if not todo:
        print("Nothing to add.", file=sys.stderr)
        return
    kdata = json.loads(fetch("kanji-data.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(fetch("kanjidic2-en.zip")) as z:
        kd = {c["literal"]: c for c in json.loads(
            z.read(next(n for n in z.namelist() if n.endswith(".json"))))["characters"]}
    furi, jlpt, common = load_furigana(), jlpt_words(), common_words()
    allk = have | set(todo)

    rows = []
    for k, word in todo.items():
        d, c = kdata.get(k) or {}, kd[k]
        rm = (c.get("readingMeaning") or {}).get("groups") or [{}]
        meanings = [m["value"] for g in rm for m in g.get("meanings", []) if m["lang"] == "en"][:4]
        ons = [kata(r.replace(".", "")) for r in d.get("readings_on", [])]
        kuns = [r.replace(".", "(") + ")" if "." in r else r for r in d.get("readings_kun", [])]
        ons = mark_first(affix_last(ons), d.get("wk_readings_on") or [])
        kuns = mark_first(affix_last(kuns), d.get("wk_readings_kun") or [])
        rank = d.get("freq") or c["misc"].get("frequency") or ""
        rows.append([str(rank), k, str(c["misc"]["strokeCounts"][0]),
                     str(d.get("jlpt_new") or ""), "; ".join(meanings),
                     "、".join(ons), "、".join(kuns),
                     example(k, ons, furi, jlpt, common, allk), ""])
        print(f"{k} (from {word})\t" + "\t".join(rows[-1][4:8]))
    print(f"{len(rows)} row(s) {'added' if write else 'would be added'}.", file=sys.stderr)
    if not write:
        return
    lines = EXTRA.read_text(encoding="utf-8").split("\n")
    header = [l for l in lines if l.startswith("#")]
    body = extra + rows
    body.sort(key=lambda c: (not c[0], int(c[0]) if c[0] else 0))
    EXTRA.write_text("\n".join(header + ["\t".join(c) for c in body]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
