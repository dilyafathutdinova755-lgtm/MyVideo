#!/usr/bin/env python3
"""Движок монтажа по плейбуку (montage/PLAYBOOK.md).

Видео + партитура edit.json -> готовый ролик и слои для ручной доработки.
Временная последовательность исходника не меняется: только зум, графика и субтитры поверх.

  python3 montage/engine.py projects/<имя>/edit.json --stills 1.0 4.5 ...  # стоп-кадры для проверки
  python3 montage/engine.py projects/<имя>/edit.json --out out/<имя>        # полный рендер

Полный рендер кладёт в папку --out:
  final.mp4      — готовый ролик (звук исходника без обработки)
  subs.srt       — субтитры текстом, чтобы переоформить их в редакторе
  с флагом --layers ещё слои для ручной доработки в монтажке:
  base_zoom.mp4  — только видеоряд с зумами, без графики
  overlay.mov    — вся графика и субтитры с альфа-каналом, ProRes 4444 (~20 МБ/с)
Формат edit.json — montage/EDIT_FORMAT.md.
"""
import argparse, json, math, os, subprocess, sys
from fractions import Fraction
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920

# ---------- токены (плейбук §3.1) ----------
PAL = {
    "milk": (0xFF, 0xF8, 0xF1), "ink": (0x30, 0x2D, 0x3A), "muted": (0x5E, 0x58, 0x6B),
    "cream": (0xFF, 0xF8, 0xF1), "vanilla": (0xF4, 0xE7, 0xA8), "blush": (0xEF, 0xC6, 0xD8),
    "lavender": (0xD8, 0xCC, 0xF0), "sky": (0xC5, 0xE3, 0xF0), "mint": (0xC9, 0xE2, 0xD2),
    "peach": (0xF1, 0xCF, 0xB7), "plum": (0x62, 0x4B, 0x69), "scrim": (0x24, 0x21, 0x2B),
}
def C(name): return PAL[name] if isinstance(name, str) else tuple(name)

# ---------- шрифтовые роли (§4.1) ----------
FONTS = {
    "BODY": ("Manrope%5Bwght%5D.ttf", 700),
    "WIDE": ("Unbounded%5Bwght%5D.ttf", 800),
    "COND": ("Oswald%5Bwght%5D.ttf", 600),
    "EDIT": ("CormorantGaramond-Italic%5Bwght%5D.ttf", 600),
}
_fc = {}
def font(role, size):
    k = (role, size)
    if k not in _fc:
        path, wght = FONTS[role]
        f = ImageFont.truetype(os.path.join(ROOT, "fonts", path), size)
        f.set_variation_by_axes([wght])
        _fc[k] = f
    return _fc[k]

SIDE = 80          # боковые поля важных элементов (§6.1)

# ---------- easing ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def out_cubic(p): return 1 - (1 - clamp(p)) ** 3
def out_back(p, c1=1.0):
    p = clamp(p); c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
def in_out(p): return 0.5 - 0.5 * math.cos(math.pi * clamp(p))


# ---------- растеризация ----------
def text_img(txt, fnt, fill, glow=0.55, blur=14, pad=48, track=0):
    """Текст без обводки; на видео читаемость держит мягкая тёмная тень (§3.3)."""
    widths = [fnt.getlength(c) for c in txt] if track else None
    l, t, r, b = fnt.getbbox(txt, anchor="ls")
    if track: r = l + sum(widths) + track * (len(txt) - 1)
    w, h = int(r - l + 2 * pad), int(b - t + 2 * pad)
    ox, oy = pad - l, pad - t
    def draw(d, col):
        if not track:
            d.text((ox, oy), txt, font=fnt, fill=col, anchor="ls"); return
        x = ox
        for c, cw in zip(txt, widths):
            d.text((x, oy), c, font=fnt, fill=col, anchor="ls"); x += cw + track
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if glow:
        m = Image.new("L", (w, h), 0); draw(ImageDraw.Draw(m), 255)
        sh = m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, int(v * glow * 1.6)))
        img.paste(Image.new("RGBA", (w, h), PAL["scrim"] + (255,)), (0, 4), sh)
    draw(ImageDraw.Draw(img), fill + (255,))
    return img, (ox, oy)

def soft_shadow(img, blur=22, alpha=0.18, dy=12, col=None):
    """Тёмно-сливовая тень 0.12-0.20, смещение 8-14px, размытие 24-40px (§3.4)."""
    w, h = img.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = img.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    out.paste(Image.new("RGBA", (w, h), (col or PAL["plum"]) + (255,)), (0, dy), sh)
    out.alpha_composite(img)
    return out

