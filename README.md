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
| `Readings` | Text | Card back (first line) |
| `Meaning` | Text | Card back (after readings) |
| `Type` | Select | Deck `Nihongo::<Type>` and a tag (defaults to `Vocab`) |
| `Lesson` | Number | Tag `lesson<N>` |

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

> **Windows users:** the console's default encoding cannot print kana, so `--dry-run` crashes with a `UnicodeEncodeError`. Run the script with `PYTHONIOENCODING=utf-8` set, or use `python -X utf8 main.py ...`.

## Limitations

- Cards are matched **only by Front text**, across *all* `Basic` notes in your collection. This causes a collision when a ledger item is identical to a kana character (particles such as は or を are common examples): the kana seed and the ledger sync will overwrite each other's Back field.
- Moving a row to a different `Type` does not move the existing card to the new deck. Tags are only ever added, never removed. Rows deleted in Notion are not deleted from Anki.
- A multi-word `Type` (for example `Kanji Compound`) becomes two separate Anki tags.

## Troubleshooting

| Message | Fix |
|---|---|
| `Could not reach AnkiConnect at http://127.0.0.1:8765` | Open Anki and check that AnkiConnect is installed and enabled. |
| `Notion API error 401` | `NOTION_TOKEN` is wrong or has been revoked. |
| `Notion API error 404` | The database ID is wrong, or the database isn't shared with your integration. |
| `Set NOTION_TOKEN and NOTION_DATABASE_ID ...` | `.env` is missing, or isn't in the same folder as `main.py`. |
