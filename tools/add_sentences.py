"""Propose Tatoeba sentences for sentences.tsv: ones you can read already.

Picks the indexed Tatoeba sentences (see tools/readable_sentences.py) whose
every word is a studied Words/Verbs card (or a word a studied Core Kanji card
teaches, or a particle/copula in main.SENTENCE_GRAMMAR) and whose every kanji
has a studied Core Kanji card. Then it filters:

  - length: MIN_LEN to MAX_LEN characters;
  - near-duplicates: a sentence that differs from an already picked (or
    already listed) one by a single word is skipped (私は医者です after
    私は学生です), so the deck isn't a drill of one template;
  - already in sentences.tsv (by Tatoeba id or by text), so rerunning only
    adds sentences newly readable.

There's no content filter (user's choice, 2026-11-14): Tatoeba's crude or
violent lines (死ね！ "Die!") are real Japanese too.

It proposes up to --max of them, shortest first. Dry run by default; --write
appends them to sentences.tsv (creating it with its header), never rewriting
existing rows: the file is the source of truth, so edit rows by hand. To drop
a sentence, put "skip" in its note column rather than deleting the row (a
deleted row would be proposed again); main.py leaves skip rows off the deck.

Columns: id (Tatoeba jpn_eng ids), japanese, english, words (front or
front{form used}, space-separated), grammar (particles/copula used), note.

Needs Anki open (to read what you've studied) and tools/cache/examples.utf.gz
(run tools/readable_sentences.py once to download it).

Usage:
  python3 tools/add_sentences.py               # show what would be added
  python3 tools/add_sentences.py --write       # append them
  python3 tools/add_sentences.py --max 100     # propose up to 100 (default 40)
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main  # noqa: E402

MIN_LEN, MAX_LEN = 5, 30
HEADER = """\
# Example sentences for Nihongo::Sentences (python main.py --seed-sentences).
# From Tatoeba (https://tatoeba.org), CC BY 2.0 FR; the id column holds each
# pair's Tatoeba sentence ids (Japanese_English), shown on the card for
# attribution. Word indices via EDRDG's examples.utf. Rows are proposed by
# tools/add_sentences.py (only sentences readable with studied cards) and
# edited by hand; put "skip" in the note column to keep a row off the deck.
id\tjapanese\tenglish\twords\tgrammar\tnote
"""


def skeletons(heads):
    """The word sequence with each position in turn replaced by a wildcard."""
    return {tuple(heads[:i]) + ("*",) + tuple(heads[i + 1:]) for i in range(len(heads))}


def proposals(limit):
    if not os.path.exists(main.EXAMPLES_FILE):
        sys.exit("No tools/cache/examples.utf.gz; run tools/readable_sentences.py first.")
    if not main.anki_available():
        sys.exit("Anki isn't reachable; open Anki and run again.")
    known, kanji = main.studied_words(), main.studied_kanji()
    existing = main.load_sentences() if os.path.exists(main.SENTENCE_FILE) else []
    have_ids = {r["id"] for r in existing}
    have_text = {r["japanese"] for r in existing}

    seen, candidates = set(), []
    for jpn, eng, ids, words in main.example_sentences():
        heads = [w[0] for w in words]
        if ids in have_ids or jpn in have_text:
            seen |= skeletons(heads)
            continue
        if not words or not eng or not (MIN_LEN <= len(jpn) <= MAX_LEN):
            continue
        if not all(c in kanji for c in main._KANJI_CHAR.findall(jpn)):
            continue
        row_words, grammar = [], []
        for w in words:
            if w[0] in main.SENTENCE_GRAMMAR:
                if w[0] not in grammar:
                    grammar.append(w[0])
                continue
            front = known.find(w)
            if front is None:
                break
            surface = w[2] if w[2] and w[2] != front else ""
            item = f"{front}{{{surface}}}" if surface else front
            if item not in row_words:
                row_words.append(item)
        else:
            candidates.append((len(jpn), jpn, eng, ids, heads, row_words, grammar))

    picked, texts = [], set(have_text)
    for _, jpn, eng, ids, heads, row_words, grammar in sorted(candidates):
        if jpn in texts or skeletons(heads) & seen:
            continue
        texts.add(jpn)
        seen |= skeletons(heads)
        picked.append("\t".join([ids, jpn, eng, " ".join(row_words), " ".join(grammar), ""]))
        if len(picked) >= limit:
            break
    return picked, len(existing)


def cli():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true", help="append to sentences.tsv")
    p.add_argument("--max", type=int, default=40, help="most rows to propose (default 40)")
    p.add_argument("--profile", metavar="NAME", help="Anki profile to read (default: main.DEFAULT_PROFILE)")
    args = p.parse_args()
    with main.anki_profile(args.profile):
        rows, have = proposals(args.max)
    print(f"sentences.tsv has {have} rows; {len(rows)} new readable sentence(s):")
    for r in rows:
        cols = r.split("\t")
        print(f"  {cols[1]}  —  {cols[2]}")
    if args.write and rows:
        new_file = not os.path.exists(main.SENTENCE_FILE)
        with open(main.SENTENCE_FILE, "a", encoding="utf-8") as f:
            if new_file:
                f.write(HEADER)
            f.write("".join(r + "\n" for r in rows))
        print(f"Appended to {os.path.basename(main.SENTENCE_FILE)}.")
    elif rows:
        print("Dry run; --write to append.")


if __name__ == "__main__":
    cli()
