"""Drop duplicate readings from kanji_top1000.tsv and kanji_extra.tsv.

One-off helper (2026-11-11). KANJIDIC2 lists some readings twice, once with
the okurigana marked and once without (後 うし(ろ) and うしろ, 行 -い(き) and
-いき), so the card showed the same reading twice. Two readings count as the
same when they match once the okurigana brackets are removed; prefix/suffix
dashes still count (あい-, -あい and あ(い) are different uses). The one kept
is the bold one if either is bold, else the one with okurigana marked, else
the first; the others keep their order.

Usage:
  python3 tools/dedupe_readings.py           # show what would change
  python3 tools/dedupe_readings.py --write   # apply it
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "kanji_top1000.tsv", ROOT / "kanji_extra.tsv"]


def key(r):
    return r.lstrip("*").replace("(", "").replace(")", "")


def rank(r):
    return (not r.startswith("*"), "(" not in r)


def dedupe(cell):
    rs = [r for r in cell.split("、") if r]
    best = {}
    for r in rs:
        k = key(r)
        if k not in best or rank(r) < rank(best[k]):
            best[k] = r
    out, done = [], set()
    for r in rs:
        k = key(r)
        if k not in done:
            out.append(best[k])
            done.add(k)
    return "、".join(out)


def main(argv):
    total = 0
    for path in FILES:
        lines = path.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            if not line or line.startswith("#"):
                continue
            c = line.split("\t")
            for col in (5, 6):
                new = dedupe(c[col])
                if new != c[col]:
                    print(f"{path.name}: {c[1]}  {c[col]}  ->  {new}")
                    c[col] = new
                    total += 1
            lines[i] = "\t".join(c)
        if "--write" in argv:
            path.write_text("\n".join(lines), encoding="utf-8")
    print(f"{total} line(s) {'changed' if '--write' in argv else 'would change'}.",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
