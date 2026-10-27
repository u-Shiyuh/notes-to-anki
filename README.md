# notion-to-anki

This tool syncs a Notion "Language Learning Ledger" database into Anki flashcards. It can also seed full hiragana and katakana decks, and a deck of the 1,000 most frequent kanji.

It is a single Python script. It reads your Notion database through the official API and writes cards into Anki through [AnkiConnect](https://ankiweb.net/shared/info/2055492159). It is safe to re-run: new rows are added, and existing cards are updated (text, deck and tags) when their row changes.

## Features

- **Ledger sync:** each Notion row becomes a `Basic` Anki card in a deck named after its `Type` (for example `Nihongo::Vocab` or `Nihongo::Kanji`). Each card is tagged with its lesson number.
- **Kana seed:** 208 recognition cards (hiragana and katakana, including dakuten/handakuten and yōon combinations). They go in `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.
- **Core Kanji seed:** the 1,000 most frequent kanji (by newspaper frequency) go in `Nihongo::Core Kanji`, in frequency order, so Anki introduces the most common ones first. Your daily new-card limit sets the pace. Kanji you already have in `Nihongo::Kanji` are skipped.
- **Idempotent:** each ledger card carries a `notion_<page id>` tag that links it to its row, so running the script again never creates duplicates, and renaming an `Item` updates its card instead of making a new one.
- **Stays in its lane:** the kana seed only touches `Nihongo::Kana::*`, the kanji seed only `Nihongo::Core Kanji`, and the ledger sync the other `Nihongo` decks. The one crossover: when you add a `Kanji` row to Notion for a kanji that's already in Core Kanji, the sync moves that card into `Nihongo::Kanji` and rewrites it from your row, keeping its review history, instead of making a second card. Tags you add yourself are never removed.
- **Dry-run mode** lets you preview changes before touching Anki. With Anki open, it lists every card that would be added, changed, moved, retagged or deleted.

## Requirements

- Python 3.8+
- [Anki](https://apps.ankiweb.net/) desktop with the **AnkiConnect** add-on (code `2055492159`). Anki must be **open** while the script runs.
- A Notion integration token (only needed for the ledger sync, not the kana seed)

## Setup

1. **Install the dependency**

   ```bash
   pip install python-dotenv
   ```

2. **Create a Notion integration** at <https://www.notion.so/my-integrations>. Copy its *Internal Integration Secret*.

3. **Share your database with the integration.** In Notion, open the database, then go to **⋯** → **Connections** and add your integration.

4. **Find the database ID.** Open the database as a full page. The ID is the 32-character string in the URL, before `?v=`.

5. **Configure `.env`**

   ```bash
   cp .env.sample .env
   ```

   ```ini
   NOTION_TOKEN=secret_xxx
   NOTION_DATABASE_ID=your_database_id
   ```

6. **Install AnkiConnect.** In Anki, go to **Tools** → **Add-ons** → **Get Add-ons**, enter `2055492159`, then restart Anki.

### macOS

The script works the same on macOS, with two differences:

- Use `python3` and `pip3` in place of `python` and `pip`.
- macOS's App Nap can pause Anki while it's in the background, so AnkiConnect stops answering and the script reports it can't reach AnkiConnect. Turn App Nap off for Anki once, then restart Anki:

  ```bash
  defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
  defaults write net.ichi2.anki NSAppSleepDisabled -bool true
  defaults write org.qt-project.Qt.QtWebEngineCore NSAppSleepDisabled -bool true
  ```

## Notion database schema

| Property | Type | Becomes |
|---|---|---|
| `Item` | Title | Card front |
| `Meaning` | Text | Card back (headline) |
| `Readings` | Text | Card back (under the meaning) |
| `Type` | Select | Deck `Nihongo::<Type>` and a tag (defaults to `Vocab`) |
| `Lesson` | Number | Tag `lesson<N>` |
| `Language` | Select | Only `Japanese` rows (or rows with no language) are synced |

Rows are skipped, and listed in the output, when `Item` is empty, starts with `IGNORE`, or has a `Language` other than Japanese.

## Card layout

The card back is formatted for review rather than copied as one block of text:

- **Meaning first**, in bold, so it's the first thing you check your answer against.
- **Readings** on the next line.
- **Side notes** go in small, faded text at the bottom. A side note is anything after ` — ` (space, em dash, space) in `Meaning` or `Readings`. For example, `き(く) kun / ぶん on — 新聞 is N5 vocab` shows the readings on one line and "新聞 is N5 vocab" as a note.
- **Grammar** rows are prose, so each sentence gets its own line with the first one as the headline.
- **Grammar Drill** rows are short practice cards (one prompt, one answer), such as `待つ → て-form` → `待って`. They go to their own `Nihongo::Grammar Drill` deck. Put the prompt in `Item`, the answer in `Meaning` and a short reason in `Readings`. The longer `Grammar` rows stay in `Nihongo::Grammar` as reference notes.

```
FRONT   聞

BACK    hear, listen, ask                      (bold)
        き(く) kun / ぶん, もん on
        新聞(しんぶん, newspaper) is N5 vocab   (small, faded)
```

Core Kanji cards show up to four meanings, the on'yomi in katakana and the kun'yomi in hiragana (okurigana in brackets), then the stroke count, JLPT level and frequency rank. In each reading line, the most common reading comes first in bold, with the rarer ones faded after it. "Most common" means the reading WaniKani teaches first. If none of a kanji's kun'yomi are common (such as 発), the whole kun line is faded. They're tagged `kanji`, `core_kanji` and `jlpt_n<level>`.

```
FRONT   連

BACK    take along, lead, join, connect           (bold)
        On: レン                                   (bold)
        Kun: つ(れる)、つら(なる)、つら(ねる)、-づ(れ)   (first bold, rest faded)
        10 strokes · JLPT N3 · #30 by frequency    (small, faded)
```

The formatting uses inline styles, so it works with Anki's stock `Basic` note type and in night mode. Use `--dry-run` to preview the first few cards.

## Usage

```bash
python main.py                          # sync the Notion ledger into Anki
python main.py --dry-run                # preview the sync without touching Anki
python main.py --no-update              # only add new cards; leave existing ones alone
python main.py --prune --dry-run        # list cards whose Notion row is gone
python main.py --prune                  # ...and delete them

python main.py --seed-kana              # add all hiragana + katakana cards
python main.py --seed-kana --dry-run    # preview the kana seed
python main.py --seed-kana --no-update  # add missing kana only

python main.py --seed-kanji             # add the 1,000 most frequent kanji
python main.py --seed-kanji --dry-run   # preview the kanji seed
```

By default, cards already in Anki are brought in line with their source: the text is rewritten when it changed (for example after you fix a meaning in Notion), the card moves deck when you change its `Type`, and old `lesson<N>` / type tags are swapped for the current ones. Pass `--no-update` to only add new cards.

`--prune` deletes cards whose Notion row was deleted or is now skipped (for example renamed to `IGNORE …`). Deleting a card also deletes its review history, so run `--prune --dry-run` first. Prune only deletes cards that carry a `notion_` link tag. Any other card in the ledger decks, such as one you made by hand, is listed but left alone.

The first sync after upgrading to linked cards reports every ledger card under "Tags changed", because each one gets its `notion_` tag once.

## Limitations

- Two rows with the same `Item` and `Type` would be the same card, so only the first one is synced. The other is listed under "Not added".
- A card whose row was deleted *before* it got a `notion_` tag can't be told apart from a hand-made card, so `--prune` won't delete it. Delete it in Anki yourself (the prune output lists it).

## Kanji data

`kanji_top1000.tsv` was generated once and is read locally, so seeding needs no network. Frequency ranks, readings, meanings and stroke counts come from [KANJIDIC2](https://www.edrdg.org/wiki/index.php/KANJIDIC_Project), © the Electronic Dictionary Research and Development Group, used under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). JLPT N-levels and the most-common-reading order (WaniKani's) come from [kanji-data](https://github.com/davidluzgouveia/kanji-data) (MIT). The frequency ranking is based on newspaper text, so news-heavy kanji such as 党 (political party) rank higher than they would in everyday conversation. Ten of the 1,000 have no JLPT level.

## Troubleshooting

| Message | Fix |
|---|---|
| `Could not reach AnkiConnect at http://127.0.0.1:8765` | Open Anki and check that AnkiConnect is installed and enabled. |
| `Notion API error 401` | `NOTION_TOKEN` is wrong or has been revoked. |
| `Notion request failed (...); retrying` | Notion rate-limited the run or had a hiccup. The script retries up to 5 times on its own. |
| `Notion API error 404` | The database ID is wrong, or the database isn't shared with your integration. |
| `Set NOTION_TOKEN and NOTION_DATABASE_ID ...` | `.env` is missing, or isn't in the same folder as `main.py`. |
