"""Find the Tatoeba sentences you can already read, from your Anki progress.

Read-only: it never writes to Anki or to a .tsv file. It reads which Words and
Verbs cards you've studied (not new) and which Core Kanji cards you've studied,
then checks every sentence of the Tatoeba Japanese-English corpus that has word
indices (~148,000, the "B lines" of EDRDG's examples.utf) against them.

A sentence is readable when every indexed word is a studied word (including
one-kanji words a studied Core Kanji card teaches, 私) or one of the
main.SENTENCE_GRAMMAR words (particles, the copula), which have no card. It's "readable with
kanji" when, in addition, every kanji in it has a studied Core Kanji card.
Sentences with exactly one unknown word are counted too ("one new word"): the
next words worth learning are the ones that unlock the most of them.

The parsing and word matching live in main.py (example_sentences, WordSet,
studied_words), which `--order` also uses to move the words that unlock the
most sentences forward.

Writes the sentences it finds to tools/cache/readable_sentences.tsv (columns:
status, japanese, english, tatoeba ids, unknown word, grammar used) for a
person to pick from; it's a proposal, not a source of truth.

Source: Tatoeba (https://tatoeba.org), CC BY 2.0 FR, via the weekly export
EDRDG publishes as examples.utf.gz (format:
https://www.edrdg.org/wiki/index.php/Sentence-Dictionary_Linking). The export
changes every week and has no versions, so the script pins its SHA-256 and
says when a --refresh downloads a different one (bump EXAMPLES_SHA256 then).
Sentences that end up on cards must keep their Tatoeba ids for attribution.

Usage (Anki must be open):
  python3 tools/readable_sentences.py            # report + write the cache file
  python3 tools/readable_sentences.py --show 30  # also print 30 of each kind
  python3 tools/readable_sentences.py --refresh  # re-download the export
"""

import argparse
import collections
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main  # noqa: E402

CACHE = ROOT / "tools" / "cache"
EXAMPLES = Path(main.EXAMPLES_FILE)
EXAMPLES_URL = "http://ftp.edrdg.org/pub/Nihongo/examples.utf.gz"
EXAMPLES_SHA256 = "309821b4e49a473fe3e667f3885302765d12a0de85391b8e301de8cddde790f3"  # 2026-11-14
OUT = CACHE / "readable_sentences.tsv"

def fetch(refresh):
    if refresh or not EXAMPLES.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {EXAMPLES_URL} ...", file=sys.stderr)
        urllib.request.urlretrieve(EXAMPLES_URL, EXAMPLES)
    digest = hashlib.sha256(EXAMPLES.read_bytes()).hexdigest()
    if digest != EXAMPLES_SHA256:
        print(f"Note: examples.utf.gz is a newer export than the pinned one\n"
              f"  (sha256 {digest}); bump EXAMPLES_SHA256 if you keep it.", file=sys.stderr)


def known(word, words):
    return word[0] in main.SENTENCE_GRAMMAR or words.find(word) is not None


def run(show):
    if not main.anki_available():
        sys.exit("Anki isn't reachable; open Anki and run again.")
    words_known, kanji = main.studied_words(), main.studied_kanji()
    print(f"You know {len(words_known.by_front)} words (studied Words/Verbs cards, "
          f"and words your studied kanji cards teach) and {len(kanji)} kanji.")
    counts = collections.Counter()
    unlocks = collections.Counter()
    rows = []
    for jpn, eng, ids, words in main.example_sentences(EXAMPLES):
        counts["all"] += 1
        unknown = sorted({w[0] for w in words if not known(w, words_known)})
        if len(unknown) > 1 or not words:
            continue
        grammar = " ".join(sorted({w[0] for w in words if w[0] in main.SENTENCE_GRAMMAR}))
        kanji_ok = all(c in kanji for c in main._KANJI_CHAR.findall(jpn))
        if unknown:
            status = "one_new_word"
            unlocks[unknown[0]] += 1
        else:
            status = "readable" if kanji_ok else "readable_words_only"
        counts[status] += 1
        rows.append((status, jpn, eng, ids, "".join(unknown), grammar))

    rows.sort(key=lambda r: (r[0], len(r[1])))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Tatoeba sentences (https://tatoeba.org, CC BY 2.0 FR), "
                "ids are jpn_eng.\nstatus\tjapanese\tenglish\tids\tunknown\tgrammar\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    print(f"Of {counts['all']:,} indexed Tatoeba sentences:")
    print(f"  {counts['readable']:5,} readable: every word and kanji studied")
    print(f"  {counts['readable_words_only']:5,} every word studied, but a kanji isn't yet")
    print(f"  {counts['one_new_word']:5,} one new word away")
    print("Words that would unlock the most sentences:")
    print("  " + "  ".join(f"{w} ({n})" for w, n in unlocks.most_common(20)))
    print(f"Written to {OUT.relative_to(ROOT)}.")
    for status in ("readable", "readable_words_only", "one_new_word"):
        picked = [r for r in rows if r[0] == status][:show]
        if picked:
            print(f"\n{status}:")
            for r in picked:
                extra = f"  [new: {r[4]}]" if r[4] else ""
                print(f"  {r[1]}  —  {r[2]}{extra}")


def cli():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--show", type=int, default=0, help="print N sentences of each kind")
    p.add_argument("--refresh", action="store_true", help="re-download the Tatoeba export")
    p.add_argument("--profile", metavar="NAME", help="Anki profile to read (default: main.DEFAULT_PROFILE)")
    args = p.parse_args()
    fetch(args.refresh)
    with main.anki_profile(args.profile):
        run(args.show)


if __name__ == "__main__":
    cli()
