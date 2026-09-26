# notion-to-anki

This tool syncs a Notion "Language Learning Ledger" database into Anki flashcards. It can also seed full hiragana and katakana decks.

It is a single Python script. It reads your Notion database through the official API and writes cards into Anki through [AnkiConnect](https://ankiweb.net/shared/info/2055492159). It is safe to re-run: new rows are added, and existing cards are updated when their content changes.

## Features

- **Ledger sync:** each Notion row becomes a `Basic` Anki card in a deck named after its `Type` (for example `Nihongo::Vocab` or `Nihongo::Kanji`). Each card is tagged with its lesson number.
- **Kana seed:** 208 recognition cards (hiragana and katakana, including dakuten/handakuten and yōon combinations). They go in `Nihongo::Kana::Hiragana` and `Nihongo::Kana::Katakana`.
- **Idempotent:** cards are matched by their Front text, so running the script again never creates duplicates.
- **Dry-run mode** lets you preview changes before touching Anki.

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

python main.py --seed-kana              # add all hiragana + katakana cards
python main.py --seed-kana --dry-run    # preview the kana seed
python main.py --seed-kana --no-update  # add missing kana only
```

By default, cards already in Anki get their Back field overwritten when the source has changed, for example after you fix a meaning in Notion. Pass `--no-update` to only add new cards.

The first sync after upgrading to the new card layout will report most notes as "Updated", because every card back changes format once.

## Limitations

- Cards are matched **only by Front text**, across *all* `Basic` notes in your collection. This causes a collision when a ledger item is identical to a kana character (particles such as は or を are common examples): the kana seed and the ledger sync will overwrite each other's Back field.
- Moving a row to a different `Type` does not move the existing card to the new deck. Tags are only ever added, never removed. Rows deleted in Notion are not deleted from Anki.

## Troubleshooting

| Message | Fix |
|---|---|
| `Could not reach AnkiConnect at http://127.0.0.1:8765` | Open Anki and check that AnkiConnect is installed and enabled. |
| `Notion API error 401` | `NOTION_TOKEN` is wrong or has been revoked. |
| `Notion API error 404` | The database ID is wrong, or the database isn't shared with your integration. |
| `Set NOTION_TOKEN and NOTION_DATABASE_ID ...` | `.env` is missing, or isn't in the same folder as `main.py`. |
