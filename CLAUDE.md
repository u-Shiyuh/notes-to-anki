# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A single-file Python CLI (`main.py`) that pushes Japanese study material into Anki through the AnkiConnect add-on. It has two modes:

- **Ledger sync** (default): reads every row of a Notion database (the "Language Learning Ledger") and creates or updates one Anki `Basic` note per row.
- **Kana seed** (`--seed-kana`): writes the built-in hiragana and katakana tables (104 each: gojūon, dakuten/handakuten, yōon) to `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.
- **Kanji seed** (`--seed-kanji`): writes the 1,000 most frequent kanji from `kanji_top1000.tsv` to `Nihongo::Core Kanji`, in frequency order. It skips kanji that already have a ledger card. Ledger `Kanji` rows also live in `Nihongo::Core Kanji` (`TYPE_DECKS`; merged on 2026-10-27, so `Nihongo::Kanji` is now unused). Inside that deck, a `notion_` link tag marks a ledger note, and its absence marks a seed note.

`kanji_top1000.tsv` is generated data. It was built once from KANJIDIC2 (CC BY-SA 4.0: frequency, readings, meanings, strokes) and kanji-data (MIT: JLPT N-levels and WaniKani's reading order). Its `#` header lists the sources and formatting rules. A leading `*` marks each kanji's most common on/kun reading, which comes first in its list. `kanji_readings` renders it bold and fades the rest; a lone reading is bold too. A line with no marked reading (about 57 kun lines, for kanji whose kun'yomi are all rare) is faded entirely. The generator isn't in the repo. To change the list, regenerate the file with the same columns rather than hand-editing 1,000 rows. Keep the attribution in the header and README.

There are no tests, no packaging and no `requirements.txt`. The only third-party dependency is `python-dotenv`. HTTP goes through `urllib`.

## Running

```bash
pip install python-dotenv
cp .env.sample .env            # then fill in NOTION_TOKEN / NOTION_DATABASE_ID

python main.py --dry-run               # preview the ledger sync (still calls Notion)
python main.py                         # sync the ledger (Anki must be open)
python main.py --seed-kana --dry-run   # preview the kana seed (no network)
python main.py --seed-kana
python main.py --seed-kanji --dry-run  # preview the kanji seed (reads Anki if open)
python main.py --seed-kanji
python main.py --no-update             # add new notes only; never modify existing ones
python main.py --prune --dry-run       # list linked notes whose Notion row is gone (needs Anki)
```

