# CLAUDE.md

Guidance for Claude Code when working in this repo. This file holds the rules and a map; the detail
lives in `docs/` and is read only when needed. Keep this file short: put new history and deck details
in `docs/decks.md` (or `docs/tools.md`, `docs/internals.md`), and only a rule or a pointer here.

## What this is

A single-file Python CLI (`main.py`) that pushes the user's Japanese study material into Anki through
the AnkiConnect add-on, from hand-edited and generated `.tsv` files. Anki is the record of study
progress. The user studies early N5, mostly through these decks plus textbooks.

| Deck (`Nihongo::…`) | Flag | Data | Notes |
|---|---|---|---|
| Kana::Hiragana / Katakana | `--seed-kana` | built into `main.py` | done; never changes |
| Core Kanji | `--seed-kanji` | `kanji_top1000.tsv`, `kanji_extra.tsv`, `radicals.tsv` | frequency order |
| Verbs | `--seed-verbs` | `verbs.tsv` | reviewer book sections + `extra` + `cg` |
| Words | `--seed-words` | `words.tsv` | skips verbs and words a kanji card covers |
| Numbers & Time | `--seed-numbers` | `numbers.tsv` | real-world formats (3本, 午後2時) |
| Sentences | `--seed-sentences` | `sentences.tsv` | Tatoeba, from `tools/add_sentences.py` |
| Kanji Look-alikes | `--seed-lookalikes` | `lookalikes.tsv` | only pairs of studied kanji |
| Lessons | `--order` | `references.tsv` | fast lane: new cards a lesson mentioned, and their kanji |
| Kanji N5-N4 | `--order` | kanji `jlpt` column | fast lane: new N5/N4 kanji |
| (all new cards) | `--order` | — | lanes first, then study order; needs the helper add-on |
| (any mode) | `--profile NAME` | — | Anki profile to use; default `User 1` (the user's) |

Every deck's details and history: `docs/decks.md`. Tools: `docs/tools.md`. How `main.py` matches and
updates notes, the code map and known issues: `docs/internals.md`.

**Two Anki profiles** (2026-11-21): `User 1` is the user's, `verge` is a friend's (his own AnkiWeb
account; plan in `docs/n3-plan.md`). Every run opens `User 1` unless `--profile` says otherwise, and
reopens the previous profile at the end. A profile's settings live in `users/<profile>/user.json`
(verge: only `jlpt`/`tatoeba` ref tags, no Lessons lane, `--order` follows `default_order.tsv`);
no file = the user's behaviour. His progress record goes to `users/verge/progress.tsv`. Seeded 2026-11-21.

**The Notion ledger sync is disabled** (2026-11-06; `NOTION_SYNC_ENABLED = False`). A run without a
`--seed-*` option or `--order` exits 1. Don't re-enable it unless the user asks.

## Learning workflow

- `study/profile.md` is the one place that says what the user knows: sources (with
  their tag codes), grammar learned by topic, and a dated log. Don't make per-book or per-lesson files.
- `references.tsv` lists, per lesson, every card Front it mentioned. The seeds turn it into
  `ref::<source>::<lesson>` tags; they also add `ref::jlpt::nN`, `ref::verb_book::sN`, `ref::tatoeba`.
- When the user reports a lesson or something they studied: use the **`log-lesson`** skill.
- To push changes to Anki: use the **`sync`** skill.
- **Fast lanes** (user's choice, 2026-11-14): `Nihongo::Lessons` and `Nihongo::Kanji N5-N4` hold new
  cards with their own daily limits, so the home decks' limits stay fixed. `--order` moves new cards in
  and, once mature (21 days), back home (`fill_lanes`, `LANES`); studied cards never move in. Seeds count
  a card in its lane as in place. It's the same note, so it keeps its deck's format. Easy cards: press Easy.
  **A new study deck must be added to `LANES`/`LANE_HOME_TAGS` and its seed's scope must use `deck_query`**,
  or a lesson card moved to Lessons looks missing to its seed (duplicates).

## Rules

- **Ask before any non-dry run.** It writes to the user's real Anki collection. Dry runs are safe and
  read Anki without writing. To test write paths, point `ANKICONNECT_URL` at a small in-memory fake
  AnkiConnect (a stdlib `HTTPServer` implementing the actions the script uses).
- **Never read or print `.env`.** It holds the real Notion secret and is gitignored.
- **The `.tsv` files are the source of truth.** They carry hand edits; tools check them or append,
  never overwrite one wholesale. After editing data, `python3 tools/check_data.py` must flag nothing.
  Every Anki card must have a TSV counterpart (no Anki-only cards): after a sync,
  `python3 tools/check_drift.py` must report no drift.
- **Generator and checker scripts live in `tools/` and are committed**, with every source pinned
  (the original generators were lost by leaving them in a scratchpad). Downloads go in `tools/cache/`.
- **Keep the attribution** headers in the data files, `README.md` and `sources/README.md` (JMdict,
  KANJIDIC2 and JmdictFurigana are CC BY-SA; Tatoeba CC BY).
- **One meaning style on every deck** (short comma list, common sense first; detail in `note`), and a
  word on two decks must agree. Every word-type deck shows the faded radical line. See `docs/tools.md`.
- **One card per word.** A word lives on one deck; seeds adopt cards by Front and keep their history.
- Confirm the user wants a fix before changing behaviour listed under known issues (`docs/internals.md`).

## Running

```bash
python3 main.py --seed-kana --dry-run   # smoke test: no Anki, network or credentials needed
python3 main.py --seed-<deck> --dry-run # preview one seed (reads Anki if open)
python3 main.py --seed-<deck>           # write it (ask first)
python3 main.py --order --dry-run       # what the study-order step would move
python3 main.py --no-update             # add new notes only
```

Decks: `kana`, `kanji`, `verbs`, `words`, `numbers`, `sentences`, `lookalikes`. The seeds and `--order`
are mutually exclusive.

It runs on macOS (use `python3`) and Windows. `main()` reconfigures stdout/stderr to UTF-8 for
Windows consoles; code that imports `main` without calling `main()` needs `PYTHONIOENCODING=utf-8`
there. `python-dotenv` is optional (only the disabled Notion sync reads `.env`). There are no tests,
no packaging and no `requirements.txt`.

## Conventions

- Keep it a single, dependency-light script. Use stdlib `urllib` for HTTP.
- Put user-facing errors on `stderr`, and call `sys.exit(1)` for fatal ones.
- Every mode must stay safe to re-run (idempotent) and must support `--dry-run`.
- If you add a CLI flag, update the module docstring's USAGE block, `README.md` and the deck table above.
- Commit on `master` (the repo's habit), one commit per feature.
