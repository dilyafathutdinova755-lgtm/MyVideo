#!/usr/bin/env python3
"""Ролик 1910 по «Плейбуку динамичного монтажа в пастельной палитре».

Исходник 1080x1920, 25fps, 14.98с. Временная последовательность не меняется, склеек нет.
Поверх: плавные зумы (по просьбе автора), субтитры (режим A) + выборочные крупные акценты,
предметные вставки, одна пастельная интерлюдия. Звук исходника не трогается.

Поток: кадры rgb24 в stdin -> готовые кадры rgb24 в stdout.
Стоп-кадры: python3 pb.py --png <папка_с_кадрами> 1.0 2.5 ...  -> qa3/
"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 25
DUR = 14.98
NFR = round(DUR * FPS)

# ---------- токены (плейбук §3.1) ----------
MILK = (0xFF, 0xF8, 0xF1)
INK = (0x30, 0x2D, 0x3A)
MUTED = (0x5E, 0x58, 0x6B)
CREAM = (0xFF, 0xF8, 0xF1)
VANILLA = (0xF4, 0xE7, 0xA8)
BLUSH = (0xEF, 0xC6, 0xD8)
PLUM = (0x62, 0x4B, 0x69)
SCRIM = (0x24, 0x21, 0x2B)
# Пара на весь ролик: розовый + ваниль (дружелюбная подача, §3.2). Остальные пастели не используются.

# ---------- шрифтовые роли (§4.1) ----------
FONTS = {
    "BODY": ("fonts/Manrope%5Bwght%5D.ttf", 700),
    "WIDE": ("fonts/Unbounded%5Bwght%5D.ttf", 800),
    "COND": ("fonts/Oswald%5Bwght%5D.ttf", 600),
    "EDIT": ("fonts/CormorantGaramond-Italic%5Bwght%5D.ttf", 600),
}
_fc = {}
def font(role, size):
    k = (role, size)
    if k not in _fc:
        path, wght = FONTS[role]
        f = ImageFont.truetype(os.path.join(HERE, path), size)
        f.set_variation_by_axes([wght])
        _fc[k] = f
    return _fc[k]

# ---------- зоны (§6.1) ----------
SIDE = 80                    # боковые поля важных элементов
SUB_BASE = 1556              # базовая линия субтитров; ниже 1590 — резерв под интерфейс
ACC_CY = 1185                # центр крупных акцентов: грудь, ниже лица (лицо ~430-1000)

# ---------- easing ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def out_cubic(p): return 1 - (1 - clamp(p)) ** 3
def out_back(p, c1=1.0):
    p = clamp(p); c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
def in_out(p): return 0.5 - 0.5 * math.cos(math.pi * clamp(p))
def frames(sec): return round(sec * FPS) / FPS   # длительности округляются до целых кадров


# ---------- растеризация ----------
def text_img(txt, fnt, fill, glow=0.55, blur=14, pad=48, track=0):
    """Текст без обводки: читаемость держит мягкая тёмная подложка-тень (§3.3), не контур."""
    if track:
        widths = [fnt.getlength(c) for c in txt]
        tw = sum(widths) + track * (len(txt) - 1)
    l, t, r, b = fnt.getbbox(txt, anchor="ls")
    if track: r = l + tw
    w, h = int(r - l + 2 * pad), int(b - t + 2 * pad)
    ox, oy = pad - l, pad - t
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    m = Image.new("L", (w, h), 0); dm = ImageDraw.Draw(m)
    def draw(d, col):
        if not track:
            d.text((ox, oy), txt, font=fnt, fill=col, anchor="ls"); return
        x = ox
        for c, cw in zip(txt, widths):
            d.text((x, oy), c, font=fnt, fill=col, anchor="ls"); x += cw + track
    draw(dm, 255)
    if glow:
        sh = m.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, int(v * glow * 1.6)))
        img.paste(Image.new("RGBA", (w, h), SCRIM + (255,)), (0, 4), sh)
    draw(ImageDraw.Draw(img), fill + (255,))
    return img, (ox, oy)

def soft_shadow(img, blur=22, alpha=0.18, dy=12, col=PLUM):
    """Тёмно-сливовая тень 0.12-0.20, смещение 8-14px, размытие 24-40px (§3.4)."""
    w, h = img.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = img.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    out.paste(Image.new("RGBA", (w, h), col + (255,)), (0, dy), sh)
    out.alpha_composite(img)
    return out


# ---------- слой ----------
class El:
    """Картинка + якорь + [t0, t1) + вход/выход. Фазы: вход, неподвижное удержание, выход."""
    def __init__(self, img, cx, cy, t0, t1, motion="M01", z=5, out=0.10, rot=0.0):
        self.img, self.cx, self.cy = img, cx, cy
        self.t0, self.t1 = frames(t0), frames(t1)
        self.motion, self.z, self.out, self.rot = motion, z, out, rot

    def state(self, t):
        if t < self.t0 or t >= self.t1: return None
        lt, rem = t - self.t0, self.t1 - t
        s, a, dx, dy, rot = 1.0, 1.0, 0.0, 0.0, self.rot
        m = self.motion
        if m == "M01":            # мягкий подъём: +32px, 0.98, 200ms easeOutCubic
            p = out_cubic(lt / 0.20); dy, s, a = 32 * (1 - p), 0.98 + 0.02 * p, clamp(lt / 0.12)
        elif m == "M02":          # упругий акцент: 0.90 -> 1.035 -> 1.0, 260ms
            p = clamp(lt / 0.26); s = 0.90 + 0.10 * out_back(p, 1.25); a = clamp(lt / 0.09)
        elif m == "M04":          # строка с наклоном: x+44, -6°, 230ms
            p = out_cubic(lt / 0.23); dx, rot, a = 44 * (1 - p), self.rot - 6 * (1 - p), clamp(lt / 0.12)
        elif m == "M07":          # предметная вставка: 0.9, y+40, -3°, 300ms
            p = clamp(lt / 0.30); s = 0.90 + 0.10 * out_back(p, 0.9); dy = 40 * (1 - out_cubic(p))
            rot = self.rot - 3 * (1 - out_cubic(p)); a = clamp(lt / 0.12)
        elif m == "SUB":          # субтитр: короткий подъём 14px, 120ms — не pop на каждом слове
            p = out_cubic(lt / 0.12); dy, a = 14 * (1 - p), clamp(lt / 0.08)
        if self.out:
            q = clamp(rem / self.out); a *= q
            if m == "M07": s *= 0.94 + 0.06 * q
        return s, a, dx, dy, rot

def place(frame, el, st):
    s, a, dx, dy, rot = st
    img = el.img
    if rot: img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(s - 1) > 1e-3:
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.BICUBIC)
    if a < 0.999:
        img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    x, y = round(el.cx + dx - img.width / 2), round(el.cy + dy - img.height / 2)
    tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0)); tmp.paste(img, (x, y), img)
    frame.alpha_composite(tmp)


# ---------- крупная композиция (§5.3): геометрия считается заранее ----------
def composition(parts, t_end, cy=ACC_CY, lead=1.0, out=0.12):
    """parts: [(text, role, size, color, t_reveal, motion, opts)].
    opts: dx — смещение строки (ступень P2), flip — перевернуть, track — трекинг."""
    rows = []
    for txt, role, size, col, tr, mo, o in parts:
        img, (ox, oy) = text_img(txt, font(role, size), col, track=o.get("track", 0))
        fnt = font(role, size)
        cap = -fnt.getbbox("Н", anchor="ls")[1]       # реальная высота прописной
        rows.append(dict(img=img, ox=ox, oy=oy, size=size, cap=cap, tr=tr, mo=mo, o=o))
    # базовая линия следующей строки: baseline + lead * её кегль (ориентир 0.90-1.08)
    base = [0.0]
    for r in rows[1:]: base.append(base[-1] + r["o"].get("lead", lead) * r["size"])
    top = -rows[0]["cap"]; bot = base[-1]
    shift = cy - (top + bot) / 2
    els = []
    for r, b in zip(rows, base):
        img, by = r["img"], b + shift
        if r["o"].get("flip"):
            # после поворота на 180° базовая линия становится верхней кромкой глифов;
            # перевёрнутая строка занимает ту же полосу [by - cap, by], что и обычная
            img = img.rotate(180)
            cy_img = by - r["cap"] - (img.height - r["oy"]) + img.height / 2
        else:
            cy_img = by - r["oy"] + img.height / 2
        cx = W / 2 + r["o"].get("dx", 0)
        assert cx - img.width / 2 + 48 >= SIDE - 1 and cx + img.width / 2 - 48 <= W - SIDE + 1, \
            f"строка шире поля: {img.width - 96}px"
        els.append(El(img, cx, cy_img, r["tr"], t_end, r["mo"], z=6, out=out))
    return els


# ---------- предметы ----------
def answer_sheet():
    """Лист ответов из сборника: молочная карточка, розовая шапка. Строки — абстрактные полосы."""
    pw, ph, pad = 260, 320, 50
    img = Image.new("RGBA", (pw + 2 * pad, ph + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    x0, y0 = pad, pad
    d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), 26, fill=MILK + (255,))
    d.rounded_rectangle((x0, y0, x0 + pw, y0 + 66), 26, fill=BLUSH + (255,))
    d.rectangle((x0, y0 + 40, x0 + pw, y0 + 66), fill=BLUSH + (255,))
    d.text((x0 + pw / 2, y0 + 47), "ОТВЕТЫ", font=font("WIDE", 26), fill=INK + (255,), anchor="ms")
    for i, wl in enumerate((150, 112, 168, 96, 138)):
        y = y0 + 96 + i * 42
        d.ellipse((x0 + 28, y, x0 + 46, y + 18), fill=VANILLA + (255,), outline=INK + (255,), width=3)
        d.rounded_rectangle((x0 + 62, y + 3, x0 + 62 + wl, y + 15), 6, fill=(0xE6, 0xDF, 0xE3, 255))
    return soft_shadow(img)

class Sheet(El):
    """M07-вставка + переворот вверх ногами (ease in-out, 480ms)."""
    def __init__(self, cx, cy, t0, t1, flip_t):
        super().__init__(answer_sheet(), cx, cy, t0, t1, "M07", z=5, out=0.16, rot=4.0)
        self.flip_t = flip_t
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        s, a, dx, dy, rot = st
        return s, a, dx, dy, rot + 180 * in_out((t - self.flip_t) / 0.48)

class Eyes(El):
    """Реакция: глаза выглядывают из-за листа (слой под листом), косятся и моргают."""
    def __init__(self, cx, cy, t0, t1):
        super().__init__(None, cx, cy, t0, t1, "none", z=4, out=0.14)
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        lt = t - self.t0
        rise = out_back(lt / 0.32, 1.2)
        keys = [(0.0, (0, 11)), (0.55, (0, 11)), (0.75, (-13, 2)), (1.05, (-13, 2)), (1.25, (0, 11))]
        dx, dy = keys[-1][1]
        for (ta, va), (tb, vb) in zip(keys, keys[1:]):
            if ta <= lt < tb:
                p = in_out((lt - ta) / (tb - ta)); dx, dy = va[0] + (vb[0] - va[0]) * p, va[1] + (vb[1] - va[1]) * p
        blink = 1.0 - 0.85 * max(0.0, 1 - abs(lt - 0.95) / 0.06)
        w, h = 230, 150
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        for ex in (66, 164):
            ey, rx, ry = 76, 44, 52 * blink
            d.ellipse((ex - rx, ey - ry, ex + rx, ey + ry), fill=MILK + (255,), outline=INK + (255,), width=7)
            if blink > 0.4:
                d.ellipse((ex + dx - 17, ey + dy - 17, ex + dx + 17, ey + dy + 17), fill=INK + (255,))
                d.ellipse((ex + dx - 9, ey + dy - 11, ex + dx - 2, ey + dy - 4), fill=MILK + (255,))
        self.img = soft_shadow(img, blur=10, alpha=0.25, dy=5)
        return 1.0, st[1], 0.0, 130 * (1 - rise), 0.0

def product_card():
    """Карточка продукта: только название из речи. Без выдуманного интерфейса и цифр."""
    cw, ch, pad = 420, 168, 50
    img = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, pad + cw, pad + ch), 32, fill=MILK + (255,))
    d.rounded_rectangle((pad + 26, pad + 34, pad + 126, pad + 134), 26, fill=BLUSH + (255,))
    # пиктограмма «раскрытая тетрадь»: две страницы и корешок
    bx, by = pad + 76, pad + 84
    d.rounded_rectangle((bx - 36, by - 24, bx - 3, by + 24), 6, fill=MILK + (255,), outline=INK + (255,), width=4)
    d.rounded_rectangle((bx + 3, by - 24, bx + 36, by + 24), 6, fill=MILK + (255,), outline=INK + (255,), width=4)
    for k in (-10, 2, 14):
        d.line((bx - 28, by + k, bx - 12, by + k), fill=INK + (255,), width=3)
        d.line((bx + 12, by + k, bx + 28, by + k), fill=INK + (255,), width=3)
    d.text((pad + 152, pad + 80), "ЕГЭ", font=font("WIDE", 40), fill=INK + (255,), anchor="ls")
    d.text((pad + 152, pad + 126), "Тренажёр", font=font("BODY", 38), fill=MUTED + (255,), anchor="ls")
    return soft_shadow(img)

class WriteLines(El):
    """Строки разбора дописываются одна за другой (маска слева направо, M05)."""
    def __init__(self, cx, cy, t0, t1, widths=(500, 400, 450), per=0.22):
        super().__init__(None, cx, cy, t0, t1, "none", z=6, out=0.12)
        self.widths, self.per = widths, per
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        pad, lh, gap = 30, 14, 22
        w = max(self.widths) + 2 * pad + 30; h = len(self.widths) * (lh + gap) + 2 * pad
        shape = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shape)
        for i, wl in enumerate(self.widths):
            p = out_cubic((t - self.t0 - i * self.per) / self.per)
            if p <= 0: continue
            y = pad + i * (lh + gap)
            d.ellipse((pad - 4, y - 1, pad + 12, y + 15), fill=VANILLA + (255,))
            d.rounded_rectangle((pad + 26, y, pad + 26 + max(lh, wl * p), y + lh), 7, fill=CREAM + (235,))
        self.img = glowed(shape)
        return st

def glowed(shape, alpha=0.5, blur=8):
    w, h = shape.size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = shape.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    img.paste(Image.new("RGBA", (w, h), SCRIM + (255,)), (0, 3), sh)
    img.alpha_composite(shape)
    return img

def padlock(op):
    w, h = 96, 118
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    lift = 16 * op
    d.arc((26, 12 - lift, 70, 62 - lift), 180, 360, fill=CREAM + (255,), width=9)
    d.line((30, 37 - lift, 30, 56 - lift * 1.9), fill=CREAM + (255,), width=9)
    d.line((66, 37 - lift, 66, 56 - lift), fill=CREAM + (255,), width=9)
    d.rounded_rectangle((14, 54, 82, 108), 14, fill=BLUSH + (255,))
    d.ellipse((42, 68, 54, 80), fill=INK + (255,)); d.rectangle((46, 76, 50, 92), fill=INK + (255,))
    return img

class LockPath(El):
    """M09: путь из сегментов заполняется; в конце пути открывается замок (ответ доступен)."""
    def __init__(self, n, cx, cy, t0, t1, fill_t0, fill_dur):
        super().__init__(None, cx, cy, t0, t1, "M01", z=6, out=0.12)
        self.n, self.f0, self.fd = n, fill_t0, fill_dur
        self.unlock = fill_t0 + fill_dur
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        sw, sh_, gap, pad, lw = 104, 22, 16, 30, 100
        w = self.n * (sw + gap) + lw + 2 * pad; h = 120 + 2 * pad
        shape = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shape)
        yb = pad + 64
        for i in range(self.n):
            x = pad + i * (sw + gap)
            d.rounded_rectangle((x, yb, x + sw, yb + sh_), 11, outline=CREAM + (230,), width=3)
            p = clamp((t - self.f0 - i * self.fd / self.n) / (self.fd / self.n))
            if p > 0:
                d.rounded_rectangle((x, yb, x + max(22, sw * out_cubic(p)), yb + sh_), 11, fill=VANILLA + (255,))
        op = clamp(out_back((t - self.unlock) / 0.3, 1.2), 0, 1.2) if t >= self.unlock else 0
        lk = padlock(op)
        k = 1 + 0.12 * math.sin(math.pi * clamp((t - self.unlock) / 0.3))
        lk = lk.resize((round(lk.width * k), round(lk.height * k)), Image.BICUBIC)
        lx = pad + self.n * (sw + gap) + lw / 2
        shape.alpha_composite(lk, (round(lx - lk.width / 2), round(yb + sh_ / 2 - lk.height * 0.62)))
        self.img = glowed(shape, 0.45, 7)
        return st

def arrow_img(L, prog, horizontal, col, width=7, shadow=True):
    pad = 34
    size = (L + 2 * pad, 90) if horizontal else (90, L + 2 * pad)
    def draw(d, c, w):
        if horizontal:
            y = size[1] // 2; xe = pad + L * prog
            d.line((pad, y, xe, y), fill=c, width=w)
            if prog > 0.75:
                k = (prog - 0.75) / 0.25 * 24
                d.line((xe - k, y - k, xe, y), fill=c, width=w); d.line((xe - k, y + k, xe, y), fill=c, width=w)
        else:
            x = size[0] // 2; ye = pad + L - L * prog
            d.line((x, pad + L, x, ye), fill=c, width=w)
            if prog > 0.75:
                k = (prog - 0.75) / 0.25 * 24
                d.line((x - k, ye + k, x, ye), fill=c, width=w); d.line((x + k, ye + k, x, ye), fill=c, width=w)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    if shadow:
        m = Image.new("L", size, 0); draw(ImageDraw.Draw(m), 255, width + 6)
        m = m.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.55))
        img.paste(Image.new("RGBA", size, SCRIM + (255,)), (0, 3), m)
    draw(ImageDraw.Draw(img), col + (255,), width)
    return img

class Arrow(El):
    """M10: линия прорисовывается за 180-300ms, затем наконечник."""
    def __init__(self, L, horizontal, cx, cy, t0, t1, col, draw_t=0.26, shadow=True, z=7, bob_from=None, rot=0.0):
        super().__init__(None, cx, cy, t0, t1, "none", z=z, out=0.0 if z >= 9 else 0.12, rot=rot)
        self.L, self.h, self.col, self.dt, self.shadow, self.bob = L, horizontal, col, draw_t, shadow, bob_from
        self.cache = {}
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        p = round(out_cubic((t - self.t0) / self.dt), 3)
        if p not in self.cache: self.cache[p] = arrow_img(self.L, max(p, 0.02), self.h, self.col, shadow=self.shadow)
        self.img = self.cache[p]
        s, a, dx, dy, rot = st
        if self.bob is not None and t > self.bob:      # луп — линейный синус, 6px
            dy -= 6 * math.sin(2 * math.pi * (t - self.bob) / 1.1)
        return s, a, dx, dy, rot

def link_icon():
    w = h = 150
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for off in (-25, 25):
        box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle((w / 2 - 36 + off, h / 2 - 18, w / 2 + 36 + off, h / 2 + 18), 18,
                                               outline=VANILLA + (255,), width=10)
        img.alpha_composite(box)
    return glowed(img.rotate(-45, resample=Image.BICUBIC), 0.6, 6)


# ---------- интерлюдия M12 ----------
class Interlude(El):
    """Молочная плоскость входит снизу (340ms), на ней один размытый розовый центр и тёмный текст.
    Текст входит, когда его зона уже закрыта фоном. Видеоряд под ней не меняется."""
    def __init__(self, t0, t1):
        super().__init__(None, 0, 0, t0, t1, "none", z=8, out=0.0)
        bg = Image.new("RGBA", (W, H), MILK + (255,))
        # размытое пятно считается во float и дизерится — иначе после сжатия видны кольца
        import numpy as np
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        m = np.exp(-(((xx - 540) / 520) ** 2 + ((yy - 910) / 470) ** 2) * 1.6) * 0.85
        rgb = np.array(MILK, np.float32) * (1 - m[..., None]) + np.array(BLUSH, np.float32) * m[..., None]
        rgb += np.random.default_rng(3).uniform(-1.5, 1.5, rgb.shape).astype(np.float32)
        bg = Image.fromarray(np.clip(rgb + 0.5, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        self.bg = bg
        self.t_in, self.t_out = 0.34, 0.20
    def state(self, t):
        if t < self.t0 or t >= self.t1: return None
        lt, rem = t - self.t0, self.t1 - t
        y = round(H * (1 - out_cubic(lt / self.t_in)))
        a = clamp(rem / self.t_out)
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fr.paste(self.bg, (0, y))
        if a < 1: fr.putalpha(fr.getchannel("A").point(lambda v: int(v * a)))
        self.img = fr
        return 1.0, 1.0, W / 2, H / 2, 0.0   # cx/cy задаются как смещения от (0,0)

def plaque_text(txt, role, size, col, fill):
    """Тёмный текст на пастельной плашке (§3.2: на светлой плашке — тёмный текст)."""
    f = font(role, size)
    l, t, r, b = f.getbbox(txt, anchor="ls")
    px, py, pad = 34, 22, 40
    w, h = int(r - l + 2 * px + 2 * pad), int(b - t + 2 * py + 2 * pad)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, w - pad, h - pad), 30, fill=fill + (255,))
    d.text((pad + px - l, pad + py - t), txt, font=f, fill=col + (255,), anchor="ls")
    return soft_shadow(img, blur=20, alpha=0.16, dy=10)

def plain_text(txt, role, size, col):
    img, _ = text_img(txt, font(role, size), col, glow=0)
    return img


# ---------- субтитры (режим A) ----------
# Расшифровка — Whisper medium; тайминги фрагментов — по провалам громкости,
# слова внутри фрагмента распределены по слогам.
CHUNKS = [
    (0.00, 2.54, "в бумажных сборниках ЕГЭ ответы напечатаны вверх"),
    (2.54, 5.18, "ногами и я смеюсь но иногда подглядываю"),
    (5.18, 6.63, "здесь подглядывать некуда"),
    (6.63, 7.40, "путь и ответ"),
    (7.40, 8.15, "идут подряд"),
    (8.15, 9.82, "в ЕГЭ Тренажёре к заданиям есть"),
    (9.82, 10.89, "текстовый разбор где от"),
    (10.89, 12.12, "вет нельзя подглядеть без"),
    (12.12, 12.76, "пути к нему"),
    (12.76, 14.05, "ссылка на ЕГЭ Тренажёр"),
    (14.05, 14.98, "в шапке профиля"),
]
VOW = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")

def word_times():
    out = []
    for t0, t1, txt in CHUNKS:
        ws = txt.split()
        syl = [max(1, sum(c in VOW for c in w)) + 0.3 for w in ws]
        tot, t = sum(syl), t0 + 0.04
        for w, s in zip(ws, syl):
            d = (t1 - t0 - 0.08) * s / tot
            out.append([w, t, t + d]); t += d
    for i, (w, a, b) in enumerate(out):
        if w == "от" and out[i + 1][0] == "вет":
            out[i] = ["ответ", a, out[i + 1][2]]; del out[i + 1]; break
    return out

# Смысловые группы 2-4 слова (§5.2): не рвём предлог и слово, название, отрицание.
GROUPS = [
    "в бумажных сборниках ЕГЭ", "ответы напечатаны", "вверх ногами",
    "и я смеюсь", "но иногда подглядываю",
    "здесь подглядывать некуда",
    "путь и ответ", "идут подряд",
    "в ЕГЭ Тренажёре", "к заданиям есть", "текстовый разбор",
    "где ответ нельзя", "подглядеть без пути", "к нему",
    "ссылка на ЕГЭ Тренажёр", "в шапке профиля",
]

def subtitle_track(hide=()):
    words = word_times(); i = 0; out = []
    for g in GROUPS:
        n = len(g.split()); seg = words[i:i + n]; i += n
        assert " ".join(w for w, _, _ in seg) == g, (g, seg)
        out.append([g, seg[0][1], seg[-1][2]])
    # «к нему» (~0.3с) короче порога чтения — объединить с предыдущим (§5.2)
    for k, (g, a, b) in enumerate(out):
        if g == "к нему":
            out[k - 1][0] += " к нему"; out[k - 1][2] = b; del out[k]; break
    for k in range(len(out) - 1): out[k][2] = out[k + 1][1]
    out[0][1] = 0.0; out[-1][2] = DUR + 1
    f = font("BODY", 54)
    els = []
    for g, a, b in out:
        if any(h0 <= (a + b) / 2 < h1 for h0, h1 in hide): continue
        img, (ox, oy) = text_img(g, f, CREAM, glow=0.75, blur=10, pad=40)
        assert img.width - 80 <= W - 2 * SIDE, g
        cy = SUB_BASE - oy + img.height / 2
        els.append(El(img, W / 2, cy, a, b, "SUB", z=9, out=0.0))
    return els

def bottom_scrim():
    """Вертикальный градиент (§3.3): 0 до y=650, ~0.12 у 1050, ~0.32 у 1450, ~0.50 внизу."""
    keys = [(0, 0.0), (650, 0.0), (1050, 0.12), (1450, 0.32), (1920, 0.50)]
    col = Image.new("L", (1, H), 0)
    for y in range(H):
        for (ya, va), (yb, vb) in zip(keys, keys[1:]):
            if ya <= y <= yb:
                col.putpixel((0, y), int(255 * (va + (vb - va) * (y - ya) / max(1, yb - ya)))); break
    out = Image.new("RGBA", (W, H), SCRIM + (255,)); out.putalpha(col.resize((W, H)))
    return out


# ---------- зум видеоряда (по просьбе автора) ----------
ZOOM_ANCHOR = (380, 700)
ZOOM_KEYS = [
    (0.00, 1.00, None), (1.55, 1.04, "lin"), (2.05, 1.12, "ease"), (3.55, 1.15, "lin"),
    (4.05, 1.03, "ease"), (5.15, 1.05, "lin"), (6.55, 1.16, "ease"), (8.35, 1.00, "ease"),
    (8.85, 1.09, "ease"), (9.80, 1.11, "lin"), (10.25, 1.03, "ease"), (11.05, 1.05, "lin"),
    (12.70, 1.15, "ease"), (13.20, 1.04, "ease"), (DUR, 1.08, "lin"),
]
def zoom_at(t):
    for (ta, sa, _), (tb, sb, mode) in zip(ZOOM_KEYS, ZOOM_KEYS[1:]):
        if ta <= t <= tb:
            p = (t - ta) / (tb - ta)
            return sa + (sb - sa) * (in_out(p) if mode == "ease" else p)
    return ZOOM_KEYS[-1][1]
def zoom_frame(src, t):
    s = zoom_at(t)
    if s <= 1.0005: return src
    ax, ay = ZOOM_ANCHOR
    return src.resize((W, H), Image.LANCZOS, box=(ax - ax / s, ay - ay / s, ax + (W - ax) / s, ay + (H - ay) / s))


# ---------- партитура ----------
INTER = (6.56, 8.36)

def build():
    E = []
    # beat 1 · 0.00-1.56 · вводный тезис: узкая сливочная строка + широкий ванильный акцент (P2 ступень)
    E += composition([("БУМАЖНЫЕ", "COND", 92, CREAM, 0.04, "M01", {"dx": -70, "track": 4}),
                      ("СБОРНИКИ", "WIDE", 86, VANILLA, 0.40, "M04", {"dx": 30, "lead": 1.04})], t_end=1.56)
    # beat 2 · 1.60-3.44 · главный акцент: «ОТВЕТЫ» + курсив, буквально перевёрнутый
    E += composition([("ОТВЕТЫ", "WIDE", 118, BLUSH, 1.60, "M02", {}),
                      ("вверх ногами", "EDIT", 92, CREAM, 2.62, "M01", {"flip": True, "lead": 1.06})], t_end=3.44)
    # предмет · 1.88-5.20 · лист ответов справа от лица; на «ногами» переворачивается
    sx, sy = 852, 720
    E.append(Sheet(sx, sy, 1.88, 5.20, flip_t=2.74))
    # реакция · 3.72-5.20 · глаза выглядывают из-за листа; крупного текста нет — работают субтитры
    E.append(Eyes(sx - 6, sy - 214, 3.72, 5.20))
    # 5.20-6.56 · тихий сброс (M15): лицо, субтитры, медленный наезд
    # интерлюдия · 6.56-8.16 · «путь → ответ / идут подряд»
    E.append(Interlude(*INTER))
    # вертикальная схема: ПУТЬ ↓ ОТВЕТ — последовательность читается сверху вниз
    t0 = INTER[0] + 0.30                    # текст — после того, как фон закрыл зону
    te = INTER[1] - 0.20
    E.append(El(plain_text("ПУТЬ", "WIDE", 132, INK), 540, 700, t0, te, "M01", z=9, out=0.0))
    E.append(Arrow(96, False, 540, 862, t0 + 0.12, te, PLUM, shadow=False, z=9, rot=180))
    E.append(El(plaque_text("ОТВЕТ", "WIDE", 104, INK, VANILLA), 540, 1022, t0 + 0.30, te, "M02", z=9, out=0.0))
    E.append(El(plain_text("идут подряд", "EDIT", 100, PLUM), 540, 1200, t0 + 0.52, te, "M01", z=9, out=0.0))
    # продукт · 8.40-11.06 · карточка с названием (вход разнесён с выходом интерлюдии)
    E.append(El(product_card(), 760, 690, 8.56, 11.06, "M07", z=5, out=0.16, rot=-3))
    # beat 6 · 9.86-11.06 · «текстовый разбор» + строки, которые дописываются
    E += composition([("ТЕКСТОВЫЙ", "COND", 84, CREAM, 9.86, "M01", {"track": 3}),
                      ("РАЗБОР", "WIDE", 112, VANILLA, 10.12, "M02", {"lead": 1.02})], t_end=11.06, cy=1150)
    E.append(WriteLines(540, 1338, 10.36, 11.06))
    # beat 7 · 11.10-12.76 · «нельзя подглядеть / БЕЗ ПУТИ» + путь с замком
    E += composition([("нельзя подглядеть", "EDIT", 84, CREAM, 11.10, "M01", {}),
                      ("БЕЗ ПУТИ", "WIDE", 112, BLUSH, 11.66, "M02", {"lead": 1.04})], t_end=12.76, cy=1150)
    E.append(LockPath(4, 540, 1350, 11.40, 12.76, fill_t0=11.50, fill_dur=0.90))
    # финал · 12.80-14.98 · «ССЫЛКА / в шапке профиля» + стрелка вверх + звенья ссылки
    E += composition([("ССЫЛКА", "WIDE", 116, VANILLA, 12.80, "M02", {}),
                      ("в шапке профиля", "EDIT", 88, CREAM, 14.08, "M01", {"lead": 1.0})], t_end=DUR + 1, cy=1170)
    E.append(Arrow(170, False, 960, 1180, 13.40, DUR + 1, VANILLA, draw_t=0.3, bob_from=13.9))
    E.append(El(link_icon(), 960, 1030, 13.72, DUR + 1, "M07", z=7, out=0.0))
    E += subtitle_track(hide=(INTER,))
    E.sort(key=lambda e: e.z)
    return E

def render(E, scrim, t, base):
    fr = zoom_frame(base, t).convert("RGBA")
    fr.alpha_composite(scrim)
    for e in E:
        st = e.state(t)
        if st is None: continue
        if isinstance(e, Interlude):
            fr.alpha_composite(e.img)
        else:
            place(fr, e, st)
    return fr

if __name__ == "__main__":
    E, scrim = build(), bottom_scrim()
    if sys.argv[1:2] == ["--png"]:
        os.makedirs("qa3", exist_ok=True)
        for ts in sys.argv[3:]:
            base = Image.open(f"{sys.argv[2]}/{ts}.png").convert("RGB")
            render(E, scrim, float(ts), base).convert("RGB").save(f"qa3/{ts}.png")
    else:
        inp, out = sys.stdin.buffer, sys.stdout.buffer
        fsz = W * H * 3
        for i in range(NFR):
            raw = inp.read(fsz)
            if len(raw) < fsz: break
            out.write(render(E, scrim, i / FPS, Image.frombytes("RGB", (W, H), raw)).convert("RGB").tobytes())