It runs on Windows (the user's current machine) and macOS; on macOS use `python3`/`pip3`. `main()` reconfigures stdout/stderr to UTF-8, because Windows consoles default to cp1252 and would crash printing kana. Code that imports `main` without calling `main()` (ad-hoc test snippets) still needs `PYTHONIOENCODING=utf-8` on Windows.

A safe smoke test that needs no credentials, Anki or network: `python main.py --seed-kana --dry-run`. `python main.py --dry-run` is read-only against Notion and prints the first five rendered card backs. With Anki open, both dry-runs also read (never write) Anki and list every planned change; that is the safe way to check sync logic against the real collection.

Never read or print `.env`. It holds the real Notion integration secret and is gitignored.

A non-dry run writes to the user's real Anki collection, so ask before running one. To test write paths, point `ANKICONNECT_URL` at a small in-memory fake AnkiConnect (a stdlib `HTTPServer` that implements the actions the script uses) instead of the real one.

## How it's used

The ledger sync runs over and over, not once. The user adds a row to Notion whenever they learn a new kanji, word or grammar point, then runs `python main.py`. That adds the new cards and keeps existing ones in line with Notion without touching review history. The kana and kanji seeds are meant to run once, because their tables don't change. They are safe to re-run.

As of 2026-10-19, every ledger note in the real collection carries its `notion_` link tag. So the Front-text fallback match only applies to notes created by hand or by older versions of the script.

### Automation

The script can't run on GitHub-hosted Actions. AnkiConnect is an HTTP server inside the desktop Anki app at `127.0.0.1:8765`, so a cloud runner can't reach it, and AnkiWeb has no official API for adding cards. The options considered, best first:

1. **A scheduled task on the user's computer** runs `python main.py` on a schedule. If Anki is closed the run fails harmlessly and the next one catches up. Anki's own AnkiWeb sync then carries the cards to other devices. This is the recommended option. It isn't set up yet.
   - **Windows:** Task Scheduler.
   - **macOS:** a `launchd` agent (a plist in `~/Library/LaunchAgents` with `StartCalendarInterval`), which, unlike `cron`, runs a missed job after the Mac wakes. Use `python3`. App Nap must be disabled for Anki (see README), or a background Anki stops answering AnkiConnect and every scheduled run fails.
2. **A self-hosted GitHub runner** on the same PC. It only works while the PC is on and Anki is open, so it's option 1 with more setup.
3. **A cloud Action that builds an `.apkg`** for the user to import by hand. It needs no PC, but every import is manual and it would add a second, non-AnkiConnect code path.
4. **A cloud Action that syncs through AnkiWeb** with Anki's Python library. Avoid this: it's unofficial, needs the AnkiWeb password stored as a secret, and can force a full sync that overwrites same-day reviews made on other devices.

## Code map (`main.py`)

| Area | Functions / constants |
|---|---|
| Config | `NOTION_TOKEN`, `NOTION_DATABASE_ID` (from env via dotenv; `sync_ledger` treats any value containing `paste_your` (any case) as missing), `DECK_ROOT="Nihongo"`, `NOTE_TYPE="Basic"`, `KANJI_DECK`, `TYPE_DECKS` (Type → deck overrides), `KANA_SCOPE` / `KANJI_SCOPE` / `LEDGER_SCOPE` / `LEDGER_KANJI_SCOPE` (Anki searches; `_LINKED` is `tag:notion\_*`, escaped because `_` is a wildcard in Anki search), `KANJI_FILE`, `LINK_TAG_PREFIX`, `TYPE_TAGS`, `NOTE_OPTIONS` (`duplicateScope: "deck"`), `ANKICONNECT_URL` |
| Kana data | `HIRAGANA_*`, `KATAKANA_*` lists of `(kana, romaji)`; `kana_note`, `build_kana_notes`, `seed_kana` |
| Kanji seed | `load_kanji` (parses `KANJI_FILE`), `kanji_readings`, `kanji_note` (its own Back layout and `kanji`/`core_kanji`/`jlpt_nN` tags), `without_ledger_kanji`, `seed_kanji` |
| Notion | `notion_request` (retries 429/5xx/network errors with backoff, honouring `Retry-After`; exits on other errors), `fetch_all_rows` (API `2025-09-03`: reads the database's `data_sources`, then pages through `/data_sources/{id}/query`), `get_prop`, `skip_reason`, `row_to_note`, `link_tag` |
| Card layout | `format_back`, `split_note`, `sentences`, `preview_html` (dry-run only) |
| Anki | `anki_request` (exits if AnkiConnect is unreachable; *logs but does not raise* on AnkiConnect errors), `anki_available`, `anki_multi` (batches writes through `multi`), `find_notes`, `same_html`, `plan_changes` (read-only), `print_plan`, `summarize`, `preview_changes` (dry-run), `add_or_update_notes` |
| CLI | `main` (argparse: `--dry-run`, `--seed-kana`, `--seed-kanji`, `--no-update`, `--prune`; the two seeds are mutually exclusive, and `--prune` is rejected with either seed or with `--no-update`) |

`_GOJUON` is defined and then `del`'d.

### Notion schema the script expects

| Property | Notion type | Used as |
|---|---|---|
| `Item` | title | Front field |
| `Readings` | rich_text | Back, under the meaning |
| `Meaning` | rich_text | Back, headline |
| `Type` | select | `Kanji` / `Vocab` / `Grammar` / `Grammar Drill`. Deck `Nihongo::<Type>` (`TYPE_DECKS` sends `Kanji` to `Nihongo::Core Kanji`) plus a lowercase tag with spaces → `_` (defaults to `Vocab`); `Grammar` gets prose layout |
| `Lesson` | number | Tag `lesson<N>` |
| `Language` | select | Rows whose value isn't `LANGUAGE` ("Japanese") are skipped; empty is kept |

The database also has `Status`, `Attempts`, `Correct Streak` and `Last Reviewed`, which the script ignores. Missing properties quietly become `""`. Changing these names requires editing `row_to_note` / `skip_reason`.

Rows are skipped (and reported) when `Item` is empty, starts with `IGNORE` (`SKIP_PREFIX`), or has a different `Language`.

### Card back layout (`format_back`)

The Back field is HTML with inline styles only, so it works with the stock `Basic` note type and in Anki's night mode (notes are faded with `opacity`, not a colour). The Front is sent as the raw `Item` text. It is the fallback matching key for notes that don't have a link tag yet (see below), so keep it raw.

- **Kanji / Vocab:** each of `Meaning` and `Readings` is split on the first `" — "` (`NOTE_SEP`) into core and side note. The first sentence of the meaning is a bold headline, any further meaning sentences follow on their own lines, then the core readings, then the side notes in small, faded text.
- **Grammar Drill** (short practice rows: prompt in `Item`, answer in `Meaning`, reason in `Readings`) uses the Kanji/Vocab layout and lands in `Nihongo::Grammar Drill`. The long `Grammar` rows are reference notes.
- **Grammar:** `Meaning` then `Readings` are split into sentences (`_SENTENCE_BREAK`, which ignores `e.g.`, `i.e.`, `vs.`, `etc.`). The first sentence is the headline and the rest go one per line.

All text is HTML-escaped. Changing `format_back` changes every Back field, so the next default (updating) sync rewrites every existing note once.

### How updates work (`plan_changes` → `add_or_update_notes`)

`plan_changes` is read-only and returns a plan. `add_or_update_notes` prints it and applies it; `--dry-run` prints it via `preview_changes` (only if Anki is reachable).

1. **Scope.** Each mode only reads notes matching `note:"Basic" <scope>`: `KANA_SCOPE` (`Nihongo::Kana` and below) for the kana seed, `KANJI_SCOPE` (unlinked notes in `Nihongo::Core Kanji`) for the kanji seed, `LEDGER_SCOPE` (`Nihongo` minus `Nihongo::Kana` and minus `KANJI_SCOPE`) for the ledger. Notes outside the scope are never matched or changed, with one exception: adoption (step 3). `NOTE_OPTIONS` sets `duplicateScope: "deck"` so the same Front can exist in a kana deck and a ledger deck.
2. **In-batch duplicates.** If two incoming notes share deck and Front, only the first is used; the rest are reported under "Not added".
3. **Matching.** Ledger notes carry a `notion_<page id without dashes>` tag (`link_tag`). An incoming note matches the existing note with the same link tag; otherwise an existing note *without* a link tag and with the same Front (this is how pre-link notes and the kana cards match). Each existing note is matched at most once.
   - **Adoption** (`adopt=` on `plan_changes`; only the ledger sync passes it). A ledger `Kanji` note that matched nothing takes over the seed's `Nihongo::Core Kanji` note with the same Front. That note then goes through the normal update path, so it's rewritten and gets its link tag (it's already in the right deck), and its review history is kept. Its `core_kanji`/`jlpt_nN` tags aren't owned by the ledger, so they stay. Only `Kanji`-type rows adopt; a `Vocab` row `会` doesn't take over the Core Kanji `会` card. Once the note is linked, it leaves `KANJI_SCOPE`. `without_ledger_kanji` checks `LEDGER_KANJI_SCOPE` (linked `kanji` notes anywhere under `Nihongo`, even before the sync has moved them) so the seed doesn't re-add the kanji.
4. **Changes for matched notes** (skipped entirely with `--no-update`):
   - Front or Back differs (compared with `same_html`, which ignores entity, whitespace and `style` formatting differences): `updateNoteFields` with both fields. This also applies Item renames.
   - Any card not in the target deck (`getDecks`): `changeDeck`.
   - Tags: missing ones are added. A tag on the note is removed only if the note shouldn't have it *and* the script owns it: `lessonN`, `TYPE_TAGS`, `notion_*`, or any tag the current batch produces. All other tags are the user's and are kept.
5. **Adds.** Unmatched notes are checked with `canAddNotesWithErrorDetail`; only addable ones go to `addNotes`, so counts are accurate and one bad note can't fail the batch. Rejections are listed with Anki's reason. A "deck was not found" error doesn't count as a rejection, because the run creates missing decks before adding.
6. **Prune** (`--prune`, ledger only): linked notes in scope that matched no incoming note are deleted with `deleteNotes`. Unlinked leftovers are listed but never deleted, because they may be hand-made.

All writes except `addNotes` go through `anki_multi` in chunks of `ANKI_MULTI_CHUNK`, in this order: `createDeck`, `updateNoteFields`, `changeDeck`, `addTags`/`removeTags`, `deleteNotes`. Re-running with nothing changed sends no write requests.

## Known issues / review notes

Confirm the user wants a fix before changing behaviour.

1. **Unlinked orphans.** A note whose row was deleted before the note got its `notion_` tag looks the same as a hand-made card, so `--prune` won't delete it (today: `聴く`, whose row became `IGNORE — 聴く`). It must be deleted by hand.
2. **Front fallback can adopt a hand-made card.** A hand-made `Basic` card in a ledger deck whose Front equals a ledger `Item` gets matched once, overwritten and linked. Cards outside `Nihongo` are safe.
3. **Notion result cap.** `/data_sources/{id}/query` stops at 10,000 results per query. The ledger is about 400 rows.
4. **Core Kanji is a snapshot.** Kanji that already had a ledger card when the seed ran are skipped (110 on 2026-10-27). If such a ledger row is later deleted and pruned, the next `--seed-kanji` adds that kanji back as a fresh Core Kanji card.
5. **`addNotes` errors are counted, not itemised.** Adds are pre-checked, so this is rare; if `addNotes` itself errors, the run reports one failed request and "Added 0".

## Conventions

- Keep it a single, dependency-light script. Use stdlib `urllib` for HTTP.
- Put user-facing errors on `stderr`, and call `sys.exit(1)` for fatal ones.
- Every mode must stay safe to re-run (idempotent) and must support `--dry-run`.
- If you add a CLI flag, update the module docstring's USAGE block and `README.md`.
