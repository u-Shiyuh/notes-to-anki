# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A single-file Python CLI (`main.py`) that pushes Japanese study material into Anki through the AnkiConnect add-on. It has two modes:

**Notion sync disabled (2026-11-06).** The user said the Notion ledger is outdated; Anki is the source of truth. `NOTION_SYNC_ENABLED = False` in `main.py` makes a run without a `--seed-*` option exit 1 before touching Notion or Anki (`--prune` with it). Don't re-enable it or run the ledger sync unless the user asks. The same day, at the user's request, the ledger's `Nihongo::Grammar` (35 notes) and `Nihongo::Grammar Drill` (168 notes, 23 studied) decks were deleted from Anki, after exporting both with scheduling to `~/Documents/anki-backups/` on the Mac. Also on 2026-11-06 (user's request), the 121 ledger `Kanji` notes in `Nihongo::Core Kanji` were converted to seed notes: their `notion_` and `lessonN` tags were removed, then `--seed-kanji` matched them by Front and rewrote them in the standard layout, dropping their Notion headlines and side notes (the user didn't want them) and keeping review history. Core Kanji is now 1,017 seed notes; no `notion_`-tagged notes remain anywhere. A backup of the deck before this is in `~/Documents/anki-backups/`. `python-dotenv` is now optional (only the sync reads `.env`).

- **Ledger sync** (default): reads every row of a Notion database (the "Language Learning Ledger") and creates or updates one Anki `Basic` note per row.
- **Kana seed** (`--seed-kana`): writes the built-in hiragana and katakana tables (104 each: gojūon, dakuten/handakuten, yōon) to `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.
- **Kanji seed** (`--seed-kanji`): writes the 1,000 most frequent kanji from `kanji_top1000.tsv`, then the rows of `kanji_extra.tsv`, to `Nihongo::Core Kanji`, in frequency order. It skips kanji that already have a ledger card. Ledger `Kanji` rows also live in `Nihongo::Core Kanji` (`TYPE_DECKS`; merged on 2026-10-27, so `Nihongo::Kanji` is now unused). Inside that deck, a `notion_` link tag marks a ledger note, and its absence marks a seed note.

- **Verb seed** (`--seed-verbs`): writes the verbs in `verbs.tsv` to `Nihongo::Verbs`, in file (book) order. A verb with a ledger card in `Nihongo::Vocab` takes it over (see "One owner per word" below).

- **Word seed** (`--seed-words`): writes the words in `words.tsv` to `Nihongo::Words`, in file order (added 2026-11-03). `seeded_words` drops two kinds of row: verbs that are in `verbs.tsv`, and one-kanji words their Core Kanji card covers (`kanji_card_covers`: the word's kana is the kanji's main bold reading, the first `*` on its On or Kun line; 147 on 2026-11-03, while 9 such as 後 あと keep a card). It adopts the matching `Nihongo::Vocab` ledger card (`adopt=(VOCAB_SCOPE, WORD_DECK, str.strip)`), so the card moves to Words, loses its `notion_`/`lessonN`/`vocab` tags and keeps its history. The verb seed adopts from Vocab the same way.

- **Numbers seed** (`--seed-numbers`, added 2026-11-06): writes `numbers.tsv` to `Nihongo::Numbers & Time` (one deck; the user wanted one subdeck, with groups as tags rather than sub-subdecks). Cards are expressions in real-world formats, Arabic digits as usually written (`3本`, `4階`, `午後2時`, `2:30 PM`, `3月14日`, `¥1,980`); the Back's bold headline is the reading, because reading the format is the skill. Columns: `group` (validated against `NUMBER_GROUPS`; becomes a tag next to `numbers`), `front`, `kana`, `meaning`, `note`. Hand-made, N5/N4. Single vocabulary words (一人, 二日, 去年, 毎日, weekdays, 〜本) stay in `words.tsv`; Fronts don't collide because Words uses kanji numerals. `tools/check_data.py` checks each small number + counter (3本 → 三本) against JMdict's readings (77 of 161 rows on 2026-11-06); clock times, prices and phrases are compositional and checked by hand.

- **Study order** (`--order`, added 2026-11-11): Words runs in word-frequency order and Core Kanji in kanji-frequency order, so 71% of the words studied by 2026-11-11 used a kanji not yet studied (kanji, reading and meaning learned at once; the Words review pass rate was 41%). `--order` runs `order_kanji` then `order_words`. `order_kanji` moves the new Core Kanji cards whose kanji appear in a studied Words, Verbs or Numbers & Time card (`STUDIED_WORD_DECKS`) to the front, tagged `word_seen` (`SEEN_TAG`). `order_words` moves the new Words cards whose kanji all have a studied Core Kanji card, and kana-only words, to the front, tagged `kanji_ready` (`READY_TAG`). Both keep each group's existing relative order (so N5/N4 kanji stay first) and untag cards that no longer qualify; the seeds don't own these tags. AnkiConnect refuses to set a card's `due` ("Use native scheduling commands for protected state") and has no reposition action, so the move goes through **the helper add-on in `anki_addon/notes_to_anki_helper/`**: it serves Anki's own `sched.reposition_new_cards` (randomize off, shift existing) on `127.0.0.1:8766` (`HELPER_URL`), only for new cards, as an undoable `CollectionOp` with no review-log entries. Install it once per machine as a symlink in Anki's `addons21` folder (README); it loads when Anki starts. Installed on the Mac on 2026-11-11 (at the user's request); the Windows PC still needs it. Without it, `_front_load` opens the cards in the browser for a manual Cards > Reposition. Run `--order` during each sync. Recommended alongside it: Core Kanji 10 new/day and Words 3 (Core Kanji shares the `Default` preset with Verbs and Numbers & Time, so it needs its own preset); re-check the Words pass rate around 2026-11-25 before splitting Words into reading and meaning cards.

**Topics** (added 2026-11-06). `words.tsv` column 7 `topic` (19 topics, one per word, ~460 words; abstract words have none) becomes a `topic_<name>` tag (`TOPIC_TAG_PREFIX`). `kanji_topics` gives a Core Kanji card the topic of the one-kanji word it covers (83 kanji), since the word seed skips those words. Tags starting `topic_` are script-owned, so a changed topic replaces the old tag. The initial assignment came from `tools/topics_data.py` via `tools/assign_topics.py` (which only rewrites rows whose topic changes, and appended 10 everyday non-JLPT words with a blank level: ピンク オレンジ 紫 灰色 金色 銀色 肩 胸 膝 腰); afterwards edit topics in `words.tsv` directly. The user studies a topic via Custom Study by tag, not separate decks (rejected: moving hundreds of cards and splitting the new-card order).

**One owner per word.** A ledger `Vocab` row whose Item is in `seeded_words()` or `verbs.tsv` is skipped by `sync_ledger` (one summary line) and its link tag goes in `keep`, so `--prune` doesn't delete the card before the seed adopts it. New Notion words outside the files still sync to `Nihongo::Vocab`. On 2026-11-03, 60 rows were handed over: 54 words, plus 6 verbs (聞く 読む 飲む 話す 書く 行く) whose Vocab cards duplicate existing Verbs cards and must be deleted by hand once. 洗う 寝る 見る 帰る 食べる 来る were to stay in Vocab until the book's ichidan/irregular section adds them to `verbs.tsv`, but on 2026-11-09 they had no card anywhere in Anki, and the empty `Nihongo::Vocab` deck was deleted (user's request). They aren't studied until they're added to `verbs.tsv`; sections 2 and 3 brought 食べる 寝る 見る 来る (and する), and the `extra` section 洗う and 帰る.

`words.tsv` is generated data (columns `level` n5/n4/blank, `word`, `kana`, `meaning`, `type`, `note`). It was built on 2026-11-03 from open-anki-jlpt-decks N5/N4 (MIT, on Waller's CC BY lists) plus JMdict (CC BY-SA 4.0) for part of speech and the nf frequency that orders each level. Words that had a Notion Vocab card keep that card's meaning and notes; the 15 Notion-only words go first (greetings), except the 5 travel words, which the user moved to the very end on 2026-11-04 (the 3 started ones were reset to new). Verbs are excluded. Multi-form source entries (足; 脚) were hand-mapped to one Front with an "also" note. The first word using each kana feature the kana decks lack (small っ/ッ, ー, ティ, ファ…) gets an explanation in its note. The generator was never committed and is lost; it matched kana-only words to JMdict by reading alone, so 10 kana-only rows got a homonym's part of speech (はく as 伯/箔 "noun" instead of 履く, そこ with 底's "bottom, sole" gloss). They were fixed on 2026-11-06 with `tools/check_data.py`. はく stays in this file as type `verb` (it isn't in the book's verbs yet). Hand edits to rows are fine. Keep the header's attribution.

`verbs.tsv` is hand-made from the user's reviewer book (added 2026-11-03; section 1 = the book's 87 godan verbs; section 2 = its 65 ichidan verbs, added 2026-11-09 as 64 rows: #15 and #16 are both かける and share one row, since a deck can't hold two cards with the same Front; 減る is godan though the book lists it here; いる's gloss was changed from the book's "to need; to be" to "to be; to exist", because 要る "to need" is a different, godan verb, and the note says so; section 3 = its irregular verbs, added 2026-11-09: する and 来る as `no` 1-2, then the book's 39 する-verbs as `no` c1-c39, since the book numbers that list separately). Two section-3 verbs already had Words cards (勉強する, studied, and けんかする); both cards were moved to `Nihongo::Verbs` by hand and their word tags removed, so the verb seed took them over with their history. Their `words.tsv` rows stay and are skipped like any verb in `verbs.tsv`. 29 of the する-verbs' nouns (結婚, 料理…) still have their own Words cards. After section 3, an `extra` section (user's request, 2026-11-09) holds 25 JLPT N5 verbs the book's sections lack (洗う 帰る 分かる なる…), taken from `sources/n5.csv`; its `#` header says where they came from. If a later book section has one of them, move the row there (the card follows by Front). Columns: `section`, `no` (book number), `word` (as printed, so つく/ある/やる are kana), `kana`, `meaning` (the book's gloss), `group` (`godan`/`ichidan`/`irregular`), `masu` (overrides the built ます-form; normally blank), `note` (faded line: irregular forms, transitive/intransitive pairs, look-alikes), `radicals` (`kanji:no|form` per kanji, space-separated, e.g. 手伝う `手:64|手 伝:9|亻`; set by `tools/add_radicals.py`, blank for kana-only verbs). Missing trailing columns count as blank. The book's later sections are appended as the user sends them; run `tools/add_radicals.py --write` after appending. Since 2026-11-08 (user's request) the card shows the ます/ない/た/て forms (`conjugations`: godan by ending, ichidan, and irregular verbs ending in する/来る/くる; exceptions 行く/〜いく → 行った/行って and ある → ない) on two lines under the reading, and a faded `Radical(s):` line (`verb_radicals_line`) after the note; unlike Core Kanji cards it also shows a kanji that is its own radical (行). Many verb kanji (泳 泣 磨…, 15 on 2026-11-08) aren't in the kanji files, which is why verbs carry their own column.

`kanji_extra.tsv` holds, in the same columns, kanji outside the top 1,000: every JLPT N5/N4 kanji the top 1,000 misses (all 79 N5 are in it; 15 N4 aren't) and the ledger kanji outside it. 17 rows on 2026-10-29: 耳魚姉兄弟妹冬寒 (ledger, added 2026-10-28) and 犬牛茶鳥漢勉昼飯堂 (N4, added 2026-10-29), built from kanji-data alone (漢's "China" capitalised by hand). The seed adds them after the top 1,000 (skipping those with a ledger card), and ledger kanji in it get the Core Kanji layout. A new ledger kanji outside both files keeps the plain layout until a row is added here.

**Radicals** (added 2026-11-07). Both kanji files have a 9th column `radical`, `no|form` (Kangxi number and the shape in that kanji: 海 `85|氵`, 泉 `85|水`), set by `tools/add_radicals.py` from KANJIDIC2's classical radical, with KRADFILE's parts picking the variant form (its stand-ins like 汁 = 氵 are mapped in `VARIANTS`). `radicals.tsv` (181 rows: no, form, name, meaning, kanji count) holds one row per form used; names and meanings were written by hand on 2026-11-07 (meanings started from the Unicode radical names). `kanji_back` adds a faded `Radical: 氵 さんずい · water` line above the strokes line (`radical_line`), omitted when the kanji is its own radical (86 kanji). The user decided against a separate radical deck for now (N4 doesn't test radicals; the count column is there to order one later, around N3). Note the official radical can differ from the visible part (問 and 聞 are filed under 口 and 耳, not 門).

`kanji_top1000.tsv` is generated data. It was built once from KANJIDIC2 (CC BY-SA 4.0: frequency, readings, meanings, strokes) and kanji-data (MIT: JLPT N-levels and WaniKani's reading order). Its `#` header lists the sources and formatting rules. A leading `*` marks each kanji's most common on/kun reading, which comes first in its list. Since 2026-11-09 (user's request: the kanji card faded readings their Words/Verbs cards teach, e.g. 後 あと) any other reading on the line that an N5/N4 word in `words.tsv` or a verb in `verbs.tsv` uses is also `*` and follows it (49 lines). `kanji_readings` renders the leading `*` run bold and fades the rest. By hand that day: 後's duplicate うしろ removed, and 何's lone on'yomi カ unmarked (faded; it's almost never used). A line with no marked reading is faded entirely, even a lone reading (since 2026-10-29; before, a lone reading was bold, which made rare ones like 万's よろず look essential): about 133 kun lines and 5 on lines. The 8th column, `example` (`word|kana|gloss|level`), is a word that reads the kanji with one of its on'yomi; `example_word` shows it, with the word's JLPT level, under the On line. It's the easiest JLPT word (N5 first, from open-anki-jlpt-decks, MIT, built on Jonathan Waller's CC BY lists), the main on'yomi winning ties; with no JLPT word, the most frequent common JMdict word (EDRDG, CC BY-SA 4.0) and a blank level. JmdictFurigana (CC BY-SA 4.0) says which kana belong to which kanji. Across both files (1,017 kanji, 2026-10-29): 156 N5, 149 N4, 442 N3, 180 N2/N1, 70 unlevelled, and 20 kanji (mostly name kanji like 藤, 岡) with none. The generators were never committed and are lost. To change the list, regenerate the file with the same columns rather than hand-editing 1,000 rows. Keep the attribution in the header and README.

## Data tools (`tools/`)

- **Rule: generator and checker scripts live in `tools/` and are committed. Never leave one only in a session scratchpad** (that is how the original `words.tsv` and kanji generators were lost). Downloaded source data goes in `tools/cache/`, which is gitignored.
- Pin every source (a commit hash or release tag in the script), so reruns are reproducible.
- Source data the tools read is committed in `sources/` (with attribution in `sources/README.md`): the JLPT N5/N4 CSVs as-is, and `jmdict-subset.json`, only the JMdict entries for words in `words.tsv`/`verbs.tsv` (the full JMdict is 11 MB zipped). JMdict is CC BY-SA 4.0, so the subset stays CC BY-SA with EDRDG attribution; don't drop the notices. After adding rows to either `.tsv`, run `python3 tools/check_data.py --refresh` to rebuild `sources/`; without it the checker falls back to downloading the full JMdict and says so.
- The `.tsv` files are the source of truth: they carry hand edits no generator reproduces. Tools check them or propose new rows; they never overwrite a `.tsv` wholesale.
- `tools/mark_readings.py` sets the bold `*` reading in both kanji files (dry run by default, `--write` to apply). It reimplements the lost generator's WaniKani rule (via kanji-data, pinned commit) and fixes its bug: where WaniKani teaches none of a kanji's on'yomi (all `!` in kanji-data), the original bolded the first-listed one, which is arbitrary (読 トウ, 夏 ゲ); now the on'yomi used by the most common JMdict words wins (JmdictFurigana). On 2026-11-06 it changed 6 lines (読 頭 色 夏 on, 終 帯 kun), and 夏's example became 夏季 by hand. **WaniKani is retained by the user's choice (2026-11-06) but should be replaced if a better openly licensed alternative turns up, and must be before any paid use** (WaniKani content is proprietary; kanji-data's MIT licence can't cover it). A pure word-frequency rule was tested and is worse for kun'yomi (上 あ(げる), 入 い(る)). It also marks the readings learned words use (see `kanji_top1000.tsv` above); rerun it with `--write` after adding words or a verb section. (Ledger kanji cards used to be skipped by `--seed-kanji`; since their conversion on 2026-11-06 it updates all 1,017.)
- `tools/add_radicals.py` sets the kanji files' `radical` column and `verbs.tsv`'s `radicals` column, and appends any missing form to `radicals.tsv` (blank name, Unicode meaning; dry run by default, `--write` to apply). It never changes existing `radicals.tsv` rows except their derived kanji count. Same pinned jmdict-simplified release as `check_data.py`.
- **Consistency across decks** (user, 2026-11-11): every deck, and any future subdeck, uses the same meaning style as the Core Kanji cards, and a word on two decks must agree. Word meanings: a short comma list, the common sense first, short usage tags only where they matter (`(my)`, `(polite)`, `(weather)`, `(with neg.)`), ` / ` between unrelated homonyms, and etymology, examples and grammar in the `note` column. `tools/clean_meanings.py` applied this to 277 fields of `words.tsv` on 2026-11-11, also fixing wrong glosses (あちら "this way", 口 "job opening", 厚い "kind", バス "bath; bass") and 勉強する's kana. `tools/dedupe_readings.py` removed 33 duplicate readings from the kanji files, where KANJIDIC2 lists a reading with and without okurigana marks (行 -い(き) and -いき); a bold reading is kept over a plain one. Both are dry run by default, and `--write` applies.
- `tools/check_data.py` (read-only) checks `words.tsv` (each row's `type` against JMdict's part of speech for the best-matching entry, preferring usually-kana entries for kana-only words; levelled rows against the JLPT N5/N4 lists) and `verbs.tsv` (each `group` against JMdict; a する-verb like 勉強する or 世話をする is checked by its noun, which must take する, `vs`). Exit status 1 if anything is flagged. Run it after editing either file: `python3 tools/check_data.py`. It needs no network while `sources/` covers every row. After those fixes it flagged nothing (2026-11-06).

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
python main.py --seed-verbs --dry-run  # preview the verb seed (reads Anki if open)
python main.py --seed-verbs
python main.py --seed-words --dry-run  # preview the word seed (reads Anki if open)
python main.py --seed-words
python main.py --seed-numbers --dry-run # preview the numbers seed (reads Anki if open)
python main.py --seed-numbers
python main.py --order --dry-run        # report what the study-order step would move
python main.py --order                  # kanji met in studied words first, then words whose kanji are studied
python main.py --no-update             # add new notes only; never modify existing ones
python main.py --prune --dry-run       # list linked notes whose Notion row is gone (needs Anki)
```

It runs on Windows (the user's current machine) and macOS; on macOS use `python3`/`pip3`. `main()` reconfigures stdout/stderr to UTF-8, because Windows consoles default to cp1252 and would crash printing kana. Code that imports `main` without calling `main()` (ad-hoc test snippets) still needs `PYTHONIOENCODING=utf-8` on Windows.

A safe smoke test that needs no credentials, Anki or network: `python main.py --seed-kana --dry-run`. `python main.py --dry-run` is read-only against Notion and prints the first five rendered card backs. With Anki open, both dry-runs also read (never write) Anki and list every planned change; that is the safe way to check sync logic against the real collection.

Never read or print `.env`. It holds the real Notion integration secret and is gitignored.

A non-dry run writes to the user's real Anki collection, so ask before running one. To test write paths, point `ANKICONNECT_URL` at a small in-memory fake AnkiConnect (a stdlib `HTTPServer` that implements the actions the script uses) instead of the real one.

## How it's used

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

## Code map (`main.py`)

| Area | Functions / constants |
|---|---|
| Config | `NOTION_TOKEN`, `NOTION_DATABASE_ID` (from env via dotenv; `sync_ledger` treats any value containing `paste_your` (any case) as missing), `DECK_ROOT="Nihongo"`, `NOTE_TYPE="Basic"`, `KANJI_DECK`, `TYPE_DECKS` (Type → deck overrides), `VERB_DECK`, `WORD_DECK`, `VOCAB_DECK`, `KANA_SCOPE` / `KANJI_SCOPE` / `VERB_SCOPE` / `WORD_SCOPE` / `VOCAB_SCOPE` / `LEDGER_SCOPE` / `LEDGER_KANJI_SCOPE` (Anki searches; `_LINKED` is `tag:notion\_*`, escaped because `_` is a wildcard in Anki search), `KANJI_FILE`, `VERB_FILE`, `WORD_FILE`, `LINK_TAG_PREFIX`, `TYPE_TAGS`, `NOTE_OPTIONS` (`duplicateScope: "deck"`), `ANKICONNECT_URL` |
| Kana data | `HIRAGANA_*`, `KATAKANA_*` lists of `(kana, romaji)`; `kana_note`, `build_kana_notes`, `seed_kana` |
| Kanji seed | `load_kanji` (parses `KANJI_FILE` or `KANJI_EXTRA_FILE`), `core_kanji` (cached rows of `KANJI_FILE` + `KANJI_EXTRA_FILE` by kanji), `kanji_key` (Front up to the first space, so `万 (man, 10000)` counts as `万`; used for layout lookup, adoption and `without_ledger_kanji`), `kanji_readings`, `example_word` (the on'yomi example line), `radicals` (cached `RADICAL_FILE` rows by `no|form`), `radical_line`, `kanji_back` (the Core Kanji Back layout, shared with ledger kanji), `kanji_note` (adds the `kanji`/`core_kanji`/`jlpt_nN` tags), `without_ledger_kanji`, `seed_kanji` |
| Verb seed | `VERB_GROUPS`, `_GODAN_STEM` / `_GODAN_NAI` / `_GODAN_TA` / `_IRREGULAR`, `load_verbs` (exits on a row whose forms can't be built), `conjugations`, `masu_form`, `conjugation_lines`, `verb_radicals_line` (uses `radical_text`, shared with `radical_line`), `verb_back`, `verb_note` (tags `verb`, the group, `section<N>`), `seed_verbs` |
| Word seed | `WORD_TYPE_TAGS`, `load_words`, `kanji_card_covers`, `seeded_words` (cached), `word_back`, `word_note` (tags `word`, the type, `jlpt_nN`, `katakana`), `seed_words` |
| Notion | `notion_request` (retries 429/5xx/network errors with backoff, honouring `Retry-After`; exits on other errors), `fetch_all_rows` (API `2025-09-03`: reads the database's `data_sources`, then pages through `/data_sources/{id}/query`), `get_prop`, `skip_reason`, `row_to_note`, `link_tag` |
| Card layout | `format_back`, `split_note`, `sentences`, `preview_html` (dry-run only) |
| Anki | `anki_request` (exits if AnkiConnect is unreachable; *logs but does not raise* on AnkiConnect errors), `anki_available`, `anki_multi` (batches writes through `multi`), `find_notes`, `same_html`, `plan_changes` (read-only), `print_plan`, `summarize`, `preview_changes` (dry-run), `add_or_update_notes` |
| Numbers seed | `NUMBER_GROUPS`, `load_numbers` (exits on a row with an unknown group or a missing front/reading/meaning), `number_back`, `number_note` (tags `numbers` + group), `seed_numbers` |
| CLI | `main` (argparse: `--dry-run`, `--seed-kana`, `--seed-kanji`, `--seed-verbs`, `--seed-words`, `--seed-numbers`, `--order`, `--no-update`, `--prune`; the five seeds and `--order` are mutually exclusive, and `--prune` is rejected with any seed or with `--no-update`) |

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

## Conventions

- Keep it a single, dependency-light script. Use stdlib `urllib` for HTTP.
- Put user-facing errors on `stderr`, and call `sys.exit(1)` for fatal ones.
- Every mode must stay safe to re-run (idempotent) and must support `--dry-run`.
- If you add a CLI flag, update the module docstring's USAGE block and `README.md`.
