#!/bin/bash
# Сборка: исходник -> render.py (зум + графика) + SFX, мастер −14 LUFS / TP −1.4 (двухпроходный loudnorm).
set -e
SRC=src.mp4; OUT=${1:-out.mp4}
ffmpeg -v error -y -i $SRC -i sfx.wav -filter_complex "[0:a]pan=mono|c0=0.5*c0+0.5*c1,aformat=channel_layouts=stereo[v];[v][1:a]amix=inputs=2:normalize=0:duration=first[m]" -map "[m]" -c:a pcm_s16le mix.wav
J=$(ffmpeg -hide_banner -i mix.wav -af loudnorm=I=-14:TP=-1.4:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
g(){ echo "$J" | python3 -c "import json,sys;print(json.load(sys.stdin)['$1'])"; }
ffmpeg -v error -i $SRC -f rawvideo -pix_fmt rgb24 - | python3 render.py | \
ffmpeg -v error -y -f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 25 -i - -i mix.wav \
  -filter_complex "[0:v]format=yuv420p[v];[1:a]loudnorm=I=-14:TP=-1.4:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true,aresample=48000[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 17 -profile:v high -r 25 -c:a aac -b:a 256k -movflags +faststart -shortest $OUT
