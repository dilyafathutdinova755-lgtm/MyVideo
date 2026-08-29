import json

SRC = "/home/user/MyVideo/work2/src/IMG_3436.mov"
W = 2160
H = 3840

# (label, in, out) -- duplicate hook, false starts, and the "trial lesson"
# advice removed; it's retried FOUR times total (R7 was wrongly kept as a
# separate point in an earlier pass -- it's actually attempt #1 of the same
# advice as the R8a/R8b take, just cut short at "...пробное занятие
# посмотреть"; attempts #2/#3 were already correctly dropped). Default to
# the last, most complete take (R8a+R8b) only.
CLIPS = [
    ("R1",   8.91,  14.06),   # hook, take 2 ("...обсудим как же тогда выбрать правильно")
    ("R2",  18.87,  37.74),   # "я здесь не буду упоминать...небольшую сумму"
    ("R3",  39.99,  42.34),   # "мы в такие источники не верим"
    ("R4",  48.19,  51.97),   # "я вообще в целом иногда даже..." take 2 of dup
    ("R5",  51.99,  67.58),   # "учитывая что все задания...ваше дело"
    ("R6",  69.95,  71.24),   # "на что я вам советую" (stray "об" false-start dropped)
    ("R8a",105.87, 116.86),   # final take of 4x-retried advice, part 1
    ("R8b",118.39, 135.02),   # ...part 2 ("чтобы оценить и почувствовать...развиваться")
    ("R9", 137.91, 142.60),   # "это наверное единственное..."
    ("R10",142.65, 150.06),   # CTA: "а если вы занимаетесь самоподготовкой..."
]

SPEED = 1.2  # user requested: always play back at 1.2x
SRC_FPS = 30

def snap(t):
    return round(round(t * SRC_FPS) / SRC_FPS, 6)

def crop_rect(zoom=1.0):
    # no crop/zoom per user request: full source frame (already 9:16) -> 1080x1920.
    return 0, 0, W, H

def build_edited_timeline():
    # 1x (pre-speedup) timeline. Speed change applied once, globally, after
    # concat (see speed_up.py) -- avoids per-clip A/V drift across clips.
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
    json.dump(timeline, open("/home/user/MyVideo/work2/timeline.json","w"), ensure_ascii=False, indent=1)
