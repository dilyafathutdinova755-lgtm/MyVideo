import json, subprocess, os

WORK = "/home/user/MyVideo/work"
SRC = f"{WORK}/src/IMG_3434.mov"
os.chdir(WORK)
os.makedirs("clips", exist_ok=True)

timeline = json.load(open("timeline.json"))

listfile = []
for i, c in enumerate(timeline):
    src_dur = c["out"] - c["in"]
    out_path = f"clips/{i:02d}_{c['label']}.mp4"
    # no crop/zoom: full 2160x3840 source (already 9:16) straight to 1080x1920.
    # Rendered at ORIGINAL (1x) speed -- the global 1.2x speed-up is applied once,
    # after concat, in speed_up.py (see edl.py for why: avoids per-clip A/V drift).
    vf = "scale=1080:1920,fps=30,setsar=1"
    cmd = [
        "ffmpeg", "-y", "-ss", f"{c['in']:.3f}", "-t", f"{src_dur:.3f}", "-i", SRC,
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
