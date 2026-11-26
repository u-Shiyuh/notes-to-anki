# Learner profile

The one place that says what the user knows, from every source. Update it after each lesson, book or study session.
Anki and the `.tsv` files are the record of vocabulary and kanji, and `study/progress.tsv` the record of progress; this file holds what they can't:
grammar and concepts learned, which source taught them, and a log of what each lesson added.

## Progress

Numbers (cards per deck, JLPT coverage, common words, sources, retention, pace) are data, not prose:
`study/progress.tsv`, one row per metric per day, saved by `python3 tools/progress.py --record` at every sync.
Run `python3 tools/progress.py` for the current report.

Level: early N5. Kana reading is solid; vocabulary and kanji are being built through the Anki decks.

## Sources

Every card carries a `ref::` tag per source that mentions it (Anki tag tree `ref`), so any source or lesson can be studied by tag.

| Source | What it covers | Where it lives | Card tag |
|---|---|---|---|
| Verb reviewer book | verbs by group, with glosses | `verbs.tsv` sections 1-3 | `ref::verb_book::s1`-`s3` |
| *Complete Grammar* (book; chapters: 1 intro/writing, 2 nouns, 3 numbers, …) | grammar, lesson by lesson | the log below (CG); words in `references.tsv` | `ref::cg::l01`… |
| JLPT N5/N4 lists | vocabulary, kanji levels | `words.tsv`, kanji files, `verbs.tsv` `extra` | `ref::jlpt::n5`… |
| Kanji frequency (KANJIDIC2) | the 1,000 most common kanji | `kanji_top1000.tsv` | (only its JLPT tag) |
| Tatoeba | example sentences | `sentences.tsv` | `ref::tatoeba` |
| Standalone study | anything else | the log below (self); `references.tsv` | `ref::self::<date>` |
| Notion ledger | old notes, outdated | retired 2026-11-06 | — |

## Grammar and concepts learned

One list across all sources, grouped by topic. Each bullet ends with where it was learned.

### Sounds and writing
- Long vowels change meaning: とり bird / とおり street; えい is read ええ (せんせい). (CG L1)
- Small っ doubles the consonant and changes meaning: おと sound / おっと husband. (CG L1)
- ん is a beat of its own: きねん anniversary / きんえん no smoking; ほんやく is hon-ya-ku. (CG L1)
- Contracted sounds きゃ きゅ きょ…: びょういん hospital vs びよういん beauty salon. (CG L1)
- Pitch accent tells same-kana words apart: しろ 白/城, あめ 雨/飴, はし 箸/橋, かみ 神/紙, かき 牡蠣/柿. (CG L1)
- Katakana for loanwords, incl. チェ ファ. (CG L1)
- A kanji has several readings: 生 (生きる 生まれる 先生 学生), 来 (来る 来ない 来年 来週), 私 (わたし, and シ in 私立 private). (CG L1)

### Sentence structure
- Word order subject–object–verb; the verb comes last. (CG L1)
- Particles: が subject, を object, は topic (read わ). Intro only. (CG L1)
- Pronouns are dropped when context makes them clear. (CG L1)
- です, "is/am/are". (CG L1)
- Three speech styles, intro only: plain 買ったの？, polite 買いましたか, formal お買いになりましたか ("Did you buy it?"). (CG L1)
- No articles ("a/the") and no singular/plural on nouns: 本 is "a book", "the book" or "books". (CG L2)

### Nouns
- Proper nouns: names (山田), places (ソウル Seoul, 富士山), companies (ソニー). (CG L2)
- Name titles, never used for yourself: 〜さん (general), 〜ちゃん (children, close friends), 〜様 (very polite); job titles work as titles: 部長, 社長, 先生. Introducing yourself humbly: 〜と申します. (CG L2)
- Compound nouns often voice the first sound of the second word (rendaku): 会社 → 貿易がいしゃ, 箱 → ごみばこ, 玉 → シャボンだま. Not always: 女言葉 おんなことば. (CG L2)
- A verb's stem (ます-form minus ます) works as a noun part: 食べ物, 焼き肉, 飼い猫; two stems together: 読み書き, 立ち読み. (CG L2)
- Noun + な-adjective stem makes a noun for a person or trait: 酒好き (好き → ずき), 人間嫌い (嫌い → ぎらい). (CG L2)

### Demonstratives (こそあど)
- こ = near me, そ = near you, あ = over there (away from both), ど = which. (CG L2)
- Demonstrative pronouns stand alone in place of a noun: これ/それ/あれ/どれ (thing), ここ/そこ/あそこ/どこ (place), こちら/そちら/あちら/どちら (direction; polite "this person/way"). これは本です. (CG L2)
- Demonstrative adjectives can't stand alone; they come right before a noun: この/その/あの/どの + noun. この本は高い. Wrong: このは本です. (CG L2)

