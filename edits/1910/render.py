#!/usr/bin/env python3
"""Графический слой для ролика «ответы вверх ногами» (исходник 1080x1920, 25fps, 14.98с).

Видеоряд не режется: поверх него плавные зумы (ZOOM_KEYS) и графика.
Поток: исходные кадры rgb24 в stdin -> готовые кадры rgb24 в stdout.
Кадры: python3 render.py --png <папка> 4.0 6.9 ... пишет стоп-кадры в qa/.
"""
import math, sys, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 25
DUR = 14.98
NFR = round(DUR * FPS)

# --- токены бренда (CLAUDE.md §1.2-1.4) ---
WHITE = (255, 255, 255)
ACCENT = (0xC9, 0xF5, 0xFF)      # ледяной голубой
INK = (0x22, 0x20, 0x2A)         # тёмный текст на светлой плашке
SHADOW = (0, 0, 0)
F_GOLOS = os.path.join(HERE, "fonts/GolosText%5Bwght%5D.ttf")
F_MANROPE = os.path.join(HERE, "fonts/Manrope%5Bwght%5D.ttf")
F_PLAYFAIR = os.path.join(HERE, "fonts/PlayfairDisplay-Italic%5Bwght%5D.ttf")
ICON = os.path.join(HERE, "IMG_0884.png")

CARD_BAND = (1056, 1440)         # 55-75% высоты
CARD_CY = 1250
TOP_SLOT_Y = 268                 # бегущая подпись: центр строки, ниже 180px, над волосами (~430)
MARGIN = 70

_fonts = {}
def font(path, size, wght):
    k = (path, size, wght)
    if k not in _fonts:
        f = ImageFont.truetype(path, size)
        f.set_variation_by_axes([wght])
        _fonts[k] = f
    return _fonts[k]

def golos(size, w=900): return font(F_GOLOS, size, w)

# --- easing ---
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out_cubic(p): return 1 - (1 - p) ** 3
def ease_out_back(p, c1=0.6):     # слабый отскок
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2

# --- растеризация текста ---
def text_img(txt, fnt, fill, stroke=3, shadow=0.55, blur=8, pad=40, stroke_fill=SHADOW):
    l, t, r, b = fnt.getbbox(txt, anchor="ls", stroke_width=stroke)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    ox, oy = pad - l, pad - t                         # положение базовой линии в картинке
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("L", (w, h), 0)
        ImageDraw.Draw(sh).text((ox, oy + 4), txt, font=fnt, fill=255, anchor="ls", stroke_width=stroke + 2)
        sh = sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * shadow))
        img.paste(Image.new("RGBA", (w, h), SHADOW + (255,)), (0, 0), sh)
    d = ImageDraw.Draw(img)
    d.text((ox, oy), txt, font=fnt, fill=fill + (255,), anchor="ls",
           stroke_width=stroke, stroke_fill=(stroke_fill + (255,)) if stroke else None)
    return img, (ox, oy)   # якорь: начало базовой линии


class El:
    """Слой: картинка + якорь + тайминг + тип анимации."""
    def __init__(self, img, cx, cy, t0, t1, anim="pop", rot=0.0, z=5, fade_in=0.14, fade_out=0.09):
        self.img, self.cx, self.cy, self.t0, self.t1 = img, cx, cy, t0, t1
        self.anim, self.rot, self.z = anim, rot, z
        self.fade_in, self.fade_out = fade_in, fade_out

    def state(self, t):
        if t < self.t0 or t >= self.t1:
            return None
        lt, rem = t - self.t0, self.t1 - t
        a = clamp(lt / self.fade_in) if self.fade_in else 1.0
        a = min(a, clamp(rem / self.fade_out) if self.fade_out else 1.0)
        s, dy, rot = 1.0, 0.0, self.rot
        if self.anim == "pop":                     # 0.94 -> 1.0, 320ms, ease-out + слабый отскок
            p = clamp(lt / 0.32)
            s = 0.94 + 0.06 * ease_out_back(p)
        elif self.anim == "bubble":                # M11: 0.92 -> 1.02 -> 1, -2° -> 0, 240ms
            p = clamp(lt / 0.24)
            s = 0.92 + 0.08 * ease_out_back(p, 1.6)
            rot = self.rot - 2 * (1 - ease_out_cubic(p))
        elif self.anim == "rise":                  # M01: +30px, 200ms
            p = ease_out_cubic(clamp(lt / 0.2))
            dy, s = 30 * (1 - p), 0.98 + 0.02 * p
        return s, a, dy, rot


