#!/bin/bash
set -e
cd /home/user/MyVideo/work4

IN=composited_audio.mp4
OUT=final.mp4

# pass 1: measure
MEASURE=$(ffmpeg -i "$IN" -af loudnorm=I=-14:TP=-1.35:LRA=11:print_format=json -f null - 2>&1 | tail -20)
echo "$MEASURE"

I=$(echo "$MEASURE" | grep '"input_i"' | sed -E 's/.*: "([^"]+)".*/\1/')
TP=$(echo "$MEASURE" | grep '"input_tp"' | sed -E 's/.*: "([^"]+)".*/\1/')
LRA=$(echo "$MEASURE" | grep '"input_lra"' | sed -E 's/.*: "([^"]+)".*/\1/')
THRESH=$(echo "$MEASURE" | grep '"input_thresh"' | sed -E 's/.*: "([^"]+)".*/\1/')
OFFSET=$(echo "$MEASURE" | grep '"target_offset"' | sed -E 's/.*: "([^"]+)".*/\1/')

echo "measured I=$I TP=$TP LRA=$LRA THRESH=$THRESH OFFSET=$OFFSET"

ffmpeg -y -i "$IN" -af "loudnorm=I=-14:TP=-1.35:LRA=11:measured_I=$I:measured_TP=$TP:measured_LRA=$LRA:measured_thresh=$THRESH:offset=$OFFSET:linear=true:print_format=json" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 "$OUT"

echo "---- verify ----"
ffmpeg -i "$OUT" -af loudnorm=I=-14:TP=-1.0:print_format=json -f null - 2>&1 | tail -15
