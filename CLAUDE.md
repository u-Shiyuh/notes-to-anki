# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A single-file Python CLI (`main.py`) that pushes Japanese study material into Anki through the AnkiConnect add-on. It has two modes:

- **Ledger sync** (default): reads every row of a Notion database (the "Language Learning Ledger") and creates or updates one Anki `Basic` note per row.
- **Kana seed** (`--seed-kana`): writes the built-in hiragana and katakana tables (104 each: gojūon, dakuten/handakuten, yōon) to `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.

There are no tests, no packaging and no `requirements.txt`. The only third-party dependency is `python-dotenv`. HTTP goes through `urllib`.

## Running

```bash
pip install python-dotenv
cp .env.sample .env            # then fill in NOTION_TOKEN / NOTION_DATABASE_ID

python main.py --dry-run               # preview the ledger sync (still calls Notion)
python main.py                         # sync the ledger (Anki must be open)
python main.py --seed-kana --dry-run   # preview the kana seed (no network)
python main.py --seed-kana
python main.py --no-update             # add new notes only; never modify existing ones
python main.py --prune --dry-run       # list linked notes whose Notion row is gone (needs Anki)
```

`main()` reconfigures stdout/stderr to UTF-8, because Windows consoles default to cp1252 and would crash printing kana. Code that imports `main` without calling `main()` (ad-hoc test snippets) still needs `PYTHONIOENCODING=utf-8` on Windows.

A safe smoke test that needs no credentials, Anki or network: `python main.py --seed-kana --dry-run`. `python main.py --dry-run` is read-only against Notion and prints the first five rendered card backs. With Anki open, both dry-runs also read (never write) Anki and list every planned change; that is the safe way to check sync logic against the real collection.

Never read or print `.env`. It holds the real Notion integration secret and is gitignored.

## Code map (`main.py`)

| Area | Functions / constants |
|---|---|
| Config | `NOTION_TOKEN`, `NOTION_DATABASE_ID` (from env via dotenv; `sync_ledger` treats any value containing `paste_your` (any case) as missing), `DECK_ROOT="Nihongo"`, `NOTE_TYPE="Basic"`, `KANA_SCOPE` / `LEDGER_SCOPE` (Anki searches), `LINK_TAG_PREFIX`, `TYPE_TAGS`, `NOTE_OPTIONS` (`duplicateScope: "deck"`), `ANKICONNECT_URL` |
| Kana data | `HIRAGANA_*`, `KATAKANA_*` lists of `(kana, romaji)`; `kana_note`, `build_kana_notes`, `seed_kana` |
| Notion | `notion_request` (retries 429/5xx/network errors with backoff, honouring `Retry-After`; exits on other errors), `fetch_all_rows` (API `2025-09-03`: reads the database's `data_sources`, then pages through `/data_sources/{id}/query`), `get_prop`, `skip_reason`, `row_to_note`, `link_tag` |
| Card layout | `format_back`, `split_note`, `sentences`, `preview_html` (dry-run only) |
| Anki | `anki_request` (exits if AnkiConnect is unreachable; *logs but does not raise* on AnkiConnect errors), `anki_available`, `anki_multi` (batches writes through `multi`), `same_html`, `plan_changes` (read-only), `print_plan`, `summarize`, `preview_changes` (dry-run), `add_or_update_notes` |
| CLI | `main` (argparse: `--dry-run`, `--seed-kana`, `--no-update`, `--prune`; `--prune` is rejected with `--seed-kana` or `--no-update`) |

`_GOJUON` is defined and then `del`'d.

### Notion schema the script expects

| Property | Notion type | Used as |
|---|---|---|
| `Item` | title | Front field |
| `Readings` | rich_text | Back, under the meaning |
| `Meaning` | rich_text | Back, headline |
| `Type` | select | `Kanji` / `Vocab` / `Grammar` / `Grammar Drill`. Deck `Nihongo::<Type>` plus a lowercase tag with spaces → `_` (defaults to `Vocab`); `Grammar` gets prose layout |
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

1. **Scope.** Each mode only reads notes matching `note:"Basic" <scope>`: `KANA_SCOPE` (`Nihongo::Kana` and below) for the seed, `LEDGER_SCOPE` (`Nihongo` minus `Nihongo::Kana`) for the ledger. Notes outside the scope are never matched or changed. `NOTE_OPTIONS` sets `duplicateScope: "deck"` so the same Front can exist in a kana deck and a ledger deck.
2. **In-batch duplicates.** If two incoming notes share deck and Front, only the first is used; the rest are reported under "Not added".
3. **Matching.** Ledger notes carry a `notion_<page id without dashes>` tag (`link_tag`). An incoming note matches the existing note with the same link tag; otherwise an existing note *without* a link tag and with the same Front (this is how pre-link notes and the kana cards match). Each existing note is matched at most once.
4. **Changes for matched notes** (skipped entirely with `--no-update`):
   - Front or Back differs (compared with `same_html`, which ignores entity, whitespace and `style` formatting differences): `updateNoteFields` with both fields. This also applies Item renames.
   - Any card not in the target deck (`getDecks`): `changeDeck`.
   - Tags: missing ones are added. A tag on the note is removed only if the note shouldn't have it *and* the script owns it: `lessonN`, `TYPE_TAGS`, `notion_*`, or any tag the current batch produces. All other tags are the user's and are kept.
5. **Adds.** Unmatched notes are checked with `canAddNotesWithErrorDetail`; only addable ones go to `addNotes`, so counts are accurate and one bad note can't fail the batch. Rejections are listed with Anki's reason.
6. **Prune** (`--prune`, ledger only): linked notes in scope that matched no incoming note are deleted with `deleteNotes`. Unlinked leftovers are listed but never deleted, because they may be hand-made.

All writes except `addNotes` go through `anki_multi` in chunks of `ANKI_MULTI_CHUNK`, in this order: `createDeck`, `updateNoteFields`, `changeDeck`, `addTags`/`removeTags`, `deleteNotes`. Re-running with nothing changed sends no write requests.

## Known issues / review notes

Confirm the user wants a fix before changing behaviour.

1. **Unlinked orphans.** A note whose row was deleted before the note got its `notion_` tag looks the same as a hand-made card, so `--prune` won't delete it (today: `聴く`, whose row became `IGNORE — 聴く`). It must be deleted by hand.
2. **Front fallback can adopt a hand-made card.** A hand-made `Basic` card in a ledger deck whose Front equals a ledger `Item` gets matched once, overwritten and linked. Cards outside `Nihongo` are safe.
3. **Notion result cap.** `/data_sources/{id}/query` stops at 10,000 results per query. The ledger is about 400 rows.
4. **`addNotes` errors are counted, not itemised.** Adds are pre-checked, so this is rare; if `addNotes` itself errors, the run reports one failed request and "Added 0".

## Conventions

- Keep it a single, dependency-light script. Use stdlib `urllib` for HTTP.
- Put user-facing errors on `stderr`, and call `sys.exit(1)` for fatal ones.
- Every mode must stay safe to re-run (idempotent) and must support `--dry-run`.
- If you add a CLI flag, update the module docstring's USAGE block and `README.md`.
