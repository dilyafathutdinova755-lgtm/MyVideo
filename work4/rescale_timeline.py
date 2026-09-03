import json, subprocess

WORK = "/home/user/MyVideo/work4"

def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path],
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    return float(out)

d_1x = duration(f"{WORK}/cut_1x.mp4")
d_sped = duration(f"{WORK}/cut.mp4")
ratio = d_sped / d_1x
print(f"1x duration={d_1x:.3f}  sped duration={d_sped:.3f}  ratio={ratio:.5f} (theory 1/1.2={1/1.2:.5f})")

timeline = json.load(open(f"{WORK}/timeline.json"))
for c in timeline:
    c["edited_start"] = round(c["edited_start"] * ratio, 4)
    c["edited_end"] = round(c["edited_end"] * ratio, 4)
    c["dur"] = round(c["dur"] * ratio, 4)
# snap the very last clip's edited_end to the measured real duration so nothing
# (icon/CTA/captions) runs a few ms short of or past the actual video end.
timeline[-1]["edited_end"] = round(d_sped, 4)

json.dump(timeline, open(f"{WORK}/timeline.json", "w"), ensure_ascii=False, indent=1)
json.dump({"ratio": ratio}, open(f"{WORK}/speed_ratio.json", "w"))
print("TOTAL (final):", timeline[-1]["edited_end"])
