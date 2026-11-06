"""Check words.tsv and verbs.tsv against the sources they were built from.

Read-only: it never edits a .tsv file. It prints rows that look wrong so a
person can fix them by hand (the .tsv files are the source of truth; they carry
hand edits no generator reproduces).

Checks:
  words.tsv  - the row's `type` agrees with JMdict's part of speech for the
               entry that best matches the row (catches はく labelled "noun");
             - a verb (by JMdict) whose type doesn't say so;
             - a levelled row (n5/n4) that isn't in that JLPT list.
  verbs.tsv  - the row's `group` (godan/ichidan/irregular) agrees with JMdict.

Sources are pinned (see SOURCES) and downloaded once into tools/cache/
(gitignored). Delete the cache to re-download.

Usage:
  python3 tools/check_data.py            # check both files
  python3 tools/check_data.py words      # or just one
Exit status is 1 if anything was flagged, so it can gate a commit.
"""

import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / "cache"

# Bump these deliberately; a moving source would make the check drift.
JLPT_COMMIT = "1ad66734417aca9dbcca6b2d5ee440cb13ab3ba0"  # open-anki-jlpt-decks
JMDICT_TAG = "3.6.2+20261102210542"                       # jmdict-simplified
SOURCES = {
    "n5.csv": f"https://raw.githubusercontent.com/jamsinclair/open-anki-jlpt-decks/{JLPT_COMMIT}/src/n5.csv",
    "n4.csv": f"https://raw.githubusercontent.com/jamsinclair/open-anki-jlpt-decks/{JLPT_COMMIT}/src/n4.csv",
    "jmdict.zip": ("https://github.com/scriptin/jmdict-simplified/releases/download/"
                   f"{JMDICT_TAG.replace('+', '%2B')}/jmdict-eng-{JMDICT_TAG.replace('+', '%2B')}.json.zip"),
}

# JMdict part-of-speech codes -> the `type` labels words.tsv uses.
VERB_POS = re.compile(r"^(v1|v5|vk|vz|vs-i|vs-s)")
POS_LABELS = [
    (re.compile(r"^adj-ix?$"), "い-adjective"),
    (re.compile(r"^adj-na$"), "な-adjective"),
    (re.compile(r"^adj-pn$"), "pre-noun word"),
    (re.compile(r"^adv"), "adverb"),
    (re.compile(r"^conj$"), "conjunction"),
    (re.compile(r"^ctr$"), "counter"),
    (re.compile(r"^exp$"), "expression"),
    (re.compile(r"^int$"), "interjection"),
    (re.compile(r"^num$"), "number"),
    (re.compile(r"^pref$"), "prefix"),
    (re.compile(r"^pn$"), "pronoun"),
    (re.compile(r"^(suf|n-suf|aux)"), "suffix"),
    (re.compile(r"^vs$"), "noun (+する)"),
    (re.compile(r"^(vs-i|vs-s)$"), "する-verb"),
    (re.compile(r"^n(-adv|-t|-pref)?$"), "noun"),
]
# Labels that are judgement calls the source data can't settle; never flagged.
UNCHECKED_TYPES = {"expression", "noun (grammar)", "suffix", "number", "counter"}


def fetch(name):
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {name}...", file=sys.stderr)
        with urllib.request.urlopen(SOURCES[name]) as r:
            path.write_bytes(r.read())
    return path


def load_jmdict():
    with zipfile.ZipFile(fetch("jmdict.zip")) as z:
        name = next(n for n in z.namelist() if n.endswith(".json"))
        words = json.loads(z.read(name))["words"]
    index = {}
    for w in words:
        for form in {k["text"] for k in w["kanji"]} | {k["text"] for k in w["kana"]}:
            index.setdefault(form, []).append(w)
    return index


