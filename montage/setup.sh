#!/bin/bash
# Подготовка свежего контейнера: python-зависимости, шрифты (google/fonts), модель Whisper (релиз sherpa-onnx на GitHub).
# Hugging Face в облачной среде закрыт, поэтому модель берётся с GitHub. Повторный запуск ничего не перекачивает.
set -e
cd "$(dirname "$0")"
pip install -q sherpa-onnx numpy pillow fonttools 2>&1 | grep -v -i warning || true
mkdir -p fonts
for f in ofl/manrope/Manrope%5Bwght%5D.ttf ofl/unbounded/Unbounded%5Bwght%5D.ttf \
         ofl/oswald/Oswald%5Bwght%5D.ttf ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf; do
  n=fonts/$(basename "$f"); [ -s "$n" ] || curl -sSfL -m 120 -o "$n" "https://raw.githubusercontent.com/google/fonts/main/$f"
done
M=models/sherpa-onnx-whisper-medium
if [ ! -s $M/medium-encoder.int8.onnx ]; then
  mkdir -p models
  curl -sSfL -m 900 https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-medium.tar.bz2 | tar xj -C models
fi
command -v ffmpeg >/dev/null || { echo "нет ffmpeg"; exit 1; }
echo "setup ok"
