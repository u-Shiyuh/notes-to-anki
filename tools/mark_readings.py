"""Choose the bold (*) reading on each line of kanji_top1000.tsv and kanji_extra.tsv.

The `*` marks the reading to learn first; the card shows it bold and first, and
the word seed uses it to skip one-kanji words a kanji card already teaches.

Rule (WaniKani order, via kanji-data's wk_readings_on / wk_readings_kun):
  1. If WaniKani teaches a reading on this line, bold the first one it marks
     primary (no prefix), else the first it accepts (`^` prefix).
  2. If WaniKani teaches none of the on'yomi (all `!`, "not accepted": it
     teaches the kun'yomi for that kanji, e.g. 読 よむ), its on'yomi order is
     arbitrary (読 lists とう before どく). Bold the on'yomi used by the most
     common JMdict words instead (JmdictFurigana says which kana each kanji
     carries), if that's clear: at least 3 words and twice the current one.
     This fixes the bug in the lost original generator, which bolded the
     first-listed reading here (読 トウ, 夏 ゲ).
  3. Kun'yomi WaniKani doesn't accept still follow its order, which matches
     its vocabulary (日 ひ, 人 ひと); word counts mislead there because short
     kun stems match unrelated words (入 い(る) over はい(る)).
  4. No WaniKani data (mostly name kanji): left as is.
A reading already bold that matches the choice is kept, so the file only
changes where the choice changes.

Readings you're learning are bold too (added 2026-11-09): when a line has a
bold reading, any other reading on it that an N5/N4 word in words.tsv or a
verb in verbs.tsv uses (the word is the kanji alone or the kanji plus kana,
e.g. 後 あと, 始まる はじまる) is also marked `*` and moved right after the
main one. The main reading stays first; main.py's kanji_card_covers only
counts that one, so words like 後 あと keep their own Words card. Of
duplicates (お(こす) and おこ(す)), only the first is marked.

WaniKani is proprietary: its reading order reaches this repo only through
kanji-data (MIT). Retained for now (user, 2026-11-06); replace it if a better
openly licensed alternative turns up, and before any paid use.

Sources are pinned and downloaded into tools/cache/ (gitignored).

Usage:
  python3 tools/mark_readings.py           # list the changes it would make
  python3 tools/mark_readings.py --write   # apply them to the .tsv files
Then run `python3 main.py --seed-kanji --dry-run` to see the card changes.
"""

import collections
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_data import fetch as _fetch, SOURCES, CACHE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main as seed  # noqa: E402
FILES = [ROOT / "kanji_top1000.tsv", ROOT / "kanji_extra.tsv"]

KANJI_DATA_COMMIT = "00fd7079c3890f430759536f91aa5e854ec0ca4f"
FURIGANA_TAG = "2.3.1+2026-10-25"
SOURCES.update({
    "kanji-data.json": f"https://raw.githubusercontent.com/davidluzgouveia/kanji-data/{KANJI_DATA_COMMIT}/kanji.json",
    "furigana.txt": ("https://github.com/Doublevil/JmdictFurigana/releases/download/"
                     f"{FURIGANA_TAG.replace('+', '%2B')}/JmdictFurigana.txt"),
})
MIN_WORDS, MIN_RATIO = 3, 2

VOICED = dict(zip("かきくけこさしすせそたちつてとはひふへほ",
                  "がぎぐげござじずぜぞだぢづでどばびぶべぼ"))
HALF_VOICED = dict(zip("はひふへほ", "ぱぴぷぺぽ"))


def hira(text):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def stem(reading):
    """ニチ -> にち, い(く) -> い, -び -> び."""
    return hira(re.sub(r"\(.*|[*\-.]", "", reading))


def sound_variants(s):
    """How a reading can appear inside a word: rendaku (ひ -> び, ぴ) and
    gemination (ニチ -> にっ)."""
    out = {s}
    if s and s[0] in VOICED:
        out.add(VOICED[s[0]] + s[1:])
    if s and s[0] in HALF_VOICED:
        out.add(HALF_VOICED[s[0]] + s[1:])
    for x in list(out):
        if len(x) > 1 and x[-1] in "つちくき":
            out.add(x[:-1] + "っ")
    return out


def word_counts(kanji_lines):
    """For each kanji, how many common JMdict words use each of its on'yomi."""
    with zipfile.ZipFile(_fetch("jmdict.zip")) as z:
        words = json.loads(z.read(next(n for n in z.namelist() if n.endswith(".json"))))["words"]
    common = set()
    for w in words:
        for kf in w["kanji"]:
            if not kf["common"]:
                continue
            for kn in w["kana"]:
                if kn["common"] and (kn["appliesToKanji"] == ["*"] or kf["text"] in kn["appliesToKanji"]):
                    common.add((kf["text"], kn["text"]))
    counts = collections.defaultdict(collections.Counter)
    with open(_fetch("furigana.txt"), encoding="utf-8-sig") as f:
        for line in f:
            text, reading, furi = line.rstrip("\n").split("|")
            if (text, reading) not in common:
                continue
            for part in furi.split(";"):
                idx, kana = part.split(":")
                if "-" in idx:  # a reading over several kanji (今日 きょう)
                    continue
                ch = text[int(idx)]
                for r in kanji_lines.get(ch, []):
                    if kana in sound_variants(stem(r)):
                        counts[ch][r] += 1
                        break
    return counts


