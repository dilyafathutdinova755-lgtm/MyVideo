import subprocess

WORK = "/home/user/MyVideo/work4"
SPEED = 1.2

# Global, single-pass speed-up applied to the WHOLE assembled cut (not per-clip).
# setpts before fps: fps resamples the already-compressed timeline to a true,
# clean 30fps CFR stream, so the frame count genuinely matches the sped-up
# duration (this is what per-clip rendering got wrong: fps ran before setpts
# there, locking frame count to the pre-speedup timeline).
vf = f"setpts=PTS/{SPEED},fps=30"
af = f"atempo={SPEED}"

cmd = [
    "ffmpeg", "-y", "-i", f"{WORK}/cut_1x.mp4",
    "-vf", vf, "-af", af,
    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
    f"{WORK}/cut.mp4",
]
print(" ".join(cmd))
subprocess.run(cmd, check=True)
