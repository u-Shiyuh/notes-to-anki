#!/usr/bin/env python3
"""Progress report: where the user stands toward their goals (read-only).

Anki's own stats describe memory (reviews, intervals). This combines Anki's
card states with what only the TSVs know: JLPT levels, sources and lessons,
and how common each word is. It never writes to Anki.

  seen  = the card has been studied at least once (not new)
  known = mature: interval of 21 days or more (main.MATURE_DAYS)

Sections, each a small function (add one by writing a function and listing it
in SECTIONS):
  JLPT coverage   N5/N4 words (Words + Verbs) and kanji, seen and known
  Common words    of the most common words in the decks, how many are seen
                  (word frequency: EDRDG's examples.utf, Tatoeba sentences
                  with word indices; skipped if tools/cache lacks it)
  Sources         each lesson / book section (ref:: tags): cards seen
  Retention       last 7 days, reviews passed (Again = failed), young/mature
  Pace            new N5 cards per day over the last 14 days, and when N5
                  would be done at that pace

A one-kanji word its Core Kanji card teaches (雪) counts through that card.

Usage (Anki open with AnkiConnect):
    python3 tools/progress.py
"""
import csv
import datetime
import gzip
import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import main  # noqa: E402

CORPUS = os.path.join(ROOT, "tools", "cache", "examples.utf.gz")
PACE_DAYS = 14