def place(frame, el, st):
    s, a, dy, rot = st
    img = el.img
    if rot:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(s - 1) > 1e-3:
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.BICUBIC)
    if a < 1:
        al = img.getchannel("A").point(lambda v: int(v * a))
        img = img.copy(); img.putalpha(al)
    x = round(el.cx - img.width / 2); y = round(el.cy + dy - img.height / 2)
    frame.alpha_composite(img, (x, y)) if x >= 0 and y >= 0 and x + img.width <= W and y + img.height <= H \
        else _paste_clip(frame, img, x, y)

def _paste_clip(frame, img, x, y):
    tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0)); tmp.paste(img, (x, y), img)
    frame.alpha_composite(tmp)


# ===================== КАРТОЧКИ (слой 1) =====================
def card(lines, t_end, cy=CARD_CY, lead=0.90):
    """lines: [(text, size, color, t_reveal, opts)]. Геометрия считается заранее,
    строки раскрываются в зарезервированных местах (плейбук §5.3)."""
    rend = []
    for txt, size, color, tr, o in lines:
        f = font(F_PLAYFAIR, size, 600) if o.get("italic") else golos(size)
        img, (ox, oy) = text_img(txt, f, color, stroke=0 if o.get("italic") else 3)
        if o.get("flip"):
            img = img.rotate(180)
            ox, oy = img.width - ox, img.height - oy
        rend.append((img, ox, oy, size, tr, o))
    # базовые линии: baseline_{n+1} = baseline_n + 0.90 * size_{n+1}
    bases = [0.0]
    for i in range(1, len(rend)):
        bases.append(bases[-1] + lead * rend[i][3])
    cap = 0.72
    top = -cap * rend[0][3]; bot = bases[-1]
    shift = cy - (top + bot) / 2
    els = []
    for (img, ox, oy, size, tr, o), b in zip(rend, bases):
        by = b + shift
        if o.get("flip"):        # перевёрнутая строка: визуальный низ стоит там, где была бы базовая линия
            by = by - cap * size
        cx = W / 2 + o.get("dx", 0)
        # центр картинки так, чтобы базовая линия легла на by
        cy_img = by - oy + img.height / 2
        els.append(El(img, cx, cy_img, tr, t_end, "pop"))
        assert cx - img.width / 2 + 40 >= MARGIN and cx + img.width / 2 - 40 <= W - MARGIN, txt_of(o, img)
    return els

def txt_of(o, img): return f"card line too wide: {img.width}"


# ===================== ГРАФИКА =====================
def arrow_img(length, horizontal=True, prog=1.0, width=8, color=ACCENT):
    """M10: стрелка, прорисовка по длине (prog 0..1). Возвращает картинку и центр."""
    pad = 30
    L = length
    size = (L + 2 * pad, 80 + 2 * pad) if horizontal else (80 + 2 * pad, L + 2 * pad)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    def draw(d, col, w):
        if horizontal:
            y = size[1] // 2; xe = pad + L * prog
            d.line((pad, y, xe, y), fill=col, width=w)
            if prog > 0.75:
                k = (prog - 0.75) / 0.25 * 26
                d.line((xe - k, y - k, xe, y), fill=col, width=w); d.line((xe - k, y + k, xe, y), fill=col, width=w)
        else:
            x = size[0] // 2; ye = pad + L - L * prog
            d.line((x, pad + L, x, ye), fill=col, width=w)
            if prog > 0.75:
                k = (prog - 0.75) / 0.25 * 26
                d.line((x - k, ye + k, x, ye), fill=col, width=w); d.line((x + k, ye + k, x, ye), fill=col, width=w)
    sh = Image.new("L", size, 0); draw(ImageDraw.Draw(sh), 255, width + 6)
    sh = sh.filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.6))
    img.paste(Image.new("RGBA", size, (0, 0, 0, 255)), (0, 3), sh)
    d = ImageDraw.Draw(img); draw(d, color + (255,), width)
    return img

