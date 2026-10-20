#!/usr/bin/env python3
"""Расшифровка речи с таймингами фрагментов.

  python3 montage/transcribe.py <видео> <transcript.json>

Фрагменты режутся по провалам громкости (паузы между словами), каждый распознаётся
Whisper medium (sherpa-onnx). Результат — {"duration", "chunks": [[t0, t1, "текст"], ...]}.
Whisper ошибается в названиях («ЕГ» вместо «ЕГЭ») и может разрезать слово на границе
фрагмента — после запуска фрагменты нужно вычитать и поправить руками (текст, не время).
"""
import json, os, re, subprocess, sys
import numpy as np, sherpa_onnx

ROOT = os.path.dirname(os.path.abspath(__file__))
SR = 16000

def main(video, out):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True).stdout)
    h = SR // 100
    db = 20 * np.log10(np.sqrt(np.array([np.mean(a[i:i + h] ** 2) for i in range(0, len(a) - h, h)])) + 1e-6)
    thr = np.percentile(db, 90) - 17
    # кандидаты на разрез: середины провалов ≥80ms
    cuts, i = [], 0
    while i < len(db):
        if db[i] < thr:
            j = i
            while j < len(db) and db[j] < thr: j += 1
            if j - i >= 8: cuts.append((i + j) / 2 / 100)
            i = j
        else: i += 1
    # фрагменты не короче 0.6с
    bounds, last = [0.0], 0.0
    for c in cuts:
        if c - last >= 0.6: bounds.append(c); last = c
    if dur - bounds[-1] < 0.3: bounds[-1] = dur
    else: bounds.append(dur)
    # фрагменты длиннее 2.8с режем по самой тихой точке внутри (≥0.6с от краёв)
    k = 0
    while k < len(bounds) - 1:
        t0, t1 = bounds[k], bounds[k + 1]
        if t1 - t0 > 2.8:
            seg = db[int((t0 + 0.6) * 100):int((t1 - 0.6) * 100)]
            bounds.insert(k + 1, t0 + 0.6 + int(np.argmin(np.convolve(seg, np.ones(5) / 5, "same"))) / 100)
            continue
        k += 1
    d = os.path.join(ROOT, "models", "sherpa-onnx-whisper-medium")
    rec = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=f"{d}/medium-encoder.int8.onnx", decoder=f"{d}/medium-decoder.int8.onnx",
        tokens=f"{d}/medium-tokens.txt", language="ru", task="transcribe", num_threads=os.cpu_count() or 4)
    pad = np.zeros(int(0.3 * SR), np.float32)
    chunks = []
    for t0, t1 in zip(bounds, bounds[1:]):
        st = rec.create_stream()
        st.accept_waveform(SR, np.concatenate([pad, a[int(t0 * SR):int(t1 * SR)], pad]))
        rec.decode_stream(st)
        txt = re.sub(r"[^\w\s\-ёЁ]", "", st.result.text).lower().strip()
        if txt: chunks.append([round(t0, 2), round(t1, 2), txt])
        print(f"{t0:6.2f}-{t1:6.2f}  {txt}")
    json.dump({"duration": round(dur, 2), "chunks": chunks}, open(out, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main(*sys.argv[1:3])