def anki(action, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    try:
        with urllib.request.urlopen(urllib.request.Request(main.ANKICONNECT_URL, data=body)) as r:
            result = json.loads(r.read().decode("utf-8"))
    except OSError:
        sys.exit(f"Could not reach AnkiConnect at {main.ANKICONNECT_URL} -- is Anki open?")
    if result.get("error"):
        sys.exit(f"AnkiConnect error on {action}: {result['error']}")
    return result["result"]


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


class Collection:
    """Card state of every Nihongo note, keyed by (kind, Front). The kind is
    the home deck's seed tag (word, verb, core_kanji, numbers), so a card in a
    fast lane still counts for its home deck."""

    def __init__(self):
        ids = anki("findNotes", query=f'"deck:{main.DECK_ROOT}*"')
        notes = anki("notesInfo", notes=ids) if ids else []
        cards = anki("cardsInfo", cards=[c for n in notes for c in n["cards"]]) if notes else []
        by_note = {c["note"]: c for c in cards}
        kinds = set(main.LANE_HOME_TAGS.values())
        self.card = {}
        self.notes = []
        for n in notes:
            c = by_note.get(n["noteId"])
            if not c:
                continue
            front = n["fields"]["Front"]["value"]
            state = {"seen": c["type"] != 0, "known": c["interval"] >= main.MATURE_DAYS,
                     "id": c["cardId"], "tags": n["tags"], "deck": c["deckName"]}
            self.notes.append(state)
            # A note can carry two kind tags (はく: word card tagged "verb" too).
            for kind in kinds.intersection(n["tags"]):
                self.card[(kind, front)] = state

    def get(self, kind, front):
        return self.card.get((kind, front))


def vocab(col):
    """Every word and verb as (front, kana, level, card state)."""
    levels = {}
    for n in (4, 5):
        with open(os.path.join(ROOT, "sources", f"n{n}.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                levels[r["expression"]] = f"n{n}"
    out = []
    verbs = main.load_verbs()
    verb_words = {v["word"] for v in verbs}
    for v in verbs:
        out.append((v["word"], v["kana"], levels.get(v["word"], ""), col.get("verb", v["word"])))
    for w in main.load_words():
        if w["word"] in verb_words:
            continue
        card = (col.get("core_kanji", w["word"]) if main.kanji_card_covers(w)
                else col.get("word", w["word"]))
        out.append((w["word"], w["kana"], w["level"], card))
    return out


def count(states):
    states = [s for s in states if s]
    return len(states), sum(s["seen"] for s in states), sum(s["known"] for s in states)


def jlpt_coverage(col, words):
    lines = ["JLPT coverage           seen        known (mature)"]
    for lvl in ("n5", "n4"):
        total, seen, known = count(s for _, _, l, s in words if l == lvl)
        lines.append(f"  {lvl.upper()} words  {total:5}   {seen:4} {pct(seen, total):>4}   {known:4} {pct(known, total):>4}")
    for lvl in ("5", "4"):
        total, seen, known = count(col.get("core_kanji", k) for k, r in main.core_kanji().items()
                                   if r["jlpt"] == lvl)
        lines.append(f"  N{lvl} kanji  {total:5}   {seen:4} {pct(seen, total):>4}   {known:4} {pct(known, total):>4}")
    return lines


def common_words(col, words):
    if not os.path.exists(CORPUS):
        return ["Common words: skipped (no tools/cache/examples.utf.gz; "
                "run tools/readable_sentences.py once to download it)"]
    freq = Counter()
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("B: "):
                for tok in line[3:].split():
                    head = re.split(r"[(\[{~|]", tok)[0]
                    freq[head] += 1
                    for m in re.findall(r"[({]([^)}]+)[)}]", tok):
                        if m != head:
                            freq[m] += 1

    def f(word, kana):
        if re.search(r"[一-龯]", word):
            return freq[word]
        return max(freq[word], freq[kana])

    ranked = sorted((w for w in words if w[3]), key=lambda w: -f(w[0], w[1]))
    lines = ["Common words (most frequent in everyday sentences)"]
    for top in (100, 300, 1000):
        part = ranked[:top]
        seen = sum(w[3]["seen"] for w in part)
        known = sum(w[3]["known"] for w in part)
        lines.append(f"  top {top:<5} seen {seen:4} {pct(seen, len(part)):>4}   known {known:4} {pct(known, len(part)):>4}")
    missing = [w[0] for w in ranked[:100] if not w[3]["seen"]]
    if missing:
        lines.append("  next common ones: " + " ".join(missing[:15]))
    return lines


def sources(col, words):
    groups = defaultdict(list)
    for s in col.notes:
        for t in s["tags"]:
            if t.startswith(main.REF_TAG_PREFIX) and not t.startswith(main.REF_TAG_PREFIX + "jlpt"):
                groups[t[len(main.REF_TAG_PREFIX):]].append(s)
    lines = ["Sources                 cards   seen"]
    for ref in sorted(groups):
        total, seen, _ = count(groups[ref])
        lines.append(f"  {ref:20} {total:5}   {seen:4} {pct(seen, total):>4}")
    return lines


def retention(col, words):
    ids = anki("findCards", query=f'"deck:{main.DECK_ROOT}*" rated:7 -is:new')
    revs = anki("getReviewsOfCards", cards=[str(i) for i in ids]) if ids else {}
    since = (datetime.datetime.now() - datetime.timedelta(days=7)).timestamp() * 1000
    stats = {"young": [0, 0], "mature": [0, 0]}
    for entries in (revs or {}).values():
        for r in entries:
            if r["id"] < since or r["type"] != 1:  # type 1 = review (not learning)
                continue
            group = "mature" if r["lastIvl"] >= main.MATURE_DAYS else "young"
            stats[group][0] += 1
            stats[group][1] += r["ease"] > 1
    lines = ["Retention, last 7 days (reviews passed; aim for 80-90%)"]
    for g, (n, ok) in stats.items():
        lines.append(f"  {g:7} {ok:4} of {n:4}  {pct(ok, n):>4}")
    return lines


def pace(col, words):
    recent = set(anki("findCards", query=f'"deck:{main.DECK_ROOT}*" introduced:{PACE_DAYS}'))
    n5 = [s for _, _, l, s in words if l == "n5" and s]
    n5 += [s for s in (col.get("core_kanji", k) for k, r in main.core_kanji().items()
                       if r["jlpt"] == "5") if s]
    new_n5 = sum(s["id"] in recent for s in n5)
    left = sum(not s["seen"] for s in n5)
    lines = [f"Pace (last {PACE_DAYS} days)",
             f"  new cards: {len(recent) / PACE_DAYS:.0f}/day, of which N5: {new_n5 / PACE_DAYS:.1f}/day",
             f"  N5 words + kanji left: {left}"]
    if new_n5 and left:
        days = left / (new_n5 / PACE_DAYS)
        done = datetime.date.today() + datetime.timedelta(days=round(days))
        lines.append(f"  at this pace N5 is all seen by about {done:%Y-%m-%d} ({days:.0f} days)")
    return lines


SECTIONS = [jlpt_coverage, common_words, sources, retention, pace]


def run():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    col = Collection()
    words = vocab(col)
    print(f"Progress on {datetime.date.today():%Y-%m-%d}")
    for section in SECTIONS:
        print()
        print("\n".join(section(col, words)))


if __name__ == "__main__":
    run()