def glowed(shape, alpha=0.5, blur=8):
    w, h = shape.size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = shape.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    img.paste(Image.new("RGBA", (w, h), PAL["scrim"] + (255,)), (0, 3), sh)
    img.alpha_composite(shape)
    return img


# ---------- слой ----------
Z_VIDEO, Z_SLIDE, Z_ON_SLIDE, Z_SUBS = 5, 8, 9, 10

class El:
    """Картинка + якорь + [t0, t1) + движение входа (M01/M02/M04/M07) + выход."""
    def __init__(self, img, cx, cy, t0, t1, motion="M01", z=Z_VIDEO, out=0.10, rot=0.0):
        self.img, self.cx, self.cy, self.t0, self.t1 = img, cx, cy, t0, t1
        self.motion, self.z, self.out, self.rot = motion, z, out, rot

    def state(self, t):
        if t < self.t0 or t >= self.t1: return None
        lt, rem = t - self.t0, self.t1 - t
        s, a, dx, dy, rot = 1.0, 1.0, 0.0, 0.0, self.rot
        m = self.motion
        if m == "M01":            # мягкий подъём: +32px, 0.98, 200ms
            p = out_cubic(lt / 0.20); dy, s, a = 32 * (1 - p), 0.98 + 0.02 * p, clamp(lt / 0.12)
        elif m == "M02":          # упругий акцент: 0.90 -> 1.035 -> 1.0, 260ms
            p = clamp(lt / 0.26); s = 0.90 + 0.10 * out_back(p, 1.25); a = clamp(lt / 0.09)
        elif m == "M04":          # строка с наклоном: x+44, -6°, 230ms
            p = out_cubic(lt / 0.23); dx, rot, a = 44 * (1 - p), self.rot - 6 * (1 - p), clamp(lt / 0.12)
        elif m == "M07":          # предметная вставка: 0.9, y+40, -3°, 300ms
            p = clamp(lt / 0.30); s = 0.90 + 0.10 * out_back(p, 0.9); dy = 40 * (1 - out_cubic(p))
            rot = self.rot - 3 * (1 - out_cubic(p)); a = clamp(lt / 0.12)
        elif m == "SUB":          # субтитр: короткий подъём 14px, 120ms
            p = out_cubic(lt / 0.12); dy, a = 14 * (1 - p), clamp(lt / 0.08)
        elif m == "FADE":
            a = in_out(lt / 0.30)
        if self.out:
            q = clamp(rem / self.out); a *= q
            if m == "M07": s *= 0.94 + 0.06 * q
        return s, a, dx, dy, rot

def place(frame, img, cx, cy, st):
    s, a, dx, dy, rot = st
    if rot: img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(s - 1) > 1e-3:
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.BICUBIC)
    if a < 0.999:
        img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    x, y = round(cx + dx - img.width / 2), round(cy + dy - img.height / 2)
    tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0)); tmp.paste(img, (x, y), img)
    frame.alpha_composite(tmp)


# ===================== КОМПОНЕНТЫ =====================
def composition(ev, z):
    """Крупная многосоставная надпись (§5.3): геометрия считается заранее, строки
    раскрываются в зарезервированных местах. Базовая линия: prev + lead * кегль."""
    rows = []
    for p in ev["parts"]:
        f = font(p.get("role", "WIDE"), p["size"])
        on_slide = z >= Z_ON_SLIDE
        img, (ox, oy) = text_img(p["text"], f, C(p.get("color", "ink" if on_slide else "cream")),
                                 glow=p.get("glow", 0 if on_slide else 0.55), track=p.get("track", 0))
        rows.append(dict(img=img, oy=oy, size=p["size"], cap=-f.getbbox("Н", anchor="ls")[1], p=p))
    base = [0.0]
    for r in rows[1:]: base.append(base[-1] + r["p"].get("lead", 1.0) * r["size"])
    shift = ev.get("cy", 1185) - (-rows[0]["cap"] + base[-1]) / 2
    out = []
    for r, b in zip(rows, base):
        img, by, p = r["img"], b + shift, r["p"]
        if p.get("flip"):        # перевёрнутая строка занимает ту же полосу [by - cap, by]
            img = img.rotate(180)
            cy = by - r["cap"] - (img.height - r["oy"]) + img.height / 2
        else:
            cy = by - r["oy"] + img.height / 2
        cx = ev.get("cx", W / 2) + p.get("dx", 0)
        if not (cx - img.width / 2 + 48 >= SIDE - 1 and cx + img.width / 2 - 48 <= W - SIDE + 1):
            raise ValueError(f"строка «{p['text']}» шире поля ({img.width - 96}px) — уменьшить кегль")
        out.append(El(img, cx, cy, p["t"], ev["t1"], p.get("motion", "M01"), z=z, out=ev.get("out", 0.12)))
    return out

