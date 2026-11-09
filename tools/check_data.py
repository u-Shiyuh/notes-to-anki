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
               A する-verb (勉強する, 世話をする) is looked up by its noun,
               which must be a JMdict noun that takes する (vs).
  numbers.tsv - a number + counter (3本, 何階, 4月) whose JMdict entry (written
               in kanji, 三本) doesn't list the row's reading. Clock times,
               prices and phrases are compositional and aren't in JMdict.

Sources are pinned (see SOURCES) and committed in sources/: the two JLPT
lists as-is, and sources/jmdict-subset.json, the JMdict entries for every word
in the two files. So a normal run needs no network. A word the subset doesn't
cover (a row added since the last refresh) makes the run download the full
JMdict once into tools/cache/ (gitignored) and say to refresh.

Usage:
  python3 tools/check_data.py            # check both files
  python3 tools/check_data.py words      # or just one (words/verbs/numbers)
  python3 tools/check_data.py --refresh  # rebuild sources/ from the pinned
                                         # sources, after editing a .tsv
Exit status is 1 if anything was flagged, so it can gate a commit.
"""

import csv
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / "cache"
SOURCES_DIR = ROOT / "sources"
SUBSET = SOURCES_DIR / "jmdict-subset.json"

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


def source(name):
    """The committed copy in sources/ if there is one, else the cached download."""
    path = SOURCES_DIR / name
    return path if path.exists() else fetch(name)


def load_full_jmdict():
    with zipfile.ZipFile(fetch("jmdict.zip")) as z:
        name = next(n for n in z.namelist() if n.endswith(".json"))
        data = json.loads(z.read(name))
    return data, build_index(data["words"])


def build_index(words):
    index = {}
    for w in words:
        for form in {k["text"] for k in w["kanji"]} | {k["text"] for k in w["kana"]}:
            index.setdefault(form, []).append(w)
    return index


def load_jlpt(level):
    """Every written form in the JLPT list. Entries like "いい; よい",
    "さんぽ (する)" or "スーパー (マーケット)" count under each form."""
    forms = set()
    with open(source(f"{level}.csv"), encoding="utf-8") as f:
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
    for n, r in read_tsv(ROOT / "words.tsv", WORD_COLUMNS):
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


SURU = re.compile(r"(を)?する$")


def suru_noun(word, kana):
    """(noun, noun kana) of a する-verb like 勉強する or 世話をする, else None.
    する itself isn't one."""
    m = SURU.search(word)
    if not m or m.start() == 0:
        return None
    return word[:m.start()], SURU.sub("", kana)


def check_verbs(index):
    flags = []
    for n, r in read_tsv(ROOT / "verbs.tsv", VERB_COLUMNS):
        where = f"verbs.tsv:{n} {r['word']} ({r['kana']})"
        noun = suru_noun(r["word"], r["kana"])
        if noun:
            entry = best_entry(index, noun[0], noun[1], r["meaning"])
            if entry is None:
                flags.append(f"{where}: {noun[0]} not found in JMdict")
            elif not {"vs", "vs-s", "vs-i"} & pos_codes(entry):
                flags.append(f"{where}: JMdict doesn't list {noun[0]} as taking する")
            elif r["group"] != "irregular":
                flags.append(f"{where}: group '{r['group']}', but する-verbs are irregular")
            continue
        entry = best_entry(index, r["word"], r["kana"], r["meaning"])
        if entry is None:
            flags.append(f"{where}: not found in JMdict")
            continue
        groups = {g for c in pos_codes(entry) for rx, g in GROUP_OF if rx.match(c)}
        if r["group"] not in groups:
            flags.append(f"{where}: group '{r['group']}', JMdict says "
                         f"{', '.join(sorted(groups)) or 'not a verb'}")
    return flags


WORD_COLUMNS = ["level", "word", "kana", "meaning", "type", "note", "topic"]
VERB_COLUMNS = ["section", "no", "word", "kana", "meaning", "group", "masu", "note"]


NUMBER_COLUMNS = ["group", "front", "kana", "meaning", "note"]
DIGITS = "〇一二三四五六七八九"


def kanji_number(n):
    """1-99 in kanji numerals: 3 -> 三, 14 -> 十四, 20 -> 二十."""
    n = int(n)
    if n < 10:
        return DIGITS[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else DIGITS[tens]) + "十" + (DIGITS[ones] if ones else "")