class Arrow(El):
    def __init__(self, length, horizontal, cx, cy, t0, t1, draw_time=0.26):
        super().__init__(None, cx, cy, t0, t1, "none", fade_in=0.0)
        self.length, self.horizontal, self.dt = length, horizontal, draw_time
        self.cache = {}
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        p = round(ease_out_cubic(clamp((t - self.t0) / self.dt)), 3)
        if p not in self.cache: self.cache[p] = arrow_img(self.length, self.horizontal, max(p, 0.02))
        self.img = self.cache[p]
        return st

def ease_in_out(p): return 0.5 - 0.5 * math.cos(math.pi * clamp(p))

class Item(El):
    """M07: предметная вставка — 0.9 -> 1, +40px снизу, 280ms; выход 140ms с уменьшением."""
    def __init__(self, img, cx, cy, t0, t1, tilt=0.0, z=5):
        super().__init__(img, cx, cy, t0, t1, "item", rot=tilt, z=z, fade_in=0.12, fade_out=0.14)
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        _, a, _, rot = st
        p = clamp((t - self.t0) / 0.28)
        s = 0.90 + 0.10 * ease_out_back(p, 0.8)
        dy = 40 * (1 - ease_out_cubic(p))
        s *= 1 - 0.06 * (1 - clamp((self.t1 - t) / 0.14))
        return s, a, dy, rot

def shadowed(shape_img, blur=18, alpha=0.30, dy=10):
    """Мягкая сливовая тень под непрозрачной формой (CLAUDE.md §5.2 / плейбук §3.4)."""
    w, h = shape_img.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = shape_img.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    out.paste(Image.new("RGBA", (w, h), (0x24, 0x21, 0x2B, 255)), (0, dy), sh)
    out.alpha_composite(shape_img)
    return out

def answer_sheet():
    """Иллюстрация: страница ответов из сборника. Строки абстрактные — без выдуманных цифр."""
    pw, ph, pad = 250, 310, 40
    img = Image.new("RGBA", (pw + 2 * pad, ph + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0 = pad, pad
    d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), 22, fill=(255, 255, 255, 255))
    d.rounded_rectangle((x0, y0, x0 + pw, y0 + 62), 22, fill=ACCENT + (255,))
    d.rectangle((x0, y0 + 40, x0 + pw, y0 + 62), fill=ACCENT + (255,))
    d.text((x0 + pw / 2, y0 + 45), "ОТВЕТЫ", font=golos(30), fill=INK + (255,), anchor="ms")
    for i, wl in enumerate((150, 110, 170, 90, 135)):
        y = y0 + 92 + i * 42
        d.ellipse((x0 + 26, y, x0 + 44, y + 18), fill=(0x5E, 0x58, 0x6B, 255))
        d.rounded_rectangle((x0 + 60, y + 3, x0 + 60 + wl, y + 15), 6, fill=(0xD9, 0xD6, 0xDE, 255))
    return shadowed(img)

class Sheet(Item):
    """Лист ответов: входит, затем переворачивается вверх ногами (ease in-out, 450ms)."""
    def __init__(self, cx, cy, t0, t1, flip_t, tilt=4.0):
        super().__init__(answer_sheet(), cx, cy, t0, t1, tilt=tilt, z=6)
        self.flip_t = flip_t
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        s, a, dy, rot = st
        return s, a, dy, rot + 180 * ease_in_out((t - self.flip_t) / 0.45)

class Eyes(El):
    """Глаза выглядывают из-за листа (слой ниже листа) и косятся: вниз на лист -> в сторону -> вниз."""
    def __init__(self, cx, cy, t0, t1, z=5):
        super().__init__(None, cx, cy, t0, t1, "none", z=z, fade_in=0.0, fade_out=0.14)
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        lt = t - self.t0
        rise = ease_out_back(clamp(lt / 0.32), 1.2)
        # направление зрачков (dx, dy) по ключам
        keys = [(0.0, (0, 10)), (0.55, (0, 10)), (0.75, (-12, 2)), (1.05, (-12, 2)), (1.25, (0, 10))]
        dx, dyp = keys[-1][1]
        for (ta, va), (tb, vb) in zip(keys, keys[1:]):
            if ta <= lt < tb:
                p = ease_in_out((lt - ta) / (tb - ta))
                dx, dyp = va[0] + (vb[0] - va[0]) * p, va[1] + (vb[1] - va[1]) * p
        # моргание в середине
        blink = 1.0 - 0.85 * max(0.0, 1 - abs(lt - 0.95) / 0.06)
        w, h = 210, 130
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        for ex in (60, 150):
            ey, rx, ry = 66, 38, 44 * blink
            d.ellipse((ex - rx, ey - ry, ex + rx, ey + ry), fill=(255, 255, 255, 255), outline=INK + (255,), width=6)
            if blink > 0.4:
                d.ellipse((ex + dx - 15, ey + dyp - 15, ex + dx + 15, ey + dyp + 15), fill=INK + (255,))
                d.ellipse((ex + dx - 8, ey + dyp - 10, ex + dx - 2, ey + dyp - 4), fill=(255, 255, 255, 255))
        img = img.resize((round(w * 1.25), round(h * 1.25)), Image.BICUBIC)
        self.img = shadowed(img, blur=8, alpha=0.35, dy=4)
        return 1.0, st[1], 120 * (1 - rise), 0.0

