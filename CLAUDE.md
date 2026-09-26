# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A single-file Python CLI (`main.py`) that pushes Japanese study material into Anki through the AnkiConnect add-on. It has two modes:

- **Ledger sync** (default): reads every row of a Notion database (the "Language Learning Ledger") and creates or updates one Anki `Basic` note per row.
- **Kana seed** (`--seed-kana`): writes the built-in hiragana and katakana tables (104 each: gojūon, dakuten/handakuten, yōon) to `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.

There are no tests, no packaging and no `requirements.txt`. The only third-party dependency is `python-dotenv`. HTTP goes through `urllib`, not `requests`, even though the module docstring says to install `requests`.

## Running

```bash
pip install python-dotenv
cp .env.sample .env            # then fill in NOTION_TOKEN / NOTION_DATABASE_ID

python main.py --dry-run               # preview the ledger sync (still calls Notion)
python main.py                         # sync the ledger (Anki must be open)
python main.py --seed-kana --dry-run   # preview the kana seed (no network)
python main.py --seed-kana
python main.py --no-update             # add new notes only; never modify existing ones
```

**Windows:** set `PYTHONIOENCODING=utf-8` (or run `python -X utf8`). Otherwise both `--dry-run` paths crash with `UnicodeEncodeError: 'charmap' codec can't encode character` when they print kana to a cp1252 console. This was reproduced on Python 3.14.

A safe smoke test that needs no credentials, Anki or network: `PYTHONIOENCODING=utf-8 python main.py --seed-kana --dry-run`.

Never read or print `.env`. It holds the real Notion integration secret and is gitignored.

## Code map (`main.py`)

| Area | Functions / constants |
|---|---|
| Config | `NOTION_TOKEN`, `NOTION_DATABASE_ID` (from env via dotenv; the placeholder `PASTE_YOUR_...` defaults are how `sync_ledger` detects missing config), `DECK_ROOT="Nihongo"`, `NOTE_TYPE="Basic"`, `ANKICONNECT_URL` |
| Kana data | `HIRAGANA_*`, `KATAKANA_*` lists of `(kana, romaji)`; `kana_note`, `build_kana_notes`, `seed_kana` |
| Notion | `notion_request` (exits on any HTTP error), `fetch_all_rows` (paginates with `start_cursor`), `get_prop`, `row_to_note` |
| Anki | `anki_request` (exits if AnkiConnect is unreachable; *logs but does not raise* on AnkiConnect errors), `ensure_deck`, `add_or_update_notes` |
| CLI | `main` (argparse: `--dry-run`, `--seed-kana`, `--no-update`) |

`_escape_query_value` is defined but never called. `_GOJUON` is defined and then `del`'d.

### Notion schema the script expects

| Property | Notion type | Used as |
|---|---|---|
| `Item` | title | Front field |
| `Readings` | rich_text | Back, first line |
| `Meaning` | rich_text | Back, joined after readings with `<br>` |
| `Type` | select | Deck `Nihongo::<Type>` plus a lowercase tag (defaults to `Vocab`) |
| `Lesson` | number | Tag `lesson<N>` |

Missing properties quietly become `""`. Changing these names requires editing `row_to_note`.

### How updates work (`add_or_update_notes`)

1. Creates every target deck.
2. `--no-update`: one `addNotes` call; duplicates are rejected by Anki (`allowDuplicate: False`).
3. Default: `findNotes 'note:"Basic"'` then `notesInfo`, which builds a Front-text → note map covering **every Basic note in the whole collection**. For each incoming note with a matching Front:
   - if Back differs: `updateNoteFields` with both fields
   - always: `addTags`
   
   Notes with no match are added in one batch.

Internal keys prefixed with `_` (for example `_notion_page_id`) are stripped before anything is sent to Anki.

## Known issues / review notes

These are ordered by impact. Confirm the user wants a fix before changing behaviour.

1. **Front-text collisions across sources.** Matching uses only the Front text, over all `Basic` notes. If a ledger row's `Item` is a single kana (particles are the usual case: は, を, に, の, も, へ, と, か, ね, よ), then `--seed-kana` overwrites that ledger card's Back with romaji, and the next ledger sync overwrites the kana card. The same applies to any unrelated `Basic` note the user created by hand. Possible fix: scope the lookup query to the managed decks (`deck:"Nihongo::Kana::*"` vs `deck:"Nihongo" -deck:"Nihongo::Kana::*"`), or give the notes their own note type.
2. **Moves and removals are never synced.** Changing a row's `Type` does not move the card to the new deck. Tags are only ever added, so changing `Lesson` leaves the old `lessonN` tag in place. Rows deleted in Notion stay in Anki. `_notion_page_id` is captured but never stored, so it cannot be used as a stable key.
3. **Only Back is diffed.** A tag-only change still triggers `addTags` (which runs for every matched note on every run anyway). Some Anki versions normalise stored field HTML. If that happens, Back never compares equal and the note is re-"updated" on every run.
4. **Multi-word `Type` values break tags.** `"Kanji Compound".lower()` becomes the tag `kanji compound`, which Anki splits into two tags.
5. **`--no-update` counts are unreliable.** Newer AnkiConnect versions make `addNotes` return an error when any note in the batch is a duplicate. `anki_request` then returns `None`, so the script prints "Added 0" even though the non-duplicate notes were added.
6. **Duplicate Fronts inside one batch.** Two ledger rows with the same `Item` both land in `to_add`, and the second one is rejected. If a Front already exists, both rows update the same note and the last one wins.
7. **Empty `Item`** produces a note with an empty Front, which Anki rejects (and in newer AnkiConnect this also triggers #5).
8. **No retry on Notion 429 or 5xx.** Any HTTP error exits the whole run.
9. Pinned to Notion API `2022-06-28` with `/databases/{id}/query`. This still works, but newer API versions move querying to data sources.
10. One HTTP round-trip per matched note (`updateNoteFields` and `addTags`). This is fine at ledger scale. AnkiConnect's `multi` action could batch the calls if speed ever matters.
11. `.env.sample` contains what looks like the author's real database ID instead of a placeholder. It is not a secret without the token, but it is worth replacing.

## Conventions

- Keep it a single, dependency-light script. Use stdlib `urllib` for HTTP.
- Put user-facing errors on `stderr`, and call `sys.exit(1)` for fatal ones.
- Every mode must stay safe to re-run (idempotent) and must support `--dry-run`.
- If you add a CLI flag, update the module docstring's USAGE block and `README.md`.
