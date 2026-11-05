#!/usr/bin/env python3
"""Перепроверка спорных мест расшифровки длинными окнами с контекстом.

  python3 montage/recheck.py <видео>                  # весь ролик окнами по 9с с шагом 7.5с
  python3 montage/recheck.py <видео> 5.8 10.5 22 27   # только указанные окна: начало конец начало конец ...

Короткие фрагменты из transcribe.py режутся посреди слов и путают числа и названия. Окно в 5-9с даёт
Whisper контекст. Каждое окно распознаётся дважды (обычная скорость и замедленная 0.85) — совпадение
в обоих прогонах = надёжно. Числа, которых нет в обоих прогонах, на экран не ставить.
"""
import os, subprocess, sys
import numpy as np, sherpa_onnx

SR = 16000
ROOT = os.path.dirname(os.path.abspath(__file__))

def main(video, wins):
    d = os.path.join(ROOT, "models", "sherpa-onnx-whisper-medium")
    rec = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=f"{d}/medium-encoder.int8.onnx", decoder=f"{d}/medium-decoder.int8.onnx",
        tokens=f"{d}/medium-tokens.txt", language="ru", task="transcribe", num_threads=os.cpu_count() or 4)
    def audio(flt):
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-ac", "1", "-ar", str(SR), "-af", flt, "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    a = {1.0: audio("anull"), 0.85: audio("atempo=0.85")}
    dur = len(a[1.0]) / SR
    if not wins:
        t = 0.0
        while t < dur - 0.5:
            wins += [t, min(dur, t + 9)]; t += 7.5
    for s, e in zip(wins[::2], wins[1::2]):
        for k, x in a.items():
            st = rec.create_stream()
            st.accept_waveform(SR, np.concatenate([np.zeros(4800, np.float32), x[int(s / k * SR):int(e / k * SR)]]))
            rec.decode_stream(st)
            print(f"[{s:5.1f}-{e:5.1f}] x{k}: {st.result.text}")

if __name__ == "__main__":
    main(sys.argv[1], [float(v) for v in sys.argv[2:]])