class WriteLines(El):
    """«Текстовый разбор»: строки текста дописываются одна за другой (абстрактные полосы)."""
    def __init__(self, cx, cy, t0, t1, widths=(520, 420, 470), per=0.24):
        super().__init__(None, cx, cy, t0, t1, "none", fade_in=0.0)
        self.widths, self.per = widths, per
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        pad, lh, gap = 24, 14, 22
        w = max(self.widths) + 2 * pad + 40; h = len(self.widths) * (lh + gap) + 2 * pad
        shape = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shape)
        for i, wl in enumerate(self.widths):
            p = ease_out_cubic(clamp((t - self.t0 - i * self.per) / self.per))
            if p <= 0: continue
            y = pad + i * (lh + gap); x = pad + 20
            d.ellipse((pad - 4, y - 1, pad + 12, y + 15), fill=ACCENT + (255,))
            d.rounded_rectangle((x, y, x + max(lh, wl * p), y + lh), 7, fill=(255, 255, 255, 235))
        sh = shape.getchannel("A").filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.5))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 3), sh)
        img.alpha_composite(shape)
        self.img = img
        return st

def padlock(open_p):
    """Замок: open_p 0 — закрыт, 1 — дужка поднята и повёрнута."""
    w, h = 90, 110
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    lift = 14 * open_p
    d.arc((24, 12 - lift, 66, 58 - lift), 180, 360, fill=WHITE + (255,), width=8)
    d.line((28 - 0.5, 35 - lift, 28 - 0.5, 52 - lift * (1 - open_p)), fill=WHITE + (255,), width=8)
    d.line((62, 35 - lift, 62, 52 - lift), fill=WHITE + (255,), width=8)
    d.rounded_rectangle((14, 50, 76, 100), 12, fill=ACCENT + (255,))
    d.ellipse((39, 64, 51, 76), fill=INK + (255,)); d.rectangle((43, 72, 47, 86), fill=INK + (255,))
    return img

class LockSteps(El):
    """M09 + замок: путь из сегментов заполняется, и только в конце открывается ответ."""
    def __init__(self, n, cx, cy, t0, t1, fill_t0, fill_dur):
        super().__init__(None, cx, cy, t0, t1, "rise")
        self.n, self.f0, self.fd = n, fill_t0, fill_dur
        self.sw, self.sh, self.gap = 104, 22, 16
        self.unlock_t = fill_t0 + fill_dur
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        pad, lw = 24, 90
        w = self.n * (self.sw + self.gap) + lw + 2 * pad; h = 110 + 2 * pad
        shape = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shape)
        yb = pad + 60
        for i in range(self.n):
            x = pad + i * (self.sw + self.gap)
            d.rounded_rectangle((x, yb, x + self.sw, yb + self.sh), 11, outline=(255, 255, 255, 230), width=3)
            p = clamp((t - self.f0 - i * self.fd / self.n) / (self.fd / self.n))
            if p > 0:
                d.rounded_rectangle((x, yb, x + max(22, self.sw * ease_out_cubic(p)), yb + self.sh), 11, fill=ACCENT + (255,))
        op = ease_out_back(clamp((t - self.unlock_t) / 0.3), 1.2)
        lk = padlock(clamp(op, 0, 1.2))
        k = 1 + 0.12 * math.sin(math.pi * clamp((t - self.unlock_t) / 0.3))
        lk = lk.resize((round(lk.width * k), round(lk.height * k)), Image.BICUBIC)
        lx = pad + self.n * (self.sw + self.gap) + lw / 2
        shape.alpha_composite(lk, (round(lx - lk.width / 2), round(yb + self.sh / 2 - lk.height * 0.62)))
        sh = shape.getchannel("A").filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.45))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 3), sh)
        img.alpha_composite(shape)
        self.img = img
        return st

