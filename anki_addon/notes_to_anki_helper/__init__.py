"""notes-to-anki helper: lets main.py reposition new cards.

AnkiConnect has no reposition action and refuses to set a card's queue
position ("Use native scheduling commands for protected state"), so this
add-on exposes Anki's own Cards > Reposition (sched.reposition_new_cards) on
http://127.0.0.1:8766. It only accepts connections from this computer, only
moves cards that are still new, and adds no review-log entries; it is undoable
with Edit > Undo like the browser command.

Request (POST, JSON):
  {"action": "version"}
  {"action": "repositionNewCards",
   "params": {"cards": [card ids in the wanted order], "start": 0,
              "step": 1, "shift": true}}
Reply: {"result": ..., "error": null | "message"}

Install: symlink this folder into Anki's addons21 folder (README), restart Anki.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aqt import mw
from aqt.operations import CollectionOp

PORT = 8766
VERSION = 1
TIMEOUT = 60


def _reposition(params, done):
    cids = [int(c) for c in params.get("cards", [])]
    # Anki keeps the cards' existing relative order (randomize off), so the
    # caller's list only chooses which cards move.
    new = set(mw.col.find_cards("is:new"))
    cids = [c for c in cids if c in new]

    def op(col):
        return col.sched.reposition_new_cards(
            card_ids=cids,
            starting_from=int(params.get("start", 0)),
            step_size=int(params.get("step", 1)),
            randomize=False,
            shift_existing=bool(params.get("shift", True)),
        )

    def ok(changes):
        done({"result": {"moved": getattr(changes, "count", len(cids))}, "error": None})

    def fail(err):
        done({"result": None, "error": str(err)})

    if not cids:
        done({"result": {"moved": 0}, "error": None})
        return
    CollectionOp(parent=mw, op=op).success(ok).failure(fail).run_in_background()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._reply({"result": None, "error": "bad JSON"}, 400)
            return
        action = req.get("action")
        if action == "version":
            self._reply({"result": VERSION, "error": None})
            return
        if action != "repositionNewCards":
            self._reply({"result": None, "error": f"unknown action {action!r}"}, 400)
            return
        box, event = {}, threading.Event()

        def done(payload):
            box.update(payload)
            event.set()

        mw.taskman.run_on_main(lambda: _reposition(req.get("params") or {}, done))
        if not event.wait(TIMEOUT):
            self._reply({"result": None, "error": "timed out waiting for Anki"}, 504)
            return
        self._reply(box)


def _start():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    except OSError as e:
        print(f"notes-to-anki helper: port {PORT} unavailable ({e})")
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()


_start()
