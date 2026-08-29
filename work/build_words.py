import json

WORK = "/home/user/MyVideo/work"
timeline = json.load(open(f"{WORK}/timeline.json"))
words = json.load(open(f"{WORK}/audio/words.json"))  # [text, start, end]

# run AFTER rescale_timeline.py: timeline.json's edited_start is already in
# final sped-up output time; RATIO converts an offset measured in original
# (1x) source seconds into that same output time domain.
RATIO = json.load(open(f"{WORK}/speed_ratio.json"))["ratio"]

edited_words = []
for c in timeline:
    lo, hi = c["in"], c["out"]
    for w, ws, we in words:
        # word counted in this clip if it starts within [lo,hi]
        if lo <= ws < hi:
            ews = c["edited_start"] + (ws - lo) * RATIO
            ewe = c["edited_start"] + (min(we, hi) - lo) * RATIO
            edited_words.append({"text": w, "start": round(ews,3), "end": round(ewe,3), "clip": c["label"]})

json.dump(edited_words, open(f"{WORK}/edited_words.json","w"), ensure_ascii=False, indent=1)
print(len(edited_words), "words mapped")
for w in edited_words:
    print(f"{w['start']:7.2f}-{w['end']:7.2f}  {w['clip']:5s} {w['text']}")
