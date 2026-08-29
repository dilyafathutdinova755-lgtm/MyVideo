import json, subprocess

WORK = "/home/user/MyVideo/work"
timeline = json.load(open(f"{WORK}/timeline.json"))

t = 0.0
for i, c in enumerate(timeline):
    path = f"{WORK}/clips/{i:02d}_{c['label']}.mp4"
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path],
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    actual_dur = float(out)
    c["edited_start"] = round(t, 3)
    c["dur"] = round(actual_dur, 3)
    t += actual_dur
    c["edited_end"] = round(t, 3)

json.dump(timeline, open(f"{WORK}/timeline.json", "w"), ensure_ascii=False, indent=1)
print("TOTAL (actual):", timeline[-1]["edited_end"])
