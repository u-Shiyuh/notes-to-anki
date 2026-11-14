# Internals

How `main.py` works: code map, matching and update rules, card layout, the Notion schema, known issues and automation options.
Read before changing `main.py`.

## Code map (`main.py`)

| Area | Functions / constants |
|---|---|
| Config | `NOTION_TOKEN`, `NOTION_DATABASE_ID` (from env via dotenv; `sync_ledger` treats any value containing `paste_your` (any case) as missing), `DECK_ROOT="Nihongo"`, `NOTE_TYPE="Basic"`, `KANJI_DECK`, `TYPE_DECKS` (Type → deck overrides), `VERB_DECK`, `WORD_DECK`, `VOCAB_DECK`, `KANA_SCOPE` / `KANJI_SCOPE` / `VERB_SCOPE` / `WORD_SCOPE` / `VOCAB_SCOPE` / `LEDGER_SCOPE` / `LEDGER_KANJI_SCOPE` (Anki searches; `_LINKED` is `tag:notion\_*`, escaped because `_` is a wildcard in Anki search), `KANJI_FILE`, `VERB_FILE`, `WORD_FILE`, `LINK_TAG_PREFIX`, `TYPE_TAGS`, `NOTE_OPTIONS` (`duplicateScope: "deck"`), `ANKICONNECT_URL` |
| Kana data | `HIRAGANA_*`, `KATAKANA_*` lists of `(kana, romaji)`; `kana_note`, `build_kana_notes`, `seed_kana` |
| Kanji seed | `load_kanji` (parses `KANJI_FILE` or `KANJI_EXTRA_FILE`), `core_kanji` (cached rows of `KANJI_FILE` + `KANJI_EXTRA_FILE` by kanji), `kanji_key` (Front up to the first space, so `万 (man, 10000)` counts as `万`; used for layout lookup, adoption and `without_ledger_kanji`), `kanji_readings`, `example_word` (the on'yomi example line), `radicals` (cached `RADICAL_FILE` rows by `no|form`), `radical_line`, `kanji_back` (the Core Kanji Back layout, shared with ledger kanji), `kanji_note` (adds the `kanji`/`core_kanji`/`jlpt_nN` tags), `without_ledger_kanji`, `seed_kanji` |
| Verb seed | `VERB_GROUPS`, `_GODAN_STEM` / `_GODAN_NAI` / `_GODAN_TA` / `_IRREGULAR`, `load_verbs` (exits on a row whose forms can't be built), `conjugations`, `masu_form`, `conjugation_lines`, `radicals_lines` (the shared faded Radical(s) line), `verb_radicals_line` (uses `radical_text`, shared with `radical_line`), `verb_back`, `verb_note` (tags `verb`, the group, `section<N>`), `seed_verbs` |
| Word seed | `WORD_TYPE_TAGS`, `load_words`, `kanji_card_covers`, `seeded_words` (cached), `word_back` (radicals via `text_radicals_line`), `word_note` (tags `word`, the type, `jlpt_nN`, `katakana`), `seed_words` |
| Notion | `notion_request` (retries 429/5xx/network errors with backoff, honouring `Retry-After`; exits on other errors), `fetch_all_rows` (API `2025-09-03`: reads the database's `data_sources`, then pages through `/data_sources/{id}/query`), `get_prop`, `skip_reason`, `row_to_note`, `link_tag` |
| Card layout | `format_back`, `split_note`, `sentences`, `preview_html` (dry-run only) |
| Anki | `anki_request` (exits if AnkiConnect is unreachable; *logs but does not raise* on AnkiConnect errors), `anki_available`, `anki_multi` (batches writes through `multi`), `find_notes`, `same_html`, `plan_changes` (read-only), `print_plan`, `summarize`, `preview_changes` (dry-run), `add_or_update_notes` |
| Look-alikes seed | `load_lookalikes` (exits on a kanji with no Core Kanji row), `studied_kanji`, `main_readings`, `_telling_parts`, `lookalike_back`, `lookalike_note` (tag `lookalike`), `seed_lookalikes` |
| Numbers seed | `NUMBER_GROUPS`, `load_numbers` (exits on a row with an unknown group or a missing front/reading/meaning), `number_back` (radicals via `text_radicals_line`), `number_note` (tags `numbers` + group), `seed_numbers` |
| Source tags | `REFERENCE_FILE` (`references.tsv`), `REF_TAG_PREFIX`, `references`, `ref_tags`, `verb_source` |
| Sentence seed | `SENTENCE_DECK`, `SENTENCE_FILE`, `load_sentences`, `_word_glosses`, `sentence_word_line`, `sentence_back`, `sentence_note`, `seed_sentences`; shared with `--order` and the tools: `EXAMPLES_FILE`, `SENTENCE_GRAMMAR`, `example_sentences`, `WordSet`, `studied_words`, `sentence_unlocks` |
| CLI | `main` (argparse: `--dry-run`, `--seed-kana`, `--seed-kanji`, `--seed-verbs`, `--seed-words`, `--seed-numbers`, `--seed-lookalikes`, `--order`, `--no-update`, `--prune`; the five seeds and `--order` are mutually exclusive, and `--prune` is rejected with any seed or with `--no-update`) |

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

The database also has `Status`, `Attempts`, `Correct Streak` and `Last Reviewed`, which the script ignores. They predate Anki and are stale: nothing has updated them since 2026-09-22, and the sync is one-way (Notion → Anki). Anki is the record of study progress; don't read progress from these columns. Missing properties quietly become `""`. Changing these names requires editing `row_to_note` / `skip_reason`.

Rows are skipped (and reported) when `Item` is empty, starts with `IGNORE` (`SKIP_PREFIX`), or has a different `Language`.

### Card back layout (`format_back`)

The Back field is HTML with inline styles only, so it works with the stock `Basic` note type and in Anki's night mode (notes are faded with `opacity`, not a colour). The Front is sent as the raw `Item` text. It is the fallback matching key for notes that don't have a link tag yet (see below), so keep it raw.

- **Kanji / Vocab:** each of `Meaning` and `Readings` is split on the first `" — "` (`NOTE_SEP`) into core and side note. The first sentence of the meaning is a bold headline, any further meaning sentences follow on their own lines, then the core readings, then the side notes in small, faded text.
- **Kanji in `kanji_top1000.tsv`:** a ledger `Kanji` row whose `Item` (by `kanji_key`) is one of the 1,000 or in `kanji_extra.tsv` gets the Core Kanji layout (`kanji_back`): its own meaning headline, the file's on line, example word and kun line, its `—` side notes, then strokes, JLPT and rank. The row's `Readings` core text is dropped in favour of the file's readings. Other `Kanji` rows use the Kanji/Vocab layout. (Added 2026-10-28; before that, ledger kanji kept the plain layout after the deck merge.)
- **Grammar Drill** (short practice rows: prompt in `Item`, answer in `Meaning`, reason in `Readings`) uses the Kanji/Vocab layout and lands in `Nihongo::Grammar Drill`. The long `Grammar` rows are reference notes.
- **Grammar:** `Meaning` then `Readings` are split into sentences (`_SENTENCE_BREAK`, which ignores `e.g.`, `i.e.`, `vs.`, `etc.`). The first sentence is the headline and the rest go one per line.

All text is HTML-escaped. Changing `format_back` changes every Back field, so the next default (updating) sync rewrites every existing note once.

### How updates work (`plan_changes` → `add_or_update_notes`)

`plan_changes` is read-only and returns a plan. `add_or_update_notes` prints it and applies it; `--dry-run` prints it via `preview_changes` (only if Anki is reachable).

1. **Scope.** Each mode only reads notes matching `note:"Basic" <scope>`: `KANA_SCOPE` (`Nihongo::Kana` and below) for the kana seed, `KANJI_SCOPE` (unlinked notes in `Nihongo::Core Kanji`) for the kanji seed, `VERB_SCOPE` (`Nihongo::Verbs`) for the verb seed, `WORD_SCOPE` (`Nihongo::Words`) for the word seed, `LEDGER_SCOPE` (`Nihongo` minus `Nihongo::Kana`, `Nihongo::Verbs`, `Nihongo::Words` and `KANJI_SCOPE`) for the ledger. Notes outside the scope are never matched or changed, with one exception: adoption (step 3). `NOTE_OPTIONS` sets `duplicateScope: "deck"` so the same Front can exist in a kana deck and a ledger deck.
2. **In-batch duplicates.** If two incoming notes share deck and Front, only the first is used; the rest are reported under "Not added".
3. **Matching.** Ledger notes carry a `notion_<page id without dashes>` tag (`link_tag`). An incoming note matches the existing note with the same link tag; otherwise an existing note *without* a link tag and with the same Front (this is how pre-link notes and the kana cards match). Each existing note is matched at most once.
   - **Adoption** (`adopt=(scope, deck, key)` on `plan_changes`). The word and verb seeds adopt from `VOCAB_SCOPE` by exact Front (see Word seed above); the ledger sync adopts kanji as follows. A ledger `Kanji` note that matched nothing takes over the seed's `Nihongo::Core Kanji` note with the same Front. That note then goes through the normal update path, so it's rewritten and gets its link tag (it's already in the right deck), and its review history is kept. Its `core_kanji`/`jlpt_nN` tags aren't owned by the ledger, so they stay. Only `Kanji`-type rows adopt; a `Vocab` row `会` doesn't take over the Core Kanji `会` card. Once the note is linked, it leaves `KANJI_SCOPE`. `without_ledger_kanji` checks `LEDGER_KANJI_SCOPE` (linked `kanji` notes anywhere under `Nihongo`, even before the sync has moved them) so the seed doesn't re-add the kanji.
4. **Changes for matched notes** (skipped entirely with `--no-update`):
   - Front or Back differs (compared with `same_html`, which ignores entity, whitespace and `style` formatting differences): `updateNoteFields` with both fields. This also applies Item renames.
   - Any card not in the target deck (`getDecks`): `changeDeck`.
   - Tags: missing ones are added. A tag on the note is removed only if the note shouldn't have it *and* the script owns it: `lessonN`, `TYPE_TAGS`, `notion_*`, or any tag the current batch produces. All other tags are the user's and are kept.
5. **Adds.** Unmatched notes are checked with `canAddNotesWithErrorDetail`; only addable ones go to `addNotes`, so counts are accurate and one bad note can't fail the batch. Rejections are listed with Anki's reason. A "deck was not found" error doesn't count as a rejection, because the run creates missing decks before adding.
6. **Prune** (`--prune`, ledger only): linked notes in scope that matched no incoming note are deleted with `deleteNotes`, except those in `keep` (Vocab rows handed over to a file). Unlinked leftovers are listed but never deleted, because they may be hand-made.

All writes except `addNotes` go through `anki_multi` in chunks of `ANKI_MULTI_CHUNK`, in this order: `createDeck`, `updateNoteFields`, `changeDeck`, `addTags`/`removeTags`, `deleteNotes`. Re-running with nothing changed sends no write requests.

## Known issues / review notes

Confirm the user wants a fix before changing behaviour.

1. **Unlinked orphans.** A note whose row was deleted before the note got its `notion_` tag looks the same as a hand-made card, so `--prune` won't delete it. It must be deleted by hand. (The one known case, a lesson-3 `聴く`, was deleted on 2026-10-28; `--prune --dry-run` now lists none.)
2. **Front fallback can adopt a hand-made card.** A hand-made `Basic` card in a ledger deck whose Front equals a ledger `Item` gets matched once, overwritten and linked. Cards outside `Nihongo` are safe.
3. **Notion result cap.** `/data_sources/{id}/query` stops at 10,000 results per query. The ledger is about 400 rows.
4. **Core Kanji is a snapshot.** Kanji that already had a ledger card when the seed ran are skipped (110 on 2026-10-27). If such a ledger row is later deleted and pruned, the next `--seed-kanji` adds that kanji back as a fresh Core Kanji card.
5. **`addNotes` errors are counted, not itemised.** Adds are pre-checked, so this is rare; if `addNotes` itself errors, the run reports one failed request and "Added 0".
6. **Cards in a filtered deck count as misplaced.** `getDecks` reports a card in a Custom Study Session under the filtered deck, so an updating seed plans a `changeDeck` that would pull it out of the session (seen 2026-11-09 with 貸す, 使う). Use `--no-update` while a session is open, or empty the session first.

## How the ledger sync was used

(Historical, until 2026-11-06; the sync is now disabled.) The ledger sync runs over and over, not once. The user adds a row to Notion whenever they learn a new kanji, word or grammar point, then runs `python main.py`. That adds the new cards and keeps existing ones in line with Notion without touching review history. The kana and kanji seeds are meant to run once, because their tables don't change. The verb seed runs again each time a section is appended to `verbs.tsv`, and the word seed after `words.tsv` changes. All are safe to re-run.

As of 2026-10-19, every ledger note in the real collection carries its `notion_` link tag. So the Front-text fallback match only applies to notes created by hand or by older versions of the script.

### Automation

The script can't run on GitHub-hosted Actions. AnkiConnect is an HTTP server inside the desktop Anki app at `127.0.0.1:8765`, so a cloud runner can't reach it, and AnkiWeb has no official API for adding cards. The options considered, best first:

1. **A scheduled task on the user's computer** runs `python main.py` on a schedule. If Anki is closed the run fails harmlessly and the next one catches up. Anki's own AnkiWeb sync then carries the cards to other devices. This is the recommended option. It isn't set up yet.
   - **Windows:** Task Scheduler.
   - **macOS:** a `launchd` agent (a plist in `~/Library/LaunchAgents` with `StartCalendarInterval`), which, unlike `cron`, runs a missed job after the Mac wakes. Use `python3`. App Nap must be disabled for Anki (see README), or a background Anki stops answering AnkiConnect and every scheduled run fails.
2. **A self-hosted GitHub runner** on the same PC. It only works while the PC is on and Anki is open, so it's option 1 with more setup.
3. **A cloud Action that builds an `.apkg`** for the user to import by hand. It needs no PC, but every import is manual and it would add a second, non-AnkiConnect code path.
4. **A cloud Action that syncs through AnkiWeb** with Anki's Python library. Avoid this: it's unofficial, needs the AnkiWeb password stored as a secret, and can force a full sync that overwrites same-day reviews made on other devices.

## Full command reference (from the old CLAUDE.md)

```bash
pip install python-dotenv
cp .env.sample .env            # then fill in NOTION_TOKEN / NOTION_DATABASE_ID

python main.py --dry-run               # preview the ledger sync (still calls Notion)
python main.py                         # sync the ledger (Anki must be open)
python main.py --seed-kana --dry-run   # preview the kana seed (no network)
python main.py --seed-kana
python main.py --seed-kanji --dry-run  # preview the kanji seed (reads Anki if open)
python main.py --seed-kanji
python main.py --seed-verbs --dry-run  # preview the verb seed (reads Anki if open)
python main.py --seed-verbs
python main.py --seed-words --dry-run  # preview the word seed (reads Anki if open)
python main.py --seed-words
python main.py --seed-numbers --dry-run # preview the numbers seed (reads Anki if open)
python main.py --seed-numbers
python main.py --seed-lookalikes --dry-run  # preview look-alike pairs of studied kanji (needs Anki)
python main.py --seed-lookalikes
python main.py --order --dry-run        # report what the study-order step would move
python main.py --order                  # kanji met in studied words first, then words whose kanji are studied
python main.py --no-update             # add new notes only; never modify existing ones
python main.py --prune --dry-run       # list linked notes whose Notion row is gone (needs Anki)
```

It runs on Windows (the user's current machine) and macOS; on macOS use `python3`/`pip3`. `main()` reconfigures stdout/stderr to UTF-8, because Windows consoles default to cp1252 and would crash printing kana. Code that imports `main` without calling `main()` (ad-hoc test snippets) still needs `PYTHONIOENCODING=utf-8` on Windows.

A safe smoke test that needs no credentials, Anki or network: `python main.py --seed-kana --dry-run`. `python main.py --dry-run` is read-only against Notion and prints the first five rendered card backs. With Anki open, both dry-runs also read (never write) Anki and list every planned change; that is the safe way to check sync logic against the real collection.

Never read or print `.env`. It holds the real Notion integration secret and is gitignored.

A non-dry run writes to the user's real Anki collection, so ask before running one. To test write paths, point `ANKICONNECT_URL` at a small in-memory fake AnkiConnect (a stdlib `HTTPServer` that implements the actions the script uses) instead of the real one.
