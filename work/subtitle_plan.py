import json

WORK = "/home/user/MyVideo/work"
words = json.load(open(f"{WORK}/edited_words.json"))
timeline = json.load(open(f"{WORK}/timeline.json"))
TOTAL = timeline[-1]["edited_end"]

def find(text, occurrence=0):
    matches = [w for w in words if w["text"].strip("?,.") == text]
    return matches[occurrence] if len(matches) > occurrence else None

ACCENT = "#C9F5FF"

# Layer 1 key cards: (start, [(text, is_main)], dur)
# is_main word gets accent color + big size; others white + smaller.
raw_cards = [
    (find("совершенно")["start"], [("ЕГЭ", False), ("УСЛОЖНЯТ?", True)], 2.0),
    (find("фурсенко")["start"], [("ФУРСЕНКО", True), ("ЗАЯВИЛ", False)], 2.0),
    (find("тысяч")["start"], [("10 000", True), ("ШКОЛЬНИКОВ", False)], 2.0),
    (find("баллов")["start"], [("100", True), ("БАЛЛОВ", False)], 1.8),
    (find("ниже")["start"] - 2.2, [("СРЕДНИЙ БАЛЛ", False), ("НИЖЕ", True)], 2.2),
    (find("бюджетные")["start"], [("БЮДЖЕТНЫЕ", True), ("МЕСТА", False)], 2.0),
    (find("хорошие")["start"], [("ХОРОШИЕ", True), ("НОВОСТИ", False)], 1.8),
    (find("опроверг")["start"], [("ОПРОВЕРГ", True)], 1.8),
    (find("обычное")["start"], [("ОБЫЧНОЕ", True), ("ПРЕДЛОЖЕНИЕ", False)], 2.2),
    (find("серьезнее")["start"] - 1.9, [("ГОТОВЬСЯ", False), ("СЕРЬЁЗНЕЕ", True)], 2.2),
    (find("бесплатно")["start"], [("БЕСПЛАТНО", True)], 1.8),
    (find("тренажер")["start"] - 0.5, [("ЕГЭ", False), ("ТРЕНАЖЁР", True)], 2.4),
    (find("тупит")["start"], [("САЙТ", False), ("ТУПИТ", True)], 1.8),
    (TOTAL - 2.3, [("ССЫЛКА", True), ("В ШАПКЕ ПРОФИЛЯ", False)], 2.3),
]

cards = []
for start, parts, dur in raw_cards:
    start = round(max(0, start), 2)
    end = round(min(TOTAL, start + dur), 2)
    cards.append({"start": start, "end": end, "parts": parts})

# 1.2x speed pulls words (and their anchored cards) closer together than the
# original hold durations assumed -- clamp overlaps by shrinking the earlier
# card's tail, never pushing a card's start off its anchoring word.
MIN_GAP = 0.08
MIN_HOLD = 1.0
for a, b in zip(cards, cards[1:]):
    latest_end = b["start"] - MIN_GAP
    if a["end"] > latest_end:
        a["end"] = round(max(latest_end, a["start"] + MIN_HOLD), 2)

# icon + CTA appear together from first app mention to the end
icon_start = round(find("тренажер")["start"] - 0.5, 2)
icon = {"start": icon_start, "end": TOTAL}

# Layer 2 running caption: pairwise grouping of ALL kept words, continuous, no gaps
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

# fix known ASR mishearings for on-screen caption text
FIXES = {
    "протили": "профиля",
    "ипис": "фипи",
    "составителе": "составителей",
    "помощникау": "помощнику",
    "самые обычное": "самое обычное",
    "очереднае": "очередная",
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
# extend first caption to start at 0
captions[0]["start"] = 0.0

plan = {"total": TOTAL, "cards": cards, "icon": icon, "captions": captions}
json.dump(plan, open(f"{WORK}/subtitle_plan.json", "w"), ensure_ascii=False, indent=1)

print(len(cards), "cards,", len(captions), "caption beats, icon from", icon_start)
for c in cards:
    txt = " / ".join(p[0] for p in c["parts"])
    print(f'{c["start"]:6.2f}-{c["end"]:6.2f}  {txt}')