def answer_sheet(ev):
    """Лист ответов: молочная карточка, пастельная шапка, строки — абстрактные полосы (без цифр)."""
    pw, ph, pad = 260, 320, 50
    img = Image.new("RGBA", (pw + 2 * pad, ph + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    head = C(ev.get("accent", "blush"))
    d.rounded_rectangle((pad, pad, pad + pw, pad + ph), 26, fill=PAL["milk"] + (255,))
    d.rounded_rectangle((pad, pad, pad + pw, pad + 66), 26, fill=head + (255,))
    d.rectangle((pad, pad + 40, pad + pw, pad + 66), fill=head + (255,))
    d.text((pad + pw / 2, pad + 47), ev.get("title", "ОТВЕТЫ"), font=font("WIDE", 26), fill=PAL["ink"] + (255,), anchor="ms")
    for i, wl in enumerate((150, 112, 168, 96, 138)):
        y = pad + 96 + i * 42
        d.ellipse((pad + 28, y, pad + 46, y + 18), fill=PAL["vanilla"] + (255,), outline=PAL["ink"] + (255,), width=3)
        d.rounded_rectangle((pad + 62, y + 3, pad + 62 + wl, y + 15), 6, fill=(0xE6, 0xDF, 0xE3, 255))
    return soft_shadow(img)

class Sheet(El):
    """Лист: M07-вход; если задан flip_t — переворачивается вверх ногами (480ms)."""
    def __init__(self, ev, z):
        super().__init__(answer_sheet(ev), ev["cx"], ev["cy"], ev["t0"], ev["t1"], "M07", z=z, out=0.16, rot=ev.get("tilt", 4))
        self.flip_t = ev.get("flip_t")
    def state(self, t):
        st = super().state(t)
        if st is None or self.flip_t is None: return st
        s, a, dx, dy, rot = st
        return s, a, dx, dy, rot + 180 * in_out((t - self.flip_t) / 0.48)

class Eyes(El):
    """Реакция «подглядываю»: глаза выглядывают из-за предмета (слой под ним), косятся, моргают."""
    def __init__(self, ev, z):
        super().__init__(None, ev["cx"], ev["cy"], ev["t0"], ev["t1"], "none", z=z - 1, out=0.14)
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        lt = t - self.t0
        keys = [(0.0, (0, 11)), (0.55, (0, 11)), (0.75, (-13, 2)), (1.05, (-13, 2)), (1.25, (0, 11))]
        dx, dy = keys[-1][1]
        for (ta, va), (tb, vb) in zip(keys, keys[1:]):
            if ta <= lt < tb:
                p = in_out((lt - ta) / (tb - ta)); dx, dy = va[0] + (vb[0] - va[0]) * p, va[1] + (vb[1] - va[1]) * p
        blink = 1.0 - 0.85 * max(0.0, 1 - abs(lt - 0.95) / 0.06)
        img = Image.new("RGBA", (230, 150), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        for ex in (66, 164):
            ey, rx, ry = 76, 44, 52 * blink
            d.ellipse((ex - rx, ey - ry, ex + rx, ey + ry), fill=PAL["milk"] + (255,), outline=PAL["ink"] + (255,), width=7)
            if blink > 0.4:
                d.ellipse((ex + dx - 17, ey + dy - 17, ex + dx + 17, ey + dy + 17), fill=PAL["ink"] + (255,))
                d.ellipse((ex + dx - 9, ey + dy - 11, ex + dx - 2, ey + dy - 4), fill=PAL["milk"] + (255,))
        self.img = soft_shadow(img, blur=10, alpha=0.25, dy=5)
        return 1.0, st[1], 0.0, 130 * (1 - out_back(lt / 0.32, 1.2)), 0.0

def app_icon(ev, z):
    """Иконка ЕГЭ Тренажёра — всегда оригинальный файл, без перерисовки и перекраски:
    по ней приложение узнают в сторе. 100% непрозрачность, мягкая тень."""
    ic = Image.open(os.path.join(ROOT, "assets", "ege_icon.png")).convert("RGBA")
    size = ev.get("size", 280)
    ic = ic.resize((size, round(ic.height * size / ic.width)), Image.LANCZOS)
    pad = 50
    img = Image.new("RGBA", (ic.width + 2 * pad, ic.height + 2 * pad), (0, 0, 0, 0))
    img.alpha_composite(ic, (pad, pad))
    img = soft_shadow(img, blur=24, alpha=0.30, dy=12, col=PAL["scrim"])
    return [El(img, ev["cx"], ev["cy"], ev["t0"], ev["t1"], ev.get("motion", "M07"), z=z, out=ev.get("out", 0.16),
               rot=ev.get("tilt", 0))]

class WriteLines(El):
    """Строки текста дописываются одна за другой (абстрактные полосы, маска слева направо)."""
    def __init__(self, ev, z):
        super().__init__(None, ev["cx"], ev["cy"], ev["t0"], ev["t1"], "none", z=z, out=0.12)
        self.widths, self.per = ev.get("widths", [500, 400, 450]), ev.get("per", 0.22)
        self.light = z >= Z_ON_SLIDE
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        pad, lh, gap = 30, 14, 22
        w = max(self.widths) + 2 * pad + 30; h = len(self.widths) * (lh + gap) + 2 * pad
        shape = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shape)
        line = PAL["ink"] + (200,) if self.light else PAL["cream"] + (235,)
        for i, wl in enumerate(self.widths):
            p = out_cubic((t - self.t0 - i * self.per) / self.per)
            if p <= 0: continue
            y = pad + i * (lh + gap)
            d.ellipse((pad - 4, y - 1, pad + 12, y + 15), fill=PAL["vanilla"] + (255,))
            d.rounded_rectangle((pad + 26, y, pad + 26 + max(lh, wl * p), y + lh), 7, fill=line)
        self.img = shape if self.light else glowed(shape)
        return st

def doc_card(ev):
    """Молочная карточка-документ со строками (для слайдов «разбор»). Строки рисует WriteLines поверх."""
    cw, ch, pad = ev.get("w", 640), ev.get("h", 300), 50
    img = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, pad + cw, pad + ch), 32, fill=(255, 255, 255, 255))
    return soft_shadow(img, blur=26, alpha=0.16, dy=12)