def load_jlpt(level):
    """Every written form in the JLPT list. Entries like "いい; よい",
    "さんぽ (する)" or "スーパー (マーケット)" count under each form."""
    forms = set()
    with open(fetch(f"{level}.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for text in (r["expression"], r["reading"]):
                for form in text.split(";"):
                    forms.add(clean(re.sub(r"する$", "", clean(form))))
    return forms


def read_tsv(path, columns):
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#") or not line.strip():
            continue
        cols = (line.split("\t") + [""] * len(columns))[:len(columns)]
        rows.append((n, dict(zip(columns, cols))))
    return rows


def clean(text):
    """Strip the ～ / (て) decoration words.tsv puts on affixes."""
    return re.sub(r"[～~]|\(.*?\)|\s", "", text)


def words_of(text):
    return set(re.findall(r"[a-z]+", text.lower())) - {"to", "a", "an", "the", "of", "e", "g"}


KANA_ONLY = re.compile(r"^[ぁ-ゟァ-ヿー]+$")


RARE_KANJI = {"rK", "iK", "oK", "sK", "ateji"}


def usually_kana(entry):
    """Written in kana: no kanji form, marked "usually kana", or only rare
    kanji forms (嗚呼 for ああ)."""
    return (not entry["kanji"]
            or any("uk" in s.get("misc", []) for s in entry["sense"])
            or all(set(k.get("tags", [])) & RARE_KANJI for k in entry["kanji"]))


def best_entry(index, word, kana, meaning):
    """The JMdict entry for this row: same written form and reading, the one
    whose glosses share the most words with the row's meaning. A word written
    in kana only prefers entries usually written in kana: the reading alone
    also matches unrelated kanji words (はく is 履く, 箔 and 伯), which is how
    the original generator mislabelled several rows."""
    word, kana = clean(word), clean(kana)
    cands = [w for w in index.get(word, [])
             if kana in {k["text"] for k in w["kana"]}] or index.get(word, [])
    if not cands:
        return None
    want = words_of(meaning)
    kana_only = bool(KANA_ONLY.match(word))

    def score(w):
        glosses = " ".join(g["text"] for s in w["sense"] for g in s["gloss"])
        common = any(k.get("common") for k in w["kana"] + w["kanji"])
        return (len(want & words_of(glosses)), kana_only and usually_kana(w), common)
    return max(cands, key=score)


def pos_codes(entry):
    return {p for s in entry["sense"] for p in s["partOfSpeech"]}


def labels(codes):
    return {label for code in codes for rx, label in POS_LABELS if rx.match(code)}


def check_words(index):
    lists = {lvl: load_jlpt(lvl) for lvl in ("n5", "n4")}
    flags = []
    for n, r in read_tsv(ROOT / "words.tsv", ["level", "word", "kana", "meaning", "type", "note"]):
        where = f"words.tsv:{n} {r['word']} ({r['kana']})"
        forms = {re.sub(r"する$", "", clean(f)) for f in re.split(r"/|;", r["word"])}
        if r["level"] in lists and not forms & lists[r["level"]]:
            flags.append(f"{where}: not in the JLPT {r['level'].upper()} list")
        if r["type"] in UNCHECKED_TYPES:
            continue
        entry = best_entry(index, r["word"], r["kana"], r["meaning"])
        if entry is None:
            continue
        codes = pos_codes(entry)
        is_verb = any(VERB_POS.match(c) for c in codes) and not labels(codes) - {"する-verb"}
        if is_verb and "verb" not in r["type"]:
            flags.append(f"{where}: type '{r['type']}', but JMdict has only a verb "
                         f"({', '.join(sorted(codes))}); verbs belong in verbs.tsv "
                         "or need a verb type")
        elif not is_verb and r["type"] and r["type"] not in labels(codes) | {"verb"} \
                and not (r["type"] == "noun" and labels(codes) & {"suffix", "noun (+する)"}):
            flags.append(f"{where}: type '{r['type']}', JMdict says "
                         f"{', '.join(sorted(labels(codes))) or ', '.join(sorted(codes))}")
    return flags


GROUP_OF = [(re.compile(r"^v5"), "godan"), (re.compile(r"^v1"), "ichidan"),
            (re.compile(r"^(vk|vs-i|vs-s|vz)"), "irregular")]


def check_verbs(index):
    flags = []
    cols = ["section", "no", "word", "kana", "meaning", "group", "masu", "note"]
    for n, r in read_tsv(ROOT / "verbs.tsv", cols):
        entry = best_entry(index, r["word"], r["kana"], r["meaning"])
        where = f"verbs.tsv:{n} {r['word']} ({r['kana']})"
        if entry is None:
            flags.append(f"{where}: not found in JMdict")
            continue
        groups = {g for c in pos_codes(entry) for rx, g in GROUP_OF if rx.match(c)}
        if r["group"] not in groups:
            flags.append(f"{where}: group '{r['group']}', JMdict says "
                         f"{', '.join(sorted(groups)) or 'not a verb'}")
    return flags


def main(argv):
    which = argv or ["words", "verbs"]
    index = load_jmdict()
    flags = []
    if "words" in which:
        flags += check_words(index)
    if "verbs" in which:
        flags += check_verbs(index)
    for f in flags:
        print(f)
    print(f"{len(flags)} row(s) flagged.", file=sys.stderr)
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