def link_icon():
    """Иконка ссылки (два звена) для CTA."""
    w = h = 150                      # запас под поворот на 45° без обрезки углов
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for off in (-25, 25):
        box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle((w / 2 - 36 + off, h / 2 - 18, w / 2 + 36 + off, h / 2 + 18), 18,
                                               outline=ACCENT + (255,), width=10)
        img.alpha_composite(box)
    img = img.rotate(-45, resample=Image.BICUBIC)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = img.getchannel("A").filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.6))
    out.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 3), sh)
    out.alpha_composite(img)
    return out

class Bob(El):
    """Обёртка: после входа элемент мягко покачивается по вертикали (луп — linear-синус, 6px)."""
    def __init__(self, inner, start, amp=6, period=1.1):
        super().__init__(None, inner.cx, inner.cy, inner.t0, inner.t1, "none", z=inner.z)
        self.inner, self.start, self.amp, self.period = inner, start, amp, period
    def state(self, t):
        st = self.inner.state(t)
        if st is None: return None
        self.img = self.inner.img
        s, a, dy, rot = st
        if t > self.start:
            dy += -self.amp * math.sin(2 * math.pi * (t - self.start) / self.period)
        return s, a, dy, rot


# ===================== ЗУМ ВИДЕОРЯДА =====================
# Плавные наезды/отъезды на смысловых границах (CLAUDE.md §2.2: 1.06-1.28x). Исходник 1080p,
# поэтому потолок 1.16 — дальше апскейл заметно мылит. Якорь — лицо, оно остаётся на месте.
ZOOM_ANCHOR = (380, 700)
ZOOM_KEYS = [  # (время, масштаб, кривая сегмента, который заканчивается в этой точке)
    (0.00, 1.00, None),
    (1.55, 1.04, "lin"),
    (2.05, 1.12, "ease"),   # «ОТВЕТЫ ВВЕРХ НОГАМИ» — наезд
    (3.55, 1.15, "lin"),
    (4.05, 1.03, "ease"),   # глаза из-за листа — отъезд, освобождаем место справа
    (5.15, 1.05, "lin"),
    (6.55, 1.16, "ease"),   # «здесь подглядывать некуда» — медленный наезд в тишине
    (7.00, 1.00, "ease"),   # «путь → ответ» — общий план
    (8.10, 1.02, "lin"),
    (8.60, 1.10, "ease"),   # «ЕГЭ Тренажёр»
    (9.80, 1.12, "lin"),
    (10.25, 1.03, "ease"),  # «текстовый разбор»
    (11.05, 1.05, "lin"),
    (12.70, 1.15, "ease"),  # «без пути» — нарастание до открытия замка
    (13.20, 1.04, "ease"),  # CTA
    (DUR, 1.08, "lin"),
]

def zoom_at(t):
    for (ta, sa, _), (tb, sb, mode) in zip(ZOOM_KEYS, ZOOM_KEYS[1:]):
        if ta <= t <= tb:
            p = (t - ta) / (tb - ta)
            return sa + (sb - sa) * (ease_in_out(p) if mode == "ease" else p)
    return ZOOM_KEYS[-1][1]

def zoom_frame(src, t):
    s = zoom_at(t)
    if s <= 1.0005:
        return src
    ax, ay = ZOOM_ANCHOR
    box = (ax - ax / s, ay - ay / s, ax + (W - ax) / s, ay + (H - ay) / s)
    return src.resize((W, H), Image.LANCZOS, box=box)


# ===================== БЕГУЩАЯ ПОДПИСЬ (слой 2) =====================
# Тексты фрагментов — расшифровка Whisper, сверенная по смыслу; время фрагментов —
# по провалам громкости, слова внутри фрагмента распределены по слогам.
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
        tot = sum(syl); t = t0 + 0.04
        span = (t1 - 0.04) - t
        for w, s in zip(ws, syl):
            d = span * s / tot
            out.append([w, t, t + d]); t += d
    # склейка «от|вет» на границе фрагментов
    for i, (w, a, b) in enumerate(out):
        if w == "от" and out[i + 1][0] == "вет":
            out[i] = ["ответ", a, out[i + 1][2]]; del out[i + 1]; break
    return out

