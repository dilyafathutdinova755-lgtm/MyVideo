import json, subprocess, os

WORK = "/home/user/MyVideo/work"
SRC = f"{WORK}/src/IMG_3434.mov"
os.chdir(WORK)
os.makedirs("clips", exist_ok=True)

timeline = json.load(open("timeline.json"))
SPEED = 1.2  # keep in sync with edl.py

listfile = []
for i, c in enumerate(timeline):
    src_dur = c["out"] - c["in"]
    out_path = f"clips/{i:02d}_{c['label']}.mp4"
    # no crop/zoom: full 2160x3840 source (already 9:16) straight to 1080x1920.
    # speed up 1.2x: setpts compresses video, atempo compresses audio (pitch-preserving).
    vf = f"scale=1080:1920,fps=30,setsar=1,setpts=PTS/{SPEED}"
    af = f"atempo={SPEED}"
    cmd = [
        "ffmpeg", "-y", "-ss", f"{c['in']:.3f}", "-i", SRC,
        "-t", f"{src_dur:.3f}",
        "-vf", vf, "-af", af,
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
