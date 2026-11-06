"""Fill the `topic` column of words.tsv from tools/topics_data.py.

One-off helper (2026-11-06), kept so the assignment is reproducible. After it
runs, words.tsv is the source of truth: edit topics there by hand, and use this
only to apply a bulk change made in topics_data.py.

  - Sets each listed word's topic (column 7), and clears topics on rows that
    aren't listed.
  - Appends the EXTRA words (everyday words missing from the JLPT lists, e.g.
    ピンク, 肩) at the end with a blank level, unless they're already there.
  - Reports listed words that aren't in words.tsv (typos or missing words).

Usage:
  python3 tools/assign_topics.py           # report what would change
  python3 tools/assign_topics.py --write   # apply it
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from topics_data import TOPICS, EXTRA  # noqa: E402

WORDS = Path(__file__).resolve().parent.parent / "words.tsv"


def main(argv):
    topic_of = {}
    for topic, words in TOPICS.items():
        # A two-part entry is written with " / " (自由席 / 指定席); keep it whole.
        for w in re.split(r"(?<! /) (?!/ )", words.strip()):
            w = w.strip()
            if w in topic_of:
                sys.exit(f"{w} is listed under both {topic_of[w]} and {topic}")
            topic_of[w] = topic
    for word, _, _, _, topic in EXTRA:
        topic_of.setdefault(word, topic)

    lines = WORDS.read_text(encoding="utf-8").split("\n")
    seen, changed = set(), 0
    for i, line in enumerate(lines):
        if not line or line.startswith("#"):
            continue
        cols = (line.split("\t") + [""] * 7)[:7]
        seen.add(cols[1])
        want = topic_of.get(cols[1], "")
        if cols[6] != want:  # only touch rows whose topic changes
            cols[6] = want
            changed += 1
            lines[i] = "\t".join(cols) if want else "\t".join(cols[:6])
    added = [e for e in EXTRA if e[0] not in seen]
    while lines and lines[-1] == "":
        lines.pop()
    for word, kana, meaning, typ, topic in added:
        lines.append("\t".join(["", word, kana, meaning, typ, "", topic]))
    missing = sorted(w for w in topic_of if w not in seen and w not in {e[0] for e in added})

    print(f"{changed} row(s) get a new topic; {len(added)} word(s) added: "
          f"{' '.join(e[0] for e in added) or '-'}")
    if missing:
        print("Listed but not in words.tsv:", " ".join(missing))
    if "--write" in argv:
        WORDS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Wrote words.tsv.")


if __name__ == "__main__":
    main(sys.argv[1:])