def padlock(op, light):
    img = Image.new("RGBA", (96, 118), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    lift = 16 * op
    sh = (PAL["ink"] if light else PAL["cream"]) + (255,)
    d.arc((26, 12 - lift, 70, 62 - lift), 180, 360, fill=sh, width=9)
    d.line((30, 37 - lift, 30, 56 - lift * 1.9), fill=sh, width=9)
    d.line((66, 37 - lift, 66, 56 - lift), fill=sh, width=9)
    d.rounded_rectangle((14, 54, 82, 108), 14, fill=PAL["blush"] + (255,))
    d.ellipse((42, 68, 54, 80), fill=PAL["ink"] + (255,)); d.rectangle((46, 76, 50, 92), fill=PAL["ink"] + (255,))
    return img

class LockPath(El):
    """Путь из сегментов заполняется; в конце пути открывается замок. Процесс, а не данные — без чисел."""
    def __init__(self, ev, z):
        super().__init__(None, ev["cx"], ev["cy"], ev["t0"], ev["t1"], "M01", z=z, out=0.12)
        self.n, self.f0, self.fd = ev.get("segments", 4), ev["fill_t0"], ev["fill_dur"]
        self.unlock = self.f0 + self.fd
        self.light = z >= Z_ON_SLIDE
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        sw, sh_, gap, pad, lw = 104, 22, 16, 30, 100
        w = self.n * (sw + gap) + lw + 2 * pad; h = 120 + 2 * pad
        shape = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shape)
        yb = pad + 64
        edge = PAL["ink"] + (200,) if self.light else PAL["cream"] + (230,)
        for i in range(self.n):
            x = pad + i * (sw + gap)
            d.rounded_rectangle((x, yb, x + sw, yb + sh_), 11, outline=edge, width=3)
            p = clamp((t - self.f0 - i * self.fd / self.n) / (self.fd / self.n))
            if p > 0:
                d.rounded_rectangle((x, yb, x + max(22, sw * out_cubic(p)), yb + sh_), 11, fill=PAL["vanilla"] + (255,))
        op = clamp(out_back((t - self.unlock) / 0.3, 1.2), 0, 1.2) if t >= self.unlock else 0
        lk = padlock(op, self.light)
        k = 1 + 0.12 * math.sin(math.pi * clamp((t - self.unlock) / 0.3))
        lk = lk.resize((round(lk.width * k), round(lk.height * k)), Image.BICUBIC)
        lx = pad + self.n * (sw + gap) + lw / 2
        shape.alpha_composite(lk, (round(lx - lk.width / 2), round(yb + sh_ / 2 - lk.height * 0.62)))
        self.img = shape if self.light else glowed(shape, 0.45, 7)
        return st

