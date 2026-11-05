#!/bin/bash
# Подготовка исходника: 1080x1920, ускорение (по умолчанию 1.2x), прежний fps, звук с сохранением тона.
#   bash montage/prepare.sh <исходник> <projects/имя/source.mp4> [скорость]
# Дальше расшифровка и монтаж идут уже по ускоренному source.mp4 — все тайминги считаются от него.
set -e
IN="$1"; OUT="$2"; SPEED="${3:-1.2}"
FPS=$(ffprobe -v error -select_streams v -show_entries stream=avg_frame_rate -of csv=p=0 "$IN")
ffmpeg -v error -y -i "$IN" \
  -vf "scale=1080:1920:flags=lanczos,setpts=PTS/${SPEED},fps=${FPS}" \
  -af "atempo=${SPEED}" \
  -c:v libx264 -preset fast -crf 14 -pix_fmt yuv420p -c:a aac -b:a 192k "$OUT"
