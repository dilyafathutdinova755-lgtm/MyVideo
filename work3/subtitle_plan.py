import json

WORK = "/home/user/MyVideo/work3"
words = json.load(open(f"{WORK}/edited_words.json"))
timeline = json.load(open(f"{WORK}/timeline.json"))
TOTAL = timeline[-1]["edited_end"]

def find(text, occurrence=0):
    matches = [w for w in words if w["text"].strip("?,.") == text]
    return matches[occurrence] if len(matches) > occurrence else None

ACCENT = "#C9F5FF"

raw_cards = [
    (words[0]["start"], [("ДОМОВЕРСИИ", False), ("ЕГЭ 2027", True)], 2.0),
    (find("экзамен")["start"], [("ВАШ", False), ("ЭКЗАМЕН", True)], 1.8),
    (find("форматы")["start"], [("КАКИЕ", False), ("ФОРМАТЫ?", True)], 1.8),
    (find("фипи")["start"] - 0.4, [("БАНК", False), ("ФИПИ", True)], 2.0),
    (find("достоверные")["start"], [("САМЫЙ", False), ("ДОСТОВЕРНЫЙ", True)], 2.0),
    (find("тренажер")["start"] - 0.3, [("ЕГЭ", False), ("ТРЕНАЖЁР", True)], 2.4),
    (find("клад")["start"], [("ЭТО", False), ("КЛАД", True)], 1.8),
    (TOTAL - 2.3, [("ССЫЛКА", True), ("В ШАПКЕ ПРОФИЛЯ", False)], 2.3),
]

cards = []
for start, parts, dur in raw_cards:
    start = round(max(0, start), 2)
    end = round(min(TOTAL, start + dur), 2)
    cards.append({"start": start, "end": end, "parts": parts})

MIN_GAP = 0.08
MIN_HOLD = 1.0
for a, b in zip(cards, cards[1:]):
    latest_end = b["start"] - MIN_GAP
    if a["end"] > latest_end:
        a["end"] = round(max(latest_end, a["start"] + MIN_HOLD), 2)

icon_start = round(find("тренажер")["start"] - 0.3, 2)
icon = {"start": icon_start, "end": TOTAL}

beats = []
i = 0
while i < len(words):
    if i + 1 < len(words) and (words[i+1]["start"] - words[i]["end"] < 0.6):
        text = f'{words[i]["text"]} {words[i+1]["text"]}'
        beats.append({"start": words[i]["start"], "text": text})
        i += 2
    else:
        beats.append({"start": words[i]["start"], "text": words[i]["text"]})
        i += 1

FIXES = {
    "недадвнего": "недавнего",
    "дадание": "задания",
    "заданение": "задание",
    "селать": "сделать",
    "рабрать": "разобрать",
    "попастся": "попасться",
    "рассчитывают": "рассчитываем",
    "как та": "как-то",
    "еги": "егэ",
    "гег": "егэ",
    "како какой какой": "какой",
    "бу дет": "будет",
    "скачивате": "скачивайте",
}
for b in beats:
    for k, v in FIXES.items():
        if k in b["text"]:
            b["text"] = b["text"].replace(k, v)
    b["text"] = b["text"].upper()

captions = []
for idx, b in enumerate(beats):
    start = b["start"]
    end = beats[idx+1]["start"] if idx+1 < len(beats) else TOTAL
    captions.append({"start": round(start,2), "end": round(end,2), "text": b["text"]})
captions[0]["start"] = 0.0

plan = {"total": TOTAL, "cards": cards, "icon": icon, "captions": captions}
json.dump(plan, open(f"{WORK}/subtitle_plan.json", "w"), ensure_ascii=False, indent=1)

print(len(cards), "cards,", len(captions), "caption beats, icon from", icon_start)
for c in cards:
    txt = " / ".join(p[0] for p in c["parts"])
    print(f'{c["start"]:6.2f}-{c["end"]:6.2f}  {txt}')
