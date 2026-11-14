---
name: sync
description: Push the data files to Anki - dry-run every seed and the study-order step, report what would change, and after the user's OK run them for real and verify. Use when the user says sync, update Anki, or approves adding cards.
---

# Sync to Anki

Anki must be open (AnkiConnect at 127.0.0.1:8765; the study-order step also needs the helper
add-on at 127.0.0.1:8766). Use `python3` on macOS.

## 1. Preview (read-only)

Run each dry run and collect its summary line (`Would add …`):

```bash
for m in kanji verbs words numbers sentences lookalikes; do
  echo "== $m"; python3 main.py --seed-$m --dry-run 2>&1 | grep -E '^Would|rror'
done
python3 main.py --order --dry-run
```

Order matters: kanji before words (words need their kanji rows), look-alikes after the other
seeds, `--order` last. Kana never changes; skip it.

If a dry run plans `moved:` cards, they're probably in an open Custom Study session
(docs/internals.md, known issue 6). Tell the user to close it, or run that seed with `--no-update`.

## 2. Ask

Report the counts in a few lines (cards added per deck, cards retagged or rewritten, cards moved
by `--order`) and ask before writing. Writing to the collection always needs the user's OK in this
conversation.

## 3. Run and verify

Run the same commands without `--dry-run`, in the same order. Then rerun the dry runs: every seed
should report `Would add 0 new notes` with nothing changed. Report any error lines.
