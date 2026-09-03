import json

SRC = "/home/user/MyVideo/work4/src/IMG_3440.mov"
W = 2160
H = 3840

# (label, in, out) -- triple-retried opening line ("неделя это максимально /
# минимальный / идеальный...") reduced to the final complete take + its
# anaphoric continuation; a nonsense two-syllable stumble ("пом тпипу")
# mid-sentence cut out.
CLIPS = [
    ("R1",  0.23,  15.94),   # hook
    ("R2", 27.99,  61.30),   # "неделя это идеальный..." (final take) + continuation
    ("R3a",65.31,  72.60),   # "но это не значит...бесплатно приложением"
    ("R3b",73.00,  80.04),   # "...ЕГЭ тренажера...клад в мире егэ" (stray "пом тпипу" cut)
    ("R4", 80.07,  89.10),   # CTA: "если вы о нем...осталось неделя"
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
    json.dump(timeline, open("/home/user/MyVideo/work4/timeline.json","w"), ensure_ascii=False, indent=1)
