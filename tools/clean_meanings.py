"""Rewrite dictionary-style meanings in words.tsv into the house style.

One-off helper (2026-11-11), kept so the change is reproducible and reviewable.
The user asked for cards to be consistent across decks; about 280 meanings
still carried the source lists' formatting (`;` separators, "(lit., ...)",
"(abbr.)", rare senses first, a few wrong glosses such as あちら "this way").

House style for a word's meaning (matches the Core Kanji cards):
  - A short comma list, most common sense first, at most about three senses.
  - Short parentheses only for usage that changes how the word is used:
    (my), (someone's), (polite), (casual), (weather), (with neg.).
  - " / " separates unrelated homonyms (そば).
  - Etymology, examples and grammar go in the note column (faded line).

MEANINGS maps a word to its new meaning; NOTES adds a note (appended after any
existing note). KANA fixes a reading. Rows not listed are left alone.

Usage:
  python3 tools/clean_meanings.py           # show what would change
  python3 tools/clean_meanings.py --write   # apply it to words.tsv
"""

import sys
from pathlib import Path

WORDS = Path(__file__).resolve().parent.parent / "words.tsv"

MEANINGS = {
    "携帯": "mobile phone",
    "秋": "autumn, fall",
    "足": "foot, leg",
    "後": "after, later, the rest",
    "一番": "number one, first, best",
    "顔": "face",
    "家庭": "home, household",
    "国": "country, home country",
    "午後": "afternoon, p.m.",
    "午前": "morning, a.m.",
    "言葉": "word, language",
    "子供": "child",
    "時間": "time, hours",
    "写真": "photo",
    "話": "talk, story",
    "道": "road, way",
    "絵": "picture, painting, drawing",
    "体": "body, health",
    "口": "mouth",
    "結婚": "marriage",
    "生徒": "student, pupil",
    "大変": "hard, tough, very",
    "電気": "electricity, light",
    "はく": "to wear, put on (shoes, trousers)",
    "病気": "illness",
    "町": "town",
    "料理": "cooking, dish",
    "練習": "practice",
    "授業": "class, lesson",
    "そば": "beside, near / soba noodles",
    "半": "half, half past",
    "横": "side, beside, width",
    "両親": "parents",
    "鳥": "bird, chicken",
    "広い": "spacious, wide",
    "兄": "(my) older brother",
    "お母さん": "mother (polite)",
    "兄弟": "siblings, brothers",
    "玄関": "entrance, front door",
    "休み": "holiday, day off, break",
    "医者": "doctor",
    "妹": "(my) younger sister",
    "お茶": "tea, green tea",
    "角": "corner",
    "大丈夫": "OK, all right, no problem",
    "姉": "(my) older sister",
    "お父さん": "father (polite)",
    "漢字": "kanji, Chinese characters",
    "時計": "clock, watch",
    "夕方": "evening, late afternoon",
    "切手": "postage stamp",
    "結構": "fine, enough, quite",
    "高い": "high, tall, expensive",
    "明るい": "bright, cheerful",
    "作文": "essay, composition",
    "背": "height",
    "そう": "so, that way, yes",
    "荷物": "luggage, baggage",
    "帽子": "hat, cap",
    "よく": "often, well",
    "下さい": "please (give me, do for me)",
    "熱い": "hot (to the touch)",
    "余り": "not very (with neg.), the rest",
    "晴れ": "sunny, clear weather",
    "痛い": "painful, sore, it hurts",
    "少ない": "few, little",
    "古い": "old (things, not people)",
    "忙しい": "busy",
    "遅い": "slow, late",
    "鍵": "key, lock",
    "黒い": "black, dark",
    "また": "again, also",
    "辛い": "spicy, salty",
    "重い": "heavy, serious",
    "花瓶": "vase",
    "あちら": "over there, that way (polite)",
    "冷たい": "cold (to the touch), cold-hearted",
    "厚い": "thick",
    "アパート": "apartment",
    "あの": "that (over there), um...",
    "五日": "5th (of the month), five days",
    "いつも": "always, usually",
    "上": "above, on top, up",
    "うるさい": "noisy, annoying",
    "奥さん": "(someone's) wife",
    "お手洗い": "restroom, toilet (polite)",
    "お兄さん": "older brother (polite)",
    "お姉さん": "older sister (polite)",
    "方": "person (polite), way of doing",
    "カレー": "curry, curry rice",
    "キロ": "kilogram, kilometre",
    "コート": "coat, (tennis) court",
    "九日": "9th (of the month), nine days",
    "こちら": "this way, this person (polite)",
    "こっち": "this way, this side (casual)",
    "コップ": "glass, cup",
    "先": "ahead, tip, before",
    "しかし": "however, but",
    "涼しい": "cool (weather)",
    "ストーブ": "heater",
    "スポーツ": "sports",
    "近く": "nearby, near",
    "ちょっと": "a little, a bit",
    "つまらない": "boring, dull",
    "デパート": "department store",
    "トイレ": "toilet, restroom",
    "どうも": "thanks, very much, somehow",
    "十日": "10th (of the month), ten days",
    "どちら": "which, where (polite)",
    "とても": "very",
    "ない": "there isn't, don't have",
    "なぜ": "why",
    "七日": "7th (of the month), seven days",
    "バス": "bus",
    "二十日": "20th (of the month), twenty days",
    "フィルム": "film",
    "二日": "2nd (of the month), two days",
    "ポスト": "mailbox, post (job)",
    "まずい": "bad-tasting, awful",
    "まっすぐ": "straight, straight ahead",
    "六日": "6th (of the month), six days",
    "目": "eye",
    "もしもし": "hello (on the phone)",
    "物": "thing",
    "八日": "8th (of the month), eight days",
    "四日": "4th (of the month), four days",
    "ワイシャツ": "dress shirt",
    "暑い": "hot (weather)",
    "遠い": "far, distant",
    "おまわりさん": "police officer (friendly)",
    "寒い": "cold (weather)",
    "飴": "candy",
    "多い": "many, a lot",
    "御飯": "cooked rice, meal",
    "狭い": "narrow, cramped",
    "安い": "cheap",
    "悪い": "bad",
    "お～": "honorific prefix",
    "お酒": "alcohol, sake",
    "～回": "~ times",
    "～階": "~th floor (counter)",
    "～か月": "~ months",
    "～くらい": "about, approximately",
    "～個": "counter for small things",
    "～ごろ": "around (a time)",
    "～時": "~ o'clock",
    "～すぎ": "past, too much",
    "～台": "counter for machines, vehicles",
    "～度": "~ times, ~ degrees",
    "～番": "number ~, ~th",
    "勉強する": "to study",
    "部長": "department manager",
    "男性": "man, male",
    "生産": "production",
    "妻": "(my) wife",
    "高校": "high school",
    "将来": "future, prospects",
    "警察": "police",
    "会議": "meeting, conference",
    "生活": "life, living",
    "関係": "relationship, connection",
    "昔": "long ago, old days",
    "確か": "certain, if I remember right",
    "以内": "within, no more than",
    "彼ら": "they",
    "彼女": "she, girlfriend",
    "専門": "specialty, major",
    "普通": "normal, usual",
    "工業": "industry",
    "娘": "(my) daughter",
    "残念": "too bad, regrettable",
    "住所": "address",
    "息子": "(my) son",
    "急": "sudden, urgent, steep",
    "運転手": "driver",
    "季節": "season",
    "興味": "interest",
    "仕方": "way (of doing)",
    "看護婦": "nurse (female)",
    "漫画": "manga, comic",
    "点": "point, dot, score",
    "おかしい": "funny, strange",
    "是非": "by all means, certainly",
    "腕": "arm",
    "世話": "care, looking after",
    "趣味": "hobby",
    "表": "front, surface, outside",
    "一生懸命": "very hard, with all one's effort",
    "習慣": "custom, habit",
    "僕": "I (male, casual)",
    "店員": "shop clerk",
    "久しぶり": "long time no see, after a long time",
    "背中": "back (of the body)",
    "事": "thing, matter",
    "研究室": "lab, professor's office",
    "うん": "yeah, OK (casual)",
    "細かい": "small, fine, detailed",
    "着物": "kimono",
    "特急": "limited express (train)",
    "留守": "away from home, absence",
    "畳": "tatami mat",
    "以上": "more than, that's all",
    "大体": "about, mostly, generally",
    "贈り物": "gift, present",
    "指輪": "ring",
    "優しい": "kind, gentle, easy",
    "泥棒": "thief, burglar",
    "素晴らしい": "wonderful",
    "全然": "(not) at all",
    "手袋": "gloves",
    "厳しい": "strict, severe",
    "汽車": "steam train",
    "柔らかい": "soft, tender",
    "家内": "(my) wife",
    "お嬢さん": "(someone's) daughter, young lady",
    "訳": "reason, meaning",
    "挨拶": "greeting",
    "用事": "errand, things to do",
    "テキスト": "textbook, text",
    "床屋": "barber",
    "オートバイ": "motorcycle",
    "非常に": "extremely, very",
    "お宅": "(someone's) home (polite)",
    "ちっとも": "not at all (with neg.)",
    "それに": "besides, moreover",
    "パート": "part-time job",
    "だから": "so, therefore",
    "ビル": "building",
    "どんどん": "steadily, rapidly",
    "お礼": "thanks, thank-you gift",
    "受付": "reception desk",
    "オーバー": "overcoat, over, exaggerated",
    "ご主人": "(someone's) husband",
    "用": "errand, business",
    "よろしい": "good, all right (polite)",
    "おつり": "change (money)",
    "ごちそう": "feast, treat",
    "パソコン": "PC, computer",
    "うまい": "delicious, skillful",
    "まず": "first of all",
    "それほど": "that much",
    "それで": "and then, so",
    "なるほど": "I see",
    "字": "character, letter, handwriting",
    "君": "you (casual, male speech)",
    "嬉しい": "happy, glad",
    "ソフト": "software, soft",
    "失礼": "rudeness, excuse me",
    "拝見": "seeing (humble)",
    "予習": "lesson preparation",
    "復習": "review",
    "～ございます": "to be (polite)",
    "～式": "~ ceremony, ~ style",
    "けがする": "to get hurt",
    "～ちゃん": "suffix for children and close friends",
    "お子さん": "(someone's) child",
    "～代": "~s (age), ~ fee",
    "～君": "suffix for boys and juniors",
    "もうすぐ": "soon, any moment",
    "～目": "~th (ordinal)",
    "胸": "chest",
    "腰": "lower back, hips",
}

