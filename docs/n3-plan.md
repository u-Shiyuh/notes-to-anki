# Friend profile and N3 content: plan and gap analysis

Written 2026-11-16. Mostly a plan. Built so far: the default order (`tools/default_order.py` →
`default_order.tsv`, 2026-11-17), for the starter deck; the user's own decks are untouched.

## Goal

A friend (already around N4) uses these decks to review N5/N4 and reach **N3 by December 2027**
(about 390 days from now). The same content later serves the user on their way to N3.

## How he gets the decks (agreed so far)

- **A second Anki profile on the user's Mac** (File → Switch Profile → Add), logged into **his own
  free AnkiWeb account**. He studies on his phone or on AnkiWeb; his progress never mixes with the user's.
- The user runs the seeds into his profile and syncs; he gets new cards with his progress kept.
- He starts with the full N5 content as review (his choice), then N4, then N3.
- No shared AnkiWeb account: that would be one collection with mixed reviews and sync conflicts.

Done 2026-11-21: his profile exists (`verge`, logged into his AnkiWeb; the user's is `User 1`), and
`--profile <name>` works on any mode (`anki_profile` in `main.py`: AnkiConnect `loadProfile`, which
returns before the switch finishes, so it polls `getActiveProfile` until the collection answers; the
previous profile is reopened at the end). Without `--profile`, runs use `User 1` (`DEFAULT_PROFILE`).
Also done 2026-11-21: per-profile settings in `users/<profile>/user.json` (`load_user`, `USER`): his
`ref_sources` is `["jlpt", "tatoeba"]` (no book/lesson tags, so no Lessons lane) and `order` is `default`
(`order_default` sorts each deck's new cards by `default_order.tsv` through the helper's `setNewOrder`).
Seeded the same day: 2,854 cards, all new, synced to his AnkiWeb. `loadProfile` is ignored while Anki is
busy (syncing), so `switch_profile` re-sends it every 5 s. Still open: his daily limits (all decks on
`Default`, 20 new/day each), and `users/<name>/` lessons if he ever logs any.

## Multi-user design (scales past one friend)

Same decks and layouts for everyone (built by `main.py`); data in three layers, applied in order:

```
base/      shared rows everyone can get (today's root TSVs: words, verbs, kanji, numbers, sentences…)
packs/     optional shared sets a user opts into: jlpt-n3, jlpt-n2, cg (Complete Grammar),
           verb-book, travel… (a pack = rows + its ref:: tag)
users/<name>/
  user.json         Anki profile name, packs, levels (n5..n3), lanes, daily limits, tags on/off
  add/*.tsv         rows only this user gets
  skip.tsv          Fronts this user doesn't want
  override.tsv      this user's meaning/note for a shared Front
  references.tsv, profile.md, progress.tsv
```

- **The user is one user too.** Today's `references.tsv`, `study/profile.md`, `study/progress.tsv` and
  lane settings move to `users/<user>/`, so the code has no special "owner" case.
- **Packs carry the difference between people.** Content goes into a pack, not a user's `add/`, when a
  second person could want it (a book, a JLPT level). `add/` stays for one-off personal rows.
- **Book packs only list the book's words.** The rows themselves stay in base (one card per word), and a
  pack that covers a word just adds its `ref::` tag.
- **One command per user:** `main.py --user <name> --seed-…` / `--order`. It checks the open Anki profile
  matches `user.json` and stops if not. `--all-users` runs each in turn.
- **Every tool and skill takes `--user`** (`progress.py`, `check_drift.py`, `log-lesson`, `sync`).
  `check_data.py` checks base, packs and every user's overlays, and warns when a base row changes under
  someone's override.
- **Bringing things back together:** move rows from `add/` into a pack or base. Cards keep their history
  (adopted by Front), and the user's folder shrinks to empty.
- **Adding a person:** copy `users/_template/`, set the profile name and packs, create the Anki profile
  and log it into their AnkiWeb account.

Limits as it grows:
- **One machine runs everyone's syncs.** Fine for a few people. Past that, each person runs the repo on
  their own machine (same commands, their `--user`), with git as the shared base.
- **Privacy.** `users/*/profile.md` and progress sit in the repo; anyone with repo access sees them.
  Keep the repo private, or keep `users/` out of git and back it up separately.
- **Base edits affect everyone.** A meaning change in base reaches every user at their next sync, so
  base and pack edits go through `check_data.py` and git history.
- **Front is identity across all users.** Renaming a base Front makes a new card for everyone.
- **Anki progress never merges between users.** Each collection keeps its own history.

## What the decks have now

| Deck | Rows | Level |
|---|---|---|
| Words (`words.tsv`) | 1,164 | 597 N5, 504 N4, 63 unlevelled |
| Verbs (`verbs.tsv`) | 218 | reviewer book + 25 N5 extras |
| Core Kanji (both files) | 1,200 | all N5/N4 kanji, 357 of 367 N3 |
| Numbers & Time | 169 | N5/N4 |
| Sentences | 100 | readable with N5 cards |

## Gap analysis (measured 2026-11-16)

Method: the JLPT lists in `sources/n5.csv`, `sources/n4.csv` and `tools/cache/n3.csv`
(open-anki-jlpt-decks, on Waller's lists) against every card Front in words, verbs, numbers and the
kanji files (a one-kanji word counts through its kanji card; a noun counts if its する-verb is carded).
Kanji levels from `tools/cache/kanji-data.json`.

### Words

| Level | List entries | Missing | Of which |
|---|---|---|---|
| N5 | 718 | 12 | all grammar suffixes (～ずつ ～だけ ～ごろ), fine as is |
| N4 | 668 | ~100 | ~76 **verbs** (踏む 拾う 壊れる 迎える 頑張る), keigo (いらっしゃる 召し上がる 申し上げる), patterns (～ばかり ～にくい) |
| N3 | 2,140 | **1,728** | ~320 verbs (冷める 覚める 従う 与える 信じる), 121 katakana words, the rest nouns/adverbs/adjectives (様々 更に 幸せ 事件 自然 次第) |

- N4 verbs are missing because `words.tsv` excludes verbs by design and `verbs.tsv` only has the
  book's verbs plus N5 extras. They need a `verbs.tsv` section (like `extra`), e.g. `jlpt4`.
- N3 is essentially new: about 1,400 words for `words.tsv` and about 320 verbs for `verbs.tsv`.
- Some list entries need hand mapping (multi-form entries, `～` prefixes, `パート (タイム)`);
  the counts above are within a few percent.

### Kanji

| Level | Total | Have | Missing |
|---|---|---|---|
| N5 | 79 | 79 | 0 |
| N4 | 166 | 166 | 0 |
| N3 | 367 | 357 | **10**: 才 陽 掛 貧 幾 誤 到 偶 偉 頂 |

- The N3 kanji themselves are nearly done.
- **But the house rule "every card word's kanji has a Core Kanji card" pulls in more:** the N3 word
  list uses **307 kanji with no row** (刺 酸 湿 梅 妙 句 詞 騒 診 握…), mostly N2/N1 kanji that appear
  in N3 words, often in words usually written in kana. Writing usually-kana words in kana (JMdict `uk`)
  should cut this a lot. Decision needed before adding them.

### Sentences

100 Tatoeba sentences, all readable with N5 cards. N3 needs many more at N4/N3 level;
`tools/add_sentences.py` can propose them once the N4/N3 words exist.

### Not covered by any deck

- **Grammar.** No grammar deck; grammar lives in `study/profile.md` as notes. N4 and N3 grammar
  (a couple hundred points between them) is the largest part of the exam the decks don't touch.
  A grammar deck (pattern, meaning, one example sentence) would be a separate design.
- **Reading and listening practice.** Outside Anki: graded readers, NHK Easy, listening practice.

## Load estimate for him

New cards across all decks after adding N3: about 1,160 current words + 1,400 N3 words + ~400 verbs
+ 218 current verbs + kanji (1,200 now, plus 10 to ~300) + numbers ≈ **4,500–4,800 cards** in
~390 days ≈ **12 new cards a day**. The N5/N4 part goes fast for him (pressing Easy), so the real load
is closer to 8–10 a day for the N3 material. Some top-1,000 kanji are N2/N1 and not needed for N3;
his profile could leave those for later to lighten it.

## Open decisions

1. Kana spelling for usually-kana N3 words (fewer extra kanji cards)?
2. Kanji used only by N3 words: add them all, or only N3-level ones?
3. N3 words in the user's own collection: hold them out of the daily queue until the user reaches N4?
4. A grammar deck: wanted, and from what source?
5. His daily new-card limits and lane order (N5 → N4 → N3).