SHORT = {"в", "и", "к", "на", "но", "я", "где", "без"}
def caption_groups(words):
    """1-2 слова; короткое служебное слово цепляется к следующему. Без разрывов: каждая
    группа висит до старта следующей, последняя — до конца ролика."""
    g, i = [], 0
    while i < len(words):
        w, a, b = words[i]
        if (w.lower() in SHORT or (len(w) <= 3 and w.islower())) and i + 1 < len(words):
            n = words[i + 1]
            txt = w + " " + n[0]; b = n[2]; i += 2
            # не разрывать «ЕГЭ Тренажёр»
            if n[0] == "ЕГЭ" and i < len(words) and words[i][0].startswith("Тренаж"):
                txt += " " + words[i][0]; b = words[i][2]; i += 1
        elif w == "ЕГЭ" and i + 1 < len(words) and words[i + 1][0].startswith("Тренаж"):
            txt = w + " " + words[i + 1][0]; b = words[i + 1][2]; i += 2
        else:
            txt = w; i += 1
        g.append([txt, a, b])
    for k in range(len(g) - 1):
        g[k][2] = g[k + 1][1]
    g[0][1] = 0.0; g[-1][2] = DUR + 1
    return g

def build_captions():
    f = font(F_MANROPE, 42, 600)
    els = []
    for txt, a, b in caption_groups(word_times()):
        img, _ = text_img(txt, f, WHITE, stroke=0, shadow=0.75, blur=6, pad=24)
        assert img.width - 48 <= W - 2 * MARGIN, txt
        # фиксированный слот: центр по X, базовая линия на одной высоте для всех групп
        l, t, r, bt = f.getbbox(txt, anchor="ls")
        el = El(img, W / 2, TOP_SLOT_Y, a, b, "none", fade_in=0.0, fade_out=0.0, z=9)
        el.cy = TOP_SLOT_Y - (24 - t) + img.height / 2 - 14   # baseline = TOP_SLOT_Y + 14
        els.append(el)
    return els

def top_scrim():
    """Мягкая локальная подложка под бегущей подписью: верх кадра — светлое окно и стена."""
    img = Image.new("L", (W, 420), 0)
    ImageDraw.Draw(img).ellipse((200, 140, 880, 300), fill=255)
    img = img.filter(ImageFilter.GaussianBlur(55)).point(lambda v: int(v * 0.42))
    out = Image.new("RGBA", (W, 420), (0x14, 0x12, 0x18, 255)); out.putalpha(img)
    return out


