import json

SRC = "/home/user/MyVideo/work/src/IMG_3434.mov"
W = 2160
H = 3840
EYE_Y = 1344  # measured on sample frames, static shot throughout

# (label, in, out, zoom)
CLIPS = [
    ("S1",   0.72,   7.34, 1.08),
    ("S2",  17.68,  24.38, 1.16),
    ("S3",  26.48,  32.50, 1.24),
    ("S4",  34.80,  41.70, 1.12),
    ("S5a", 43.00,  51.04, 1.20),
    ("S5b", 51.16,  53.26, 1.10),
    ("S6",  55.36,  61.78, 1.18),
    ("S7",  63.56,  68.38, 1.26),
    ("S8a", 90.20,  95.72, 1.14),
    ("S8b", 95.88, 102.10, 1.22),
    ("S9a",126.24, 127.09, 1.17),
    ("S9b",128.84, 135.26, 1.17),
    ("S10a",138.08, 144.76, 1.25),
    ("S10b",144.88, 150.50, 1.11),
    ("S11a",153.08, 157.36, 1.19),
    ("S11b",157.88, 165.58, 1.27),
]

EYE_TARGET_FRAC = 0.33  # lowered from 0.42: at zoom>=1.2 that pushed mouth/chin
                          # down into the subtitle-card band (user-reported overlap)

def crop_rect(zoom):
    h = W_SRC_H = H / zoom
    w = W / zoom
    y0 = max(0, EYE_Y - EYE_TARGET_FRAC * h)
    x0 = (W - w) / 2
    # even dims for encoder
    w = int(w // 2 * 2)
    h = int(h // 2 * 2)
    x0 = int(x0 // 2 * 2)
    y0 = int(y0 // 2 * 2)
    return x0, y0, w, h

def build_edited_timeline():
    t = 0.0
    out = []
    for label, iin, iout, zoom in CLIPS:
        dur = iout - iin
        out.append({
            "label": label, "in": iin, "out": iout, "zoom": zoom,
            "edited_start": t, "edited_end": t + dur, "dur": dur,
        })
        t += dur
    return out

if __name__ == "__main__":
    timeline = build_edited_timeline()
    for c in timeline:
        x0,y0,w,h = crop_rect(c["zoom"])
        print(f"{c['label']:5s} src[{c['in']:7.2f},{c['out']:7.2f}] dur={c['dur']:5.2f} "
              f"edited[{c['edited_start']:6.2f},{c['edited_end']:6.2f}] zoom={c['zoom']:.2f} "
              f"crop=({x0},{y0},{w},{h})")
    print("TOTAL:", timeline[-1]["edited_end"])
    json.dump(timeline, open("/home/user/MyVideo/work/timeline.json","w"), ensure_ascii=False, indent=1)
