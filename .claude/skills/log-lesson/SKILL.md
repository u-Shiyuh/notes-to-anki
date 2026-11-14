---
name: log-lesson
description: Record a lesson the user studied (from a book like Complete Grammar, or standalone study) - correct their notes, answer their questions, add new words/verbs/kanji to the data files, tag every card the lesson mentioned, and update study/profile.md. Use whenever the user pastes lesson notes or says what they just learned.
---

# Log a lesson

The user wants to focus on learning. Do the whole data routine without asking step by step;
only the final Anki write needs their OK (CLAUDE.md: ask before any non-dry run).

Sources and their codes are in the Sources table of `study/profile.md` (`cg` = *Complete Grammar*).
A new book gets a new short code there first. Standalone study uses `self::<YYYY-MM-DD>`.

## Steps

1. **Read the notes.** Turn the user's romaji into Japanese. Note anything they got wrong
   (long vowels: おじいさん vs おじさん; voicing exceptions) and answer any concept they asked
   to have checked. Ask about a word only if you really can't tell what it is.
2. **Check every word against the data.** Cards may be spelled differently from the notes
   (カキ, not 牡蠣; りんご, not 林檎):
   ```bash
   python3 - 富士山 りんご 生きる <<'EOF'
   import sys, main
   fronts = (set(main.core_kanji()) | {r["word"] for r in main.seeded_words()}
             | {r["word"] for r in main.load_verbs()})
   kana = {r["kana"]: r["word"] for r in main.load_words()}
   for w in sys.argv[1:]:
       print(w, "card" if w in fronts else f"kana of {kana[w]}" if w in kana else "-")
   EOF
   ```
   A one-kanji word whose kanji card teaches it shows as `card` (its Front is the kanji).
3. **Add what's missing.**
   - Words: append to `words.tsv` with a blank level, a topic (one of the existing ones), and a
     note explaining the lesson's point (rendaku, own/someone else's family, minimal pair). Follow
     the meaning style in `docs/tools.md` ("Consistency across decks").
   - Cards that already exist get the lesson's point too, when it changes how the word is used
     (それ vs その, own vs someone else's family, polite vs casual): put it in their `note`, with a
     tiny example. A bare "that one" isn't enough (user, 2026-11-14).
   - Verbs: append to `verbs.tsv` under section `<code>` (e.g. `cg`), numbered in lesson order.
   - Skip names used only as reading practice (山田, ボストン). Prefer kana or katakana Fronts over
     rare kanji (カキ), so obscure kanji don't become cards.
4. **New kanji.** Run in order:
   ```bash
   python3 tools/add_kanji_extra.py --write
   python3 tools/add_radicals.py --write
   python3 tools/mark_readings.py --write
   python3 tools/dedupe_readings.py --write
   ```
   `mark_readings` only bolds readings N5/N4 words use, so bold a blank-level word's reading in
   its new kanji row by hand (`*かき`).
5. **Tag the lesson.** Append one row to `references.tsv`: `<code>::lNN` then every Front the
   lesson mentioned, space-separated, including words that already had cards. List a one-kanji
   word its kanji card teaches by the kanji.
6. **Check.** `python3 tools/check_data.py --refresh` must say `0 row(s) flagged` (it checks types,
   groups, and that every `references.tsv` Front is a real card). Fix and rerun until it does.
7. **Update `study/profile.md`.** Add grammar bullets under their topic heading (make a new heading
   for a new topic), each ending `(CG LNN)`; add one Log line saying what was added and left out.
8. **Preview.** Dry-run the seeds the change touches and report the counts:
   ```bash
   python3 main.py --seed-kanji --dry-run
   python3 main.py --seed-words --dry-run
   python3 main.py --seed-verbs --dry-run
   ```
9. **Commit** the data and profile changes (on master, as this repo does).
10. **Reply** briefly: corrections, answers to their questions, what was added, then ask whether to
    sync (the `sync` skill does it).