def number_forms(front):
    """JMdict spellings of a numbers.tsv front like 3本, 何階 or 6か月, or []
    for fronts that aren't a small number + counter."""
    if not re.fullmatch(r"(\d{1,2}|何)[^\d:]+", front):
        return []
    f = re.sub(r"\d+", lambda m: kanji_number(m.group()), front)
    return [f, f.replace("か月", "ヶ月"), f.replace("か月", "箇月")]


def lookup_keys():
    """The JMdict lookups the checks make."""
    keys = {clean(r["word"]) for _, r in read_tsv(ROOT / "words.tsv", WORD_COLUMNS)}
    for _, r in read_tsv(ROOT / "verbs.tsv", VERB_COLUMNS):
        noun = suru_noun(r["word"], r["kana"])
        keys.add(clean(noun[0] if noun else r["word"]))
    keys |= {f for _, r in read_tsv(ROOT / "numbers.tsv", NUMBER_COLUMNS)
             for f in number_forms(r["front"])}
    return sorted(keys)


def load_jmdict():
    """Index from the committed subset; the full JMdict if the subset is
    missing or doesn't cover every row."""
    if SUBSET.exists():
        subset = json.loads(SUBSET.read_text(encoding="utf-8"))
        missing = set(lookup_keys()) - set(subset["keys"])
        if not missing:
            return build_index(subset["words"])
        print(f"sources/jmdict-subset.json doesn't cover {len(missing)} word(s) "
              f"({', '.join(sorted(missing)[:5])}...); using the full JMdict. "
              "Run with --refresh to update sources/.", file=sys.stderr)
    return load_full_jmdict()[1]


def refresh():
    """Rewrite sources/ from the pinned downloads."""
    SOURCES_DIR.mkdir(exist_ok=True)
    for name in ("n5.csv", "n4.csv"):
        (SOURCES_DIR / name).write_bytes(fetch(name).read_bytes())
    data, index = load_full_jmdict()
    keys = lookup_keys()
    wanted = {id(w) for k in keys for w in index.get(k, [])}
    subset = {
        "source": f"jmdict-simplified {JMDICT_TAG} (jmdict-eng), "
                  "https://github.com/scriptin/jmdict-simplified",
        "license": "CC BY-SA 4.0, (c) Electronic Dictionary Research and Development "
                   "Group (EDRDG), https://www.edrdg.org/edrdg/licence.html",
        "changes": "Only the entries indexed under the words in words.tsv and "
                   "verbs.tsv (see keys); entries otherwise unmodified.",
        "dictDate": data.get("dictDate"),
        "keys": keys,
        "words": [w for w in data["words"] if id(w) in wanted],
    }
    # One entry per line: compact, and a refresh shows up as a readable diff.
    words = subset.pop("words")
    head = json.dumps(subset, ensure_ascii=False, indent=1)[:-2]
    body = ",\n".join(json.dumps(w, ensure_ascii=False, separators=(",", ":"))
                      for w in words)
    SUBSET.write_text(f'{head},\n "words": [\n{body}\n]}}\n', encoding="utf-8")
    subset["words"] = words
    print(f"Wrote sources/: n5.csv, n4.csv, jmdict-subset.json "
          f"({len(subset['words'])} entries for {len(keys)} words).", file=sys.stderr)


def check_numbers(index):
    flags = []
    for n, r in read_tsv(ROOT / "numbers.tsv", NUMBER_COLUMNS):
        for form in number_forms(r["front"]):
            if form in index:
                readings = {k["text"] for w in index[form] for k in w["kana"]}
                if r["kana"].replace(" ", "") not in readings:
                    flags.append(f"numbers.tsv:{n} {r['front']} ({r['kana']}): JMdict reads "
                                 f"{form} as {', '.join(sorted(readings))}")
                break
    return flags


def main(argv):
    if "--refresh" in argv:
        refresh()
        argv = [a for a in argv if a != "--refresh"]
    which = argv or ["words", "verbs", "numbers"]
    index = load_jmdict()
    flags = []
    if "words" in which:
        flags += check_words(index)
    if "verbs" in which:
        flags += check_verbs(index)
    if "numbers" in which:
        flags += check_numbers(index)
    for f in flags:
        print(f)
    print(f"{len(flags)} row(s) flagged.", file=sys.stderr)
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