def arrow_img(L, prog, col, width, shadow):
    """Стрелка вверх; прорисовка по длине prog 0..1. Другие направления — через rot."""
    pad = 34
    size = (90, L + 2 * pad)
    def draw(d, c, w):
        x = size[0] // 2; ye = pad + L - L * prog
        d.line((x, pad + L, x, ye), fill=c, width=w)
        if prog > 0.75:
            k = (prog - 0.75) / 0.25 * 24
            d.line((x - k, ye + k, x, ye), fill=c, width=w); d.line((x + k, ye + k, x, ye), fill=c, width=w)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    if shadow:
        m = Image.new("L", size, 0); draw(ImageDraw.Draw(m), 255, width + 6)
        m = m.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.55))
        img.paste(Image.new("RGBA", size, PAL["scrim"] + (255,)), (0, 3), m)
    draw(ImageDraw.Draw(img), col + (255,), width)
    return img

ARROW_DIR = {"up": 0, "down": 180, "right": -90, "left": 90}
class Arrow(El):
    """M10: линия прорисовывается за 180-300ms, затем наконечник. bob — мягкое покачивание после."""
    def __init__(self, ev, z):
        super().__init__(None, ev["cx"], ev["cy"], ev["t0"], ev["t1"], "none", z=z,
                         out=0.0 if z >= Z_ON_SLIDE else 0.12, rot=ARROW_DIR[ev.get("dir", "up")])
        self.L, self.dt, self.bob = ev.get("length", 150), ev.get("draw", 0.26), ev.get("bob_from")
        on_slide = z >= Z_ON_SLIDE
        self.col = C(ev.get("color", "plum" if on_slide else "vanilla"))
        self.shadow, self.width = not on_slide, ev.get("width", 8)
        self.cache = {}
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        p = round(out_cubic((t - self.t0) / self.dt), 3)
        if p not in self.cache: self.cache[p] = arrow_img(self.L, max(p, 0.02), self.col, self.width, self.shadow)
        self.img = self.cache[p]
        s, a, dx, dy, rot = st
        if self.bob is not None and t > self.bob:
            dy -= 6 * math.sin(2 * math.pi * (t - self.bob) / 1.1)
        return s, a, dx, dy, rot