NOTES = {
    "携帯": "short for 携帯電話 (けいたいでんわ)",
    "結婚": "結婚する = to get married",
    "半": "2時半 (にじはん) = half past two",
    "鳥": "chicken meat is 鶏肉 (とりにく), often just とり",
    "お手洗い": "literally \"hand-washing place\"",
    "方": "polite word for 人 (ひと)",
    "ストーブ": "from English \"stove\"",
    "なぜ": "same as どうして",
    "ワイシャツ": "from English \"white shirt\"",
    "看護婦": "today 看護師 (かんごし) is the usual word",
    "拝見": "拝見する = to look at (humble)",
    "～代": "20代 = in one's twenties; 電気代 = electricity bill",
    "～すぎ": "3時すぎ = past three; 食べすぎ = eating too much",
    "勉強する": "勉強 + する; する is irregular: 勉強します, 勉強しました, 勉強して",
}

KANA = {"勉強する": "べんきょうする"}


def main(argv):
    lines = WORDS.read_text(encoding="utf-8").split("\n")
    seen, changes = set(), []
    for i, line in enumerate(lines):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        n = len(cols)
        cols += [""] * (7 - n)
        word = cols[1]
        new = list(cols)
        if word in MEANINGS:
            seen.add(word)
            new[3] = MEANINGS[word]
        if word in NOTES and NOTES[word] not in new[5]:
            new[5] = f"{new[5]}; {NOTES[word]}" if new[5] else NOTES[word]
        if word in KANA:
            new[2] = KANA[word]
        if new != cols:
            for col, name in ((2, "kana"), (3, "meaning"), (5, "note")):
                if new[col] != cols[col]:
                    changes.append(f"{word}\t{name}\t{cols[col]}  ->  {new[col]}")
            while len(new) > n and new[-1] == "":  # keep the row's original width
                new.pop()
            lines[i] = "\t".join(new)
    missing = sorted(set(MEANINGS) - seen)
    for c in changes:
        print(c)
    print(f"{len(changes)} field(s) {'changed' if '--write' in argv else 'would change'}.",
          file=sys.stderr)
    if missing:
        sys.exit("Not in words.tsv: " + " ".join(missing))
    if "--write" in argv:
        WORDS.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
