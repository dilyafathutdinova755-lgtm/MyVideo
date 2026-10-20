#!/bin/bash
# Сборка по плейбуку: исходник -> pb.py (зум + графика). Звук исходника копируется без обработки (§12).
set -e
SRC=${SRC:-src.mp4}; OUT=${1:-out_pb.mp4}
ffmpeg -v error -i "$SRC" -f rawvideo -pix_fmt rgb24 - | python3 pb.py | \
ffmpeg -v error -y -f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 25 -i - -i "$SRC" \
  -map 0:v -map 1:a -c:v libx264 -preset slow -crf 17 -profile:v high -pix_fmt yuv420p -r 25 \
  -c:a copy -movflags +faststart -shortest "$OUT"