def nowifi(ev, z):
    """Значок Wi-Fi, перечёркнутый наискосок: «без интернета». Светлый на видео, тёмный на слайде."""
    size = ev.get("size", 240); pad = 40
    on_slide = z >= Z_ON_SLIDE
    col, slash = PAL["ink"], PAL["plum"]
    S = size + 2 * pad
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    if not on_slide:      # плашка-стикер: читается на любом фоне
        d.rounded_rectangle((pad * 0.35, pad * 0.35, S - pad * 0.35, S - pad * 0.35), 44, fill=PAL["milk"] + (255,))
    cx, cy = S / 2, pad + size * 0.80
    w = max(8, size // 18)
    for r in (0.74, 0.52, 0.30):
        R = size * r * 0.78
        d.arc((cx - R, cy - R, cx + R, cy + R), 225, 315, fill=col + (255,), width=w)
    d.ellipse((cx - w, cy - w, cx + w, cy + w), fill=col + (255,))
    # просвет вокруг черты, чтобы она читалась поверх дуг
    a, b = (pad + size * 0.12, pad + size * 0.10), (pad + size * 0.90, pad + size * 0.94)
    gap = Image.new("L", (S, S), 0); ImageDraw.Draw(gap).line((*a, *b), fill=255, width=w * 3)
    img.paste((0, 0, 0, 0), (0, 0), gap)
    ImageDraw.Draw(img).line((*a, *b), fill=slash + (255,), width=w + 2)
    if not on_slide: img = soft_shadow(img, blur=22, alpha=0.22, dy=10)
    return [El(img, ev["cx"], ev["cy"], ev["t0"], ev["t1"], ev.get("motion", "M07"), z=z, out=ev.get("out", 0.12))]

def link_icon(ev, z):
    w = h = 150
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    col = C(ev.get("color", "vanilla"))
    for off in (-25, 25):
        box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle((w / 2 - 36 + off, h / 2 - 18, w / 2 + 36 + off, h / 2 + 18), 18,
                                               outline=col + (255,), width=10)
        img.alpha_composite(box)
    img = img.rotate(-45, resample=Image.BICUBIC)
    if z < Z_ON_SLIDE: img = glowed(img, 0.6, 6)
    return [El(img, ev["cx"], ev["cy"], ev["t0"], ev["t1"], "M07", z=z, out=ev.get("out", 0.0))]

def plaque(ev, z):
    """Тёмный текст на пастельной плашке (§3.2)."""
    f = font(ev.get("role", "WIDE"), ev["size"])
    l, t, r, b = f.getbbox(ev["text"], anchor="ls")
    px, py, pad = 34, 22, 40
    w, h = int(r - l + 2 * px + 2 * pad), int(b - t + 2 * py + 2 * pad)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, w - pad, h - pad), 30, fill=C(ev.get("fill", "vanilla")) + (255,))
    d.text((pad + px - l, pad + py - t), ev["text"], font=f, fill=C(ev.get("color", "ink")) + (255,), anchor="ls")
    img = soft_shadow(img, blur=20, alpha=0.16, dy=10)
    return [El(img, ev.get("cx", W / 2), ev["cy"], ev["t0"], ev["t1"], ev.get("motion", "M02"), z=z, out=ev.get("out", 0.0))]

def text_line(ev, z):
    """Одиночная строка (на слайде — тёмная без тени, на видео — светлая с тенью)."""
    on_slide = z >= Z_ON_SLIDE
    img, _ = text_img(ev["text"], font(ev.get("role", "WIDE"), ev["size"]),
                      C(ev.get("color", "ink" if on_slide else "cream")), glow=0 if on_slide else 0.55)
    return [El(img, ev.get("cx", W / 2), ev["cy"], ev["t0"], ev["t1"], ev.get("motion", "M01"), z=z,
               out=ev.get("out", 0.0 if on_slide else 0.12), rot=ev.get("rot", 0))]


class Slide(El):
    """Полноэкранный слайд с фоном (M12): плоскость въезжает снизу за 340ms, на ней одно
    размытое пастельное пятно. Содержимое слайда — события с "on_slide": true."""
    def __init__(self, ev):
        super().__init__(None, 0, 0, ev["t0"], ev["t1"], "none", z=Z_SLIDE, out=0.0)
        bg = np.array(C(ev.get("bg", "milk")), np.float32)
        blob = np.array(C(ev.get("blob", "blush")), np.float32)
        bx, by = ev.get("blob_at", [540, 910])
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        m = np.exp(-(((xx - bx) / 520) ** 2 + ((yy - by) / 470) ** 2) * 1.6) * ev.get("blob_strength", 0.85)
        rgb = bg * (1 - m[..., None]) + blob * m[..., None]
        rgb += np.random.default_rng(3).uniform(-1.5, 1.5, rgb.shape).astype(np.float32)   # дизеринг против колец
        self.bg = Image.fromarray(np.clip(rgb + 0.5, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        self.t_in, self.t_out = 0.34, 0.20
        self.subs = ev.get("subs", "show")
    def cover(self, t, y_line):
        """Насколько плоскость закрывает горизонталь y_line в момент t (для цвета субтитров)."""
        if t < self.t0 or t >= self.t1: return 0.0
        top = H * (1 - out_cubic((t - self.t0) / self.t_in))
        return clamp((self.t1 - t) / self.t_out) if top < y_line - 40 else 0.0
    def state(self, t):
        if t < self.t0 or t >= self.t1: return None
        y = round(H * (1 - out_cubic((t - self.t0) / self.t_in)))
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0)); fr.paste(self.bg, (0, y))
        a = clamp((self.t1 - t) / self.t_out)
        if a < 1: fr.putalpha(fr.getchannel("A").point(lambda v: int(v * a)))
        self.img = fr
        return 1.0, 1.0, 0.0, 0.0, 0.0


# ===================== СУБТИТРЫ =====================
VOW = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")