# ===================== ПАРТИТУРА =====================
def build():
    els = []
    # 0.00-1.62  хук: «БУМАЖНЫЕ СБОРНИКИ» — тема + первая фраза одновременно
    els += card([("БУМАЖНЫЕ", 58, WHITE, 0.00, {}),
                 ("СБОРНИКИ", 116, ACCENT, 0.36, {})], t_end=1.62)
    # 1.62-3.48  «ОТВЕТЫ / ВВЕРХ / НОГАМИ» — нижняя строка буквально вверх ногами
    els += card([("ОТВЕТЫ", 60, WHITE, 1.62, {}),
                 ("ВВЕРХ", 128, ACCENT, 2.14, {}),
                 ("НОГАМИ", 66, WHITE, 2.62, {"flip": True})], t_end=3.48)
    # 1.86-5.20  иллюстрация: лист ответов справа от лица, на «ногами» переворачивается
    sheet_cx, sheet_cy = 856, 720
    els.append(Sheet(sheet_cx, sheet_cy, 1.86, 5.20, flip_t=2.72))
    # 3.72-5.20  из-за листа выглядывают глаза и косятся на ответы
    els.append(Eyes(sheet_cx - 6, sheet_cy - 210, 3.72, 5.20))
    # 3.96-5.20  «НО ИНОГДА / ПОДГЛЯДЫВАЮ»
    els += card([("НО ИНОГДА", 58, WHITE, 3.96, {}),
                 ("ПОДГЛЯДЫВАЮ", 98, ACCENT, 4.30, {})], t_end=5.20)
    # 5.20-6.63  тихий участок: только лицо, бегущая подпись и медленный наезд камеры
    # 6.66-8.12  пара «ПУТЬ → ОТВЕТ» + «ПОДРЯД»
    row_y = 1206
    p1, _ = text_img("ПУТЬ", golos(104), WHITE)
    p2, _ = text_img("ОТВЕТ", golos(104), ACCENT)
    els.append(El(p1, 250, row_y, 6.66, 8.12, "pop"))
    els.append(Arrow(150, True, 520, row_y - 4, 6.94, 8.12))
    els.append(El(p2, 790, row_y, 7.14, 8.12, "pop"))
    pd, _ = text_img("ПОДРЯД", golos(58), WHITE)
    els.append(El(pd, 540, row_y + 104, 7.48, 8.12, "pop"))
    # 8.16-9.80  «ЕГЭ ТРЕНАЖЁР»; иконка входит через 300ms и держится до конца (§1.6)
    els += card([("ЕГЭ", 62, WHITE, 8.16, {}),
                 ("ТРЕНАЖЁР", 112, ACCENT, 8.16 + 0.08, {})], t_end=9.80)
    ic = Image.open(ICON).convert("RGBA")
    iw = 280; ic = ic.resize((iw, round(ic.height * iw / ic.width)), Image.LANCZOS)
    els.append(El(ic, W - 54 - iw / 2, 700, 8.46, DUR + 1, "none", fade_in=0.33, fade_out=0.0, z=4))
    # 9.84-11.06  «ТЕКСТОВЫЙ РАЗБОР»
    els += card([("ТЕКСТОВЫЙ", 60, WHITE, 9.84, {}),
                 ("РАЗБОР", 128, ACCENT, 10.10, {})], t_end=11.06, cy=1170)
    els.append(WriteLines(540, 1345, 10.34, 11.06))
    # 11.10-12.74  «без пути» — редкая курсивная подпись + шкала-процесс
    els += card([("ответ не подглядеть", 58, WHITE, 11.10, {"italic": True}),
                 ("БЕЗ ПУТИ", 120, ACCENT, 11.66, {})], t_end=12.74, cy=1196)
    els.append(LockSteps(4, 540, 1372, 11.36, 12.74, fill_t0=11.46, fill_dur=0.94))
    # 12.78-14.98  CTA «ССЫЛКА В ШАПКЕ ПРОФИЛЯ» + стрелка вверх
    els += card([("ССЫЛКА", 62, WHITE, 12.78, {}),
                 ("В ШАПКЕ", 118, ACCENT, 13.30, {}),
                 ("ПРОФИЛЯ", 70, WHITE, 14.08, {})], t_end=DUR + 1)
    arrow = Arrow(190, False, 946, 1236, 13.62, DUR + 1, draw_time=0.3)
    els.append(Bob(arrow, 14.0))
    els.append(Bob(Item(link_icon(), 946, 1080, 13.92, DUR + 1), 14.0))
    els += build_captions()
    els.sort(key=lambda e: e.z)
    return els

def render(els, scrim, t, base=None):
    fr = zoom_frame(base, t).convert("RGBA") if base is not None else Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fr.alpha_composite(scrim, (0, TOP_SLOT_Y - 220))
    for e in els:
        st = e.state(t)
        if st: place(fr, e, st)
    return fr

if __name__ == "__main__":
    els, scrim = build(), top_scrim()
    if sys.argv[1:2] == ["--png"]:
        bg = sys.argv[2]
        for ts in sys.argv[3:]:
            t = float(ts)
            base = Image.open(f"{bg}/{ts}.png").convert("RGB")
            render(els, scrim, t, base).convert("RGB").save(f"qa/{ts}.png")
    elif sys.argv[1:2] == ["--groups"]:
        for g in caption_groups(word_times()): print(f"{g[1]:6.2f}-{g[2]:6.2f} {g[0]}")
    else:
        # исходные кадры (rgb24) из stdin -> зум + графика -> rgb24 в stdout
        inp, out = sys.stdin.buffer, sys.stdout.buffer
        fsz = W * H * 3
        for i in range(NFR):
            raw = inp.read(fsz)
            if len(raw) < fsz: break
            base = Image.frombytes("RGB", (W, H), raw)
            out.write(render(els, scrim, i / FPS, base).convert("RGB").tobytes())