def choose(readings, wk, counts, on):
    """The reading to bold, or None to leave the line as is."""
    current = next((r for r in readings if r.startswith("*")), None)
    plain = [r.lstrip("*") for r in readings]
    taught = [x for x in wk if not x.startswith("!")]
    pick = None
    if taught:
        first = next((x for x in taught if not x.startswith("^")), taught[0]).lstrip("^")
        pick = first
    elif wk and on:
        best = max(plain, key=lambda r: counts[r])
        cur = current.lstrip("*") if current else None
        if counts[best] >= MIN_WORDS and counts[best] >= MIN_RATIO * counts.get(cur, 0):
            return best
        return None
    elif wk:
        pick = wk[0].lstrip("!")
    if pick is None:
        return None
    if current and stem(current) == hira(pick):
        return current.lstrip("*")
    return next((r for r in plain if stem(r) == hira(pick)), None)


def learned_words():
    """{kanji: [(word, kana, okurigana)]} for the N5/N4 words in words.tsv and
    the verbs in verbs.tsv that are one kanji, optionally followed by kana."""
    out = collections.defaultdict(list)
    rows = [r for r in seed.load_words() if r["level"] in ("n5", "n4")]
    rows += seed.load_verbs()
    for r in rows:
        word, okuri = r["word"][:1], r["word"][1:]
        if not okuri or re.fullmatch(r"[ぁ-ゖ]+", okuri):
            for kana in r["kana"].split(";"):
                out[word].append((r["word"], kana.strip(), okuri))
    return out


def reads_as(reading, kana, okuri):
    """True if `reading` (い(く), ニチ) spells the word: same kana, and the
    word's own okurigana ends the reading's (答 こたえ matches こた(え))."""
    m = re.fullmatch(r"([^()\-]+)(?:\((.*)\))?", reading.replace(".", ""))
    if not m:  # prefix/suffix forms (-がた, た(ち-))
        return False
    base, ok = m.group(1), m.group(2) or ""
    return hira(base + ok) == hira(kana) and ok.endswith(okuri)


def extras_for(readings, primary, words):
    """Readings besides `primary` that a learned word uses: {reading: word}."""
    out = {}
    plain = [r.lstrip("*") for r in readings]
    for word, kana, okuri in words:
        hit = next((r for r in plain if reads_as(r, kana, okuri)), None)
        if hit and hit != primary and hit not in out:
            out[hit] = f"{word} {kana}"
    return out


def remark(cell, chosen, extras=()):
    """Mark `chosen` and `extras` with *, chosen first, then the extras in
    their current order, then the rest in their current order."""
    rs = [r.lstrip("*") for r in cell.split("、")]
    rs.remove(chosen)
    marked = [r for r in rs if r in extras]
    rest = [r for r in rs if r not in extras]
    return "、".join(["*" + chosen] + ["*" + r for r in marked] + rest)


def main(argv):
    write = "--write" in argv
    kdata = json.loads(_fetch("kanji-data.json").read_text(encoding="utf-8"))
    tables = {}
    for path in FILES:
        tables[path] = path.read_text(encoding="utf-8").split("\n")
    on_lines = {}
    for lines in tables.values():
        for line in lines:
            if line and not line.startswith("#"):
                c = line.split("\t")
                on_lines[c[1]] = [r.lstrip("*") for r in c[5].split("、") if r]
    counts = word_counts(on_lines)
    learned = learned_words()

    changes = []
    for path, lines in tables.items():
        for i, line in enumerate(lines):
            if not line or line.startswith("#"):
                continue
            c = line.split("\t")
            k = c[1]
            for col, key, on in ((5, "wk_readings_on", True), (6, "wk_readings_kun", False)):
                readings = [r for r in c[col].split("、") if r]
                if len(readings) < 2:
                    continue
                wk = (kdata.get(k) or {}).get(key) or []
                chosen = choose(readings, wk, counts[k], on)
                current = next((r.lstrip("*") for r in readings if r.startswith("*")), None)
                label = f"{path.name}: {k} {'on' if on else 'kun'}"
                if chosen and chosen != current:
                    why = (f"{counts[k][chosen]} common words vs {counts[k].get(current, 0)}"
                           if on and not [x for x in wk if not x.startswith("!")]
                           else "WaniKani's first taught reading")
                    changes.append(f"{label}: {current} -> {chosen} ({why})")
                primary = chosen or current
                if not primary:
                    continue
                extras = extras_for(readings, primary, learned.get(k, []))
                old = [r.lstrip("*") for r in readings[1:] if r.startswith("*")]
                for r, word in extras.items():
                    if r not in old:
                        changes.append(f"{label}: also bold {r} (used by {word})")
                for r in old:
                    if r not in extras:
                        changes.append(f"{label}: no longer bold {r}")
                c[col] = remark(c[col], primary, extras)
            lines[i] = "\t".join(c)
    for ch in changes:
        print(ch)
    print(f"{len(changes)} line(s) {'changed' if write else 'would change'}.", file=sys.stderr)
    if write and changes:
        for path, lines in tables.items():
            path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