def word_times(chunks):
    """Слова внутри фрагмента распределяются по слогам (фрагменты — по провалам громкости)."""
    out = []
    for t0, t1, txt in chunks:
        ws = txt.split()
        syl = [(2 * len(w) if w.isdigit() else max(1, sum(c in VOW for c in w))) + 0.3 for w in ws]
        tot, t = sum(syl), t0 + 0.04
        for w, s in zip(ws, syl):
            d = (t1 - t0 - 0.08) * s / tot
            out.append([w, t, t + d]); t += d
    return out

def subtitle_groups(spec):
    words = word_times(spec["transcript"]["chunks"])
    groups, i = [], 0
    for g in spec["subtitles"]["groups"]:
        n = len(g.split()); seg = words[i:i + n]; i += n
        got = " ".join(w for w, _, _ in seg)
        if got.lower().replace("ё", "е") != g.lower().replace("ё", "е"):
            raise ValueError(f"группа «{g}» не совпадает с расшифровкой: «{got}»")
        groups.append([g, seg[0][1], seg[-1][2]])
    if i != len(words):
        raise ValueError(f"субтитры покрывают {i} слов из {len(words)}")
    for k in range(len(groups) - 1): groups[k][2] = groups[k + 1][1]
    groups[0][1] = 0.0; groups[-1][2] = spec["duration"]
    return groups

class Subtitle(El):
    def __init__(self, text, t0, t1, base, slides):
        f = font("BODY", 54)
        self.light, (_, oy) = text_img(text, f, PAL["cream"], glow=0.75, blur=10, pad=40)
        self.dark, _ = text_img(text, f, PAL["ink"], glow=0, pad=40)
        if self.light.width - 80 > W - 2 * SIDE:
            raise ValueError(f"субтитр «{text}» шире кадра — разбить группу")
        super().__init__(self.light, W / 2, base - oy + self.light.height / 2, t0, t1, "SUB", z=Z_SUBS, out=0.0)
        self.base, self.slides, self.text = base, slides, text
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        on = any(s.cover(t, self.base) > 0.5 for s in self.slides)
        self.img = self.dark if on else self.light
        return st


# ===================== ЗУМ =====================
def zoom_at(keys, t):
    for (ta, sa, _), (tb, sb, mode) in zip(keys, keys[1:]):
        if ta <= t <= tb:
            p = (t - ta) / (tb - ta) if tb > ta else 1
            return sa + (sb - sa) * (in_out(p) if mode == "ease" else p)
    return keys[-1][1]

def zoom_frame(src, keys, anchor, t):
    s = zoom_at(keys, t) if keys else 1.0
    if s <= 1.0005: return src
    ax, ay = anchor
    return src.resize((W, H), Image.LANCZOS, box=(ax - ax / s, ay - ay / s, ax + (W - ax) / s, ay + (H - ay) / s))


def bottom_scrim():
    """Вертикальный градиент под текстом (§3.3): 0 до y=650, ~0.12 у 1050, ~0.32 у 1450, ~0.50 внизу."""
    ys = np.arange(H, dtype=np.float32)
    a = np.interp(ys, [0, 650, 1050, 1450, 1920], [0, 0, 0.12, 0.32, 0.50])
    out = Image.new("RGBA", (W, H), PAL["scrim"] + (255,))
    out.putalpha(Image.fromarray((np.repeat(a[:, None], W, 1) * 255).astype(np.uint8), "L"))
    return out


# ===================== СБОРКА =====================
BUILDERS = {
    "composition": lambda ev, z: composition(ev, z),
    "sheet": lambda ev, z: [Sheet(ev, z)],
    "eyes": lambda ev, z: [Eyes(ev, z)],
    "app_icon": app_icon,
    "writelines": lambda ev, z: [WriteLines(ev, z)],
    "doc_card": lambda ev, z: [El(doc_card(ev), ev.get("cx", W / 2), ev["cy"], ev["t0"], ev["t1"], "M07", z=z, out=0.0)],
    "lockpath": lambda ev, z: [LockPath(ev, z)],
    "arrow": lambda ev, z: [Arrow(ev, z)],
    "link": link_icon,
    "nowifi": nowifi,
    "plaque": plaque,
    "text": text_line,
}

