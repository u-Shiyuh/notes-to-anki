#!/usr/bin/env python3
"""Check that Anki matches the TSVs: no drift.

The TSVs are the source of truth, so every card in Anki must be one the
seeds would build from them, with the same text and source tags. This
script rebuilds every deck from scratch into an in-memory fake AnkiConnect
(nothing is written anywhere), then reads the real collection (read-only)
and compares the two, note by note.

Reported as drift:
  - a card in Anki that no seed builds (no TSV counterpart)
  - a card the seeds build that is missing from Anki (run the seed)
  - a different Back, a different deck, or different ref::/topic_ tags

Not drift (expected):
  - Nihongo::Kanji Look-alikes: dynamic, adds a pair once both kanji are studied
  - cards in the fast lanes (Lessons, Kanji N5-N4) instead of their home deck
  - tags set by --order from review history (kanji_ready, word_seen, ...)

Usage (Anki open with AnkiConnect):
    python3 tools/check_drift.py
    python3 tools/check_drift.py --profile verge   # another Anki profile
Exit status 1 if any drift is found.
"""
import contextlib
import io
import json
import os
import sys
import threading
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import main  # noqa: E402

REAL_URL = main.ANKICONNECT_URL
SEEDS = ["kana", "kanji", "verbs", "words", "numbers", "sentences"]
DYNAMIC_DECKS = {"Nihongo::Kanji Look-alikes"}
LANE_DECKS = {"Nihongo::Lessons", "Nihongo::Kanji N5-N4"}
# Tags that come from the TSVs; other tags (study order, legacy) are ignored.
COMPARED_TAG_PREFIXES = (main.REF_TAG_PREFIX, main.TOPIC_TAG_PREFIX)


def rebuild():
    """Every note the seeds would add to an empty collection."""
    added = []

    def handle(action, params):
        if action == "multi":
            return [{"result": handle(a["action"], a.get("params", {})), "error": None}
                    for a in params["actions"]]
        if action == "addNotes":
            added.extend(params["notes"])
            return list(range(len(params["notes"])))
        if action == "canAddNotesWithErrorDetail":
            return [{"canAdd": True} for _ in params["notes"]]
        if action in ("findNotes", "findCards", "notesInfo", "cardsInfo"):
            return []
        if action == "getDecks":
            return {}
        if action == "version":
            return 6
        return None

    class Fake(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = {"result": handle(body["action"], body.get("params", {})), "error": None}
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    main.ANKICONNECT_URL = f"http://127.0.0.1:{server.server_port}"
    saved_argv = sys.argv
    try:
        for deck in SEEDS:
            sys.argv = ["main.py", f"--seed-{deck}"]
            log = io.StringIO()
            try:
                with contextlib.redirect_stdout(log):
                    main.main()
            except SystemExit as e:
                if e.code:
                    print(f"Rebuilding {deck} failed:\n{log.getvalue()[-1000:]}", file=sys.stderr)
                    sys.exit(1)
    finally:
        sys.argv = saved_argv
        main.ANKICONNECT_URL = REAL_URL
        server.shutdown()
    return added


def real_anki(action, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    try:
        with urllib.request.urlopen(urllib.request.Request(REAL_URL, data=body)) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except OSError:
        print(f"Could not reach AnkiConnect at {REAL_URL} -- is Anki open?", file=sys.stderr)
        sys.exit(1)
    if result.get("error"):
        print(f"AnkiConnect error on {action}: {result['error']}", file=sys.stderr)
        sys.exit(1)
    return result["result"]


def compared_tags(tags):
    return sorted(t for t in tags if t.startswith(COMPARED_TAG_PREFIXES))


def main_():
    built = defaultdict(list)
    for note in rebuild():
        built[note["fields"]["Front"]].append(note)

    ids = real_anki("findNotes", query=f'"deck:{main.DECK_ROOT}*"')
    notes = real_anki("notesInfo", notes=ids) if ids else []
    cards = real_anki("cardsInfo", cards=[c for n in notes for c in n["cards"]]) if notes else []
    deck_of = {c["note"]: c["deckName"] for c in cards}

    problems = []
    real = defaultdict(list)
    for n in notes:
        if deck_of.get(n["noteId"]) in DYNAMIC_DECKS:
            continue
        real[n["fields"]["Front"]["value"]].append(n)

    for front in sorted(set(real) | set(built)):
        have, want = real.get(front, []), list(built.get(front, []))
        unmatched = []
        for n in have:
            deck = deck_of.get(n["noteId"])
            back = n["fields"].get("Back", {}).get("value", "")
            # Pair with a built note of the same Front, preferring the same deck.
            pick = next((w for w in want if w["deckName"] == deck), None)
            if pick is None and deck in LANE_DECKS:
                # A lane holds cards from several home decks, so a word and its
                # kanji (飴) can share a Front there: pair by text first.
                pick = next((w for w in want if w["fields"]["Back"] == back),
                            next(iter(want), None))
            if pick is None:
                unmatched.append(n)
                continue
            want.remove(pick)
            issues = []
            if back != pick["fields"]["Back"]:
                issues.append("text differs (run the seed)")
            if deck != pick["deckName"] and deck not in LANE_DECKS:
                issues.append(f"in {deck}, TSVs say {pick['deckName']}")
            if compared_tags(n["tags"]) != compared_tags(pick["tags"]):
                issues.append("ref/topic tags differ (run the seed)")
            if issues:
                problems.append(f"{front}: " + "; ".join(issues))
        for n in unmatched:
            problems.append(f"{front}: in {deck_of.get(n['noteId'])} but no TSV row builds it")
        for w in want:
            problems.append(f"{front}: missing from Anki ({w['deckName']}; run the seed)")

    checked = sum(len(v) for v in real.values())
    if problems:
        print(f"Drift: {len(problems)} problem(s) across {checked} cards.")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print(f"No drift: all {checked} cards (look-alikes excluded) match the TSVs.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    with main.anki_profile(main.profile_from_argv(sys.argv[1:])):
        main_()
