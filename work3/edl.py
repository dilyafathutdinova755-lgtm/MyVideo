import json

SRC = "/home/user/MyVideo/work3/src/IMG_3438.mov"
W = 2160
H = 3840

# (label, in, out) -- duplicate hook, duplicate "domoversiya" intro, a stutter
# ("все самые все самые"), a duplicate FIPI paragraph (second take kept), and
# a duplicate CTA ending (second, cleaner take kept) removed.
CLIPS = [
    ("R1",   5.51,  14.30),   # hook, take 2 ("...поговорим где искать...домоверсии")
    ("R2",  23.47,  30.90),   # "кто все еще не знает...тонкости", take 2
    ("R3a", 34.83,  50.78),   # "если вы знаете...на егэ 2027"
    ("R3b", 50.80,  69.42),   # "какие форматы...домоверсию точно можем"
    ("R4",  97.87, 116.14),   # FIPI paragraph, take 2 (clean retry)
    ("R5", 118.51, 133.90),   # "слава богу ситуация изменилась...шапке профиля"
    ("R6", 142.11, 145.82),   # CTA ending, take 2 ("скачивайте...высокие балы")
]

SPEED = 1.2
SRC_FPS = 30

def snap(t):
    return round(round(t * SRC_FPS) / SRC_FPS, 6)

def crop_rect(zoom=1.0):
    return 0, 0, W, H

def build_edited_timeline():
    t = 0.0
    out = []
    for label, iin, iout in CLIPS:
        iin, iout = snap(iin), snap(iout)
        dur = iout - iin
        out.append({
            "label": label, "in": iin, "out": iout, "zoom": 1.0,
            "edited_start": t, "edited_end": t + dur, "dur": dur,
        })
        t += dur
    return out

if __name__ == "__main__":
    timeline = build_edited_timeline()
    for c in timeline:
        print(f"{c['label']:5s} src[{c['in']:7.2f},{c['out']:7.2f}] dur={c['dur']:5.2f} "
              f"edited[{c['edited_start']:6.2f},{c['edited_end']:6.2f}]")
    print("TOTAL:", timeline[-1]["edited_end"])
    json.dump(timeline, open("/home/user/MyVideo/work3/timeline.json","w"), ensure_ascii=False, indent=1)