def build(spec):
    els, slides = [], []
    for ev in spec["events"]:
        if ev["type"] == "slide":
            s = Slide(ev); slides.append(s); els.append(s); continue
        z = Z_ON_SLIDE if ev.get("on_slide") else Z_VIDEO + ev.get("z", 0)
        if ev["type"] not in BUILDERS:
            raise ValueError(f"неизвестный тип события: {ev['type']}")
        els += BUILDERS[ev["type"]](ev, z)
    base = spec["subtitles"].get("baseline", 1556)
    over = spec["subtitles"].get("overrides", [])      # [[t0, t1, baseline]] — поднять субтитры над демонстрируемым предметом
    hide = [(s.t0, s.t1) for s in slides if s.subs == "hide"]
    subs = []
    for g, a, b in subtitle_groups(spec):
        if any(h0 <= (a + b) / 2 < h1 for h0, h1 in hide): continue
        bl = next((o[2] for o in over if o[0] <= (a + b) / 2 < o[1]), base)
        subs.append(Subtitle(g, a, b, bl, slides))
    els += subs
    els.sort(key=lambda e: e.z)
    return els, subs

def compose(els, t, base_img, scrim):
    """base_img=None -> прозрачный оверлей (для слоя overlay.mov)."""
    fr = base_img.convert("RGBA") if base_img is not None else Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fr.alpha_composite(scrim)
    for e in els:
        st = e.state(t)
        if st is None: continue
        if isinstance(e, Slide): fr.alpha_composite(e.img)
        else: place(fr, e.img, e.cx, e.cy, st)
    return fr


def srt_time(t):
    ms = round(t * 1000); return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--stills", nargs="*", type=float)
    ap.add_argument("--out")
    ap.add_argument("--layers", action="store_true",
                    help="ещё base_zoom.mp4 и overlay.mov (ProRes 4444 с альфой, ~20 МБ на секунду)")
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    here = os.path.dirname(os.path.abspath(a.spec))
    src = os.path.join(here, spec["source"]) if not os.path.isabs(spec["source"]) else spec["source"]
    fps, dur = spec["fps"], spec["duration"]
    nfr = round(dur * fps)
    els, subs = build(spec)
    scrim = bottom_scrim()
    zk = [tuple(k) for k in spec.get("zoom", {}).get("keys", [])]
    anchor = spec.get("zoom", {}).get("anchor", [540, 700])

    if a.stills is not None:
        out = a.out or os.path.join(here, "stills"); os.makedirs(out, exist_ok=True)
        for t in a.stills:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", src, "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
            img = Image.frombytes("RGB", (W, H), raw)
            compose(els, t, zoom_frame(img, zk, anchor, t), scrim).convert("RGB").save(f"{out}/{t:05.2f}.png")
        print("stills ->", out); return

    out = a.out or os.path.join(here, "out"); os.makedirs(out, exist_ok=True)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc_args = ["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    def enc(path, pix, extra, with_audio):
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", pix, "-s", f"{W}x{H}", "-r", str(Fraction(fps).limit_denominator(1001)), "-i", "-"]
        if with_audio: cmd += ["-i", src, "-map", "0:v", "-map", "1:a", "-c:a", "copy"]
        tail = ["-movflags", "+faststart", path] if path.endswith(".mp4") else [path]
        return subprocess.Popen(cmd + extra + tail, stdin=subprocess.PIPE)
    final = enc(f"{out}/final.mp4", "rgb24", enc_args, True)
    layers = a.layers
    if layers:
        basez = enc(f"{out}/base_zoom.mp4", "rgb24", enc_args, True)
        over = enc(f"{out}/overlay.mov", "rgba", ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"], False)
    fsz = W * H * 3
    for i in range(nfr):
        raw = dec.stdout.read(fsz)
        if len(raw) < fsz: break
        t = i / fps
        zb = zoom_frame(Image.frombytes("RGB", (W, H), raw), zk, anchor, t)
        final.stdin.write(compose(els, t, zb, scrim).convert("RGB").tobytes())
        if layers:
            basez.stdin.write(zb.tobytes())
            over.stdin.write(compose(els, t, None, scrim).tobytes())
    procs = [final] + ([basez, over] if layers else [])
    for p in procs: p.stdin.close()
    for p in procs: p.wait()
    dec.wait()
    with open(f"{out}/subs.srt", "w") as f:
        for k, s in enumerate(subs, 1):
            f.write(f"{k}\n{srt_time(s.t0)} --> {srt_time(min(s.t1, dur))}\n{s.text}\n\n")
    print("готово ->", out)

if __name__ == "__main__":
    main()
