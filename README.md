# notion-to-anki

This tool syncs a Notion "Language Learning Ledger" database into Anki flashcards. It can also seed full hiragana and katakana decks.

It is a single Python script. It reads your Notion database through the official API and writes cards into Anki through [AnkiConnect](https://ankiweb.net/shared/info/2055492159). It is safe to re-run: new rows are added, and existing cards are updated (text, deck and tags) when their row changes.

## Features

- **Ledger sync:** each Notion row becomes a `Basic` Anki card in a deck named after its `Type` (for example `Nihongo::Vocab` or `Nihongo::Kanji`). Each card is tagged with its lesson number.
- **Kana seed:** 208 recognition cards (hiragana and katakana, including dakuten/handakuten and yōon combinations). They go in `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.
- **Idempotent:** each ledger card carries a `notion_<page id>` tag that links it to its row, so running the script again never creates duplicates, and renaming an `Item` updates its card instead of making a new one.
- **Stays in its lane:** the kana seed only touches `Nihongo::Kana::*`, and the ledger sync only touches the other `Nihongo` decks. Tags you add yourself are never removed.
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
```

By default, cards already in Anki are brought in line with their source: the text is rewritten when it changed (for example after you fix a meaning in Notion), the card moves deck when you change its `Type`, and old `lesson<N>` / type tags are swapped for the current ones. Pass `--no-update` to only add new cards.

`--prune` deletes cards whose Notion row was deleted or is now skipped (for example renamed to `IGNORE …`). Deleting a card also deletes its review history, so run `--prune --dry-run` first. Prune only deletes cards that carry a `notion_` link tag. Any other card in the ledger decks, such as one you made by hand, is listed but left alone.

The first sync after upgrading to linked cards reports every ledger card under "Tags changed", because each one gets its `notion_` tag once.

## Limitations

- Two rows with the same `Item` and `Type` would be the same card, so only the first one is synced. The other is listed under "Not added".
- A card whose row was deleted *before* it got a `notion_` tag can't be told apart from a hand-made card, so `--prune` won't delete it. Delete it in Anki yourself (the prune output lists it).

## Troubleshooting

| Message | Fix |
|---|---|
| `Could not reach AnkiConnect at http://127.0.0.1:8765` | Open Anki and check that AnkiConnect is installed and enabled. |
| `Notion API error 401` | `NOTION_TOKEN` is wrong or has been revoked. |
| `Notion request failed (...); retrying` | Notion rate-limited the run or had a hiccup. The script retries up to 5 times on its own. |
| `Notion API error 404` | The database ID is wrong, or the database isn't shared with your integration. |
| `Set NOTION_TOKEN and NOTION_DATABASE_ID ...` | `.env` is missing, or isn't in the same folder as `main.py`. |
