import json, subprocess, os

WORK = "/home/user/MyVideo/work"
SRC = f"{WORK}/src/IMG_3434.mov"
os.chdir(WORK)
os.makedirs("clips", exist_ok=True)

timeline = json.load(open("timeline.json"))

def crop_rect(zoom, W=2160, H=3840, EYE_Y=1344):
    h = H / zoom
    w = W / zoom
    y0 = max(0, EYE_Y - 0.42 * h)
    x0 = (W - w) / 2
    w = int(w // 2 * 2)
    h = int(h // 2 * 2)
    x0 = int(x0 // 2 * 2)
    y0 = int(y0 // 2 * 2)
    return x0, y0, w, h

listfile = []
for i, c in enumerate(timeline):
    x0, y0, w, h = crop_rect(c["zoom"])
    dur = c["out"] - c["in"]
    out_path = f"clips/{i:02d}_{c['label']}.mp4"
    vf = f"crop={w}:{h}:{x0}:{y0},scale=1080:1920,fps=30,setsar=1"
    cmd = [
        "ffmpeg", "-y", "-ss", f"{c['in']:.3f}", "-i", SRC,
        "-t", f"{dur:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        out_path,
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    listfile.append(out_path)

with open("concat_list.txt", "w") as f:
    for p in listfile:
        f.write(f"file '{WORK}/{p}'\n")

print("DONE", len(listfile), "clips")