### Pronouns and family words
- Personal pronouns, plural with 〜たち (or plainer 〜ら): 私/私たち, 僕/僕たち (male, casual), あなた/あなたたち, 彼/彼ら, 彼女/彼女ら. Usually dropped; あなた can sound rude, so use the name + さん. (CG L2)
- の links nouns (私の本), and the second noun can be dropped when clear: これは私のです. (CG L2)
- Family words come in two sets: plain for your own family when talking to others, polite for someone else's (and for addressing your own elders): 父/お父さん, 母/お母さん, 兄弟/ご兄弟, 兄/お兄さん, 姉/お姉さん, 弟/弟さん, 妹/妹さん, 祖父/おじいさん, 祖母/おばあさん, おじ/おじさん, おば/おばさん, 主人・夫/ご主人, 家内・妻/奥さん. (CG L2)
- Long vowels matter here too: おじいさん (grandfather) vs おじさん (uncle), おばあさん (grandmother) vs おばさん (aunt). (CG L2)

### Numbers and counters
- Sino-Japanese numbers いち…じゅう, then 百 ひゃく, 千 せん, 万 まん (10,000 is its own unit: 12万 = 120,000). (CG L3)
- Native numbers for counting things: ひとつ … ここのつ, then とお (10, no つ); from 11 on, Sino-Japanese. (CG L3)
- Counters follow the number and depend on the thing: 人 people (一人 ひとり, 二人 ふたり, then 〜にん; 4人 よにん), 匹 small animals, 本 long thin things, 冊 books, 枚 flat things, 杯 cups/glasses, 回 times, 番 number in order, 位 rank, ページ pages. (CG L3)
- Sound changes with h/s/t/k counters: 1, 6, 8, 10 double the consonant (いっぽん, いっさつ) and h becomes p or b (ぴき/びき, ぽん/ぼん; 3 and 何 take b: さんぼん, なんぼん). 枚 never changes. (CG L3)
- Time: 時 o'clock, 分 minutes, 年 years; 午前/午後 come before the time (午後3時). Duration adds 間: 時間, 分(間), 週間; months use か月. (CG L3)
- 何 + counter asks how many/which: 何時, 何日, 何回, 何ページ; から … まで = from … to (何ページから何ページまで). (CG L3)
- Units are katakana loanwords: リットル, グラム, キロ(グラム/メートル), メートル, センチ, ミリ, マイル, インチ, ドル; 円 yen. (CG L3)
- 〜目 turns a count into an order: 一つ目 the first one, 二番目 the second, 三回目 the third time. (CG L3)

## Where lesson vocabulary goes

Not here. New words and kanji go into the data files, so they get cards like everything else:
words → `words.tsv` (blank level, at the end), verbs → `verbs.tsv` (section `cg` for *Complete Grammar*),
then `tools/add_kanji_extra.py --write` gives any new kanji its Core Kanji row (and `add_radicals`,
`mark_readings`, `dedupe_readings`, `check_data --refresh`). The log below just says what was added.
Then add a `references.tsv` row listing every Front the lesson mentioned (including words already in the decks), so all of them get the lesson's tag.
Proper nouns used only as reading practice (大阪, ボストン) are left out.

## Log

Short dated entries; the detail goes in the sections above.

- 2026-11-14 · CG Lesson 1 (Introduction: sounds, word order, writing systems). Mostly review; new: pitch accent, particles が/を/は, speech styles.
  Added to the data files: 17 words (りんご 夫婦 記念 竹 城 神 銀 柿 カキ 下駄 天ぷら 折り紙 金魚 私立 ピザ ソファ アイロン; 竹 城 神 銀 柿 are taught by their kanji cards), verb 生きる (`cg` 1), kanji 柿 and 駄.
- 2026-11-14 · CG Lesson 2 (Nouns: proper nouns, titles, compounds, demonstratives, pronouns, の, family words).
  Added: 22 words (富士山 人間 貿易会社 女言葉 ごみ箱 シャボン玉 焼き肉 飼い猫 読み書き 立ち読み 酒好き 人間嫌い 私たち 僕たち あなたたち 彼女ら ご兄弟 弟さん 妹さん 主人 おじ おば), verb 申す (`cg` 2), kanji 飼. Left out: 山田, ソウル, ソニー (names).
- 2026-11-26 · CG Lesson 3 (Numbers: Sino-Japanese and native numbers, counters and sound changes, time, units, 何 + counter, 〜目). Mostly already in Numbers & Time; tagged 82 existing cards.
  Added: 6 words (リットル センチ ミリ マイル インチ ドル), 9 Numbers & Time cards (何回 1位 5ページ 何ページ 10ページから20ページまで 5分間 1つ目 2番目 3回目), and lesson notes on 十 一つ 一人 何時 ～時間 午後 キロ ～目. No new kanji. Corrected: kiro(meteru) → キロメートル, inichi → インチ; "doru" was listed twice.
