#!/usr/bin/env python3
"""Графический слой для ролика «ответы вверх ногами» (исходник 1080x1920, 25fps, 14.98с).

Видеоряд не режется и не кадрируется: всё ниже — оверлей поверх исходника.
Выход: сырые RGBA-кадры в stdout (ffmpeg накладывает их на видео).
Кадры: python3 render.py --png 4.0 6.9 ... пишет стоп-кадры в qa/.
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
def bubble(lines, t0, t1, cx, cy):
    """M11: молочное облачко, тёмный текст, хвост к лицу (влево)."""
    fs = [(golos(sz), sz, col) for _, sz, col in lines]
    ws = [f.getbbox(t, anchor="ls")[2] for (t, _, _), (f, _, _) in zip(lines, fs)]
    bw = max(ws) + 48
    bh = int(sum(sz * 0.9 for _, sz, _ in lines) + 54)
    pad = 40
    img = Image.new("RGBA", (bw + 2 * pad + 40, bh + 2 * pad + 30), (0, 0, 0, 0))
    x0, y0 = pad + 40, pad
    shape = Image.new("L", img.size, 0); d = ImageDraw.Draw(shape)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 34, fill=255)
    d.polygon([(x0 + 10, y0 + bh - 46), (x0 - 34, y0 + bh + 18), (x0 + 58, y0 + bh - 8)], fill=255)
    sh = shape.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.30))
    img.paste(Image.new("RGBA", img.size, (0x24, 0x21, 0x2B, 255)), (0, 10), sh)
    img.paste(Image.new("RGBA", img.size, (255, 255, 255, 255)), (0, 0), shape)
    d = ImageDraw.Draw(img)
    y = y0 + 28
    for (t, sz, col), (f, _, _) in zip(lines, fs):
        y += sz * 0.9 if y > y0 + 28 else sz * 0.72
        d.text((x0 + bw / 2, y), t, font=f, fill=col + (255,), anchor="ms")
    # правый край облачка — в action-safe (поле 54px)
    cx = min(cx, W - 54 - (x0 + bw) + img.width / 2)
    body_left = cx - img.width / 2 + x0          # хвост (ещё 34px левее) указывает на лицо, но не заходит на него
    assert body_left >= 600, f"bubble reaches face: {body_left}"
    return El(img, cx, cy, t0, t1, "bubble", fade_in=0.08, fade_out=0.09)

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

class Steps(El):
    """M09: шкала из сегментов, заполнение слева направо. Без чисел — процесс, а не данные."""
    def __init__(self, n, cx, cy, t0, t1, fill_t0, fill_dur):
        super().__init__(None, cx, cy, t0, t1, "rise")
        self.n, self.f0, self.fd = n, fill_t0, fill_dur
        self.sw, self.sh, self.gap = 96, 22, 16
    def state(self, t):
        st = super().state(t)
        if st is None: return None
        pad = 24
        w = self.n * self.sw + (self.n - 1) * self.gap + 2 * pad; h = self.sh + 2 * pad
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh = Image.new("L", (w, h), 0); ds = ImageDraw.Draw(sh)
        d = ImageDraw.Draw(img)
        for i in range(self.n):
            x = pad + i * (self.sw + self.gap)
            ds.rounded_rectangle((x, pad, x + self.sw, pad + self.sh), 11, fill=255)
        sh = sh.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.45))
        img.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 3), sh)
        for i in range(self.n):
            x = pad + i * (self.sw + self.gap)
            box = (x, pad, x + self.sw, pad + self.sh)
            d.rounded_rectangle(box, 11, outline=(255, 255, 255, 230), width=3)
            p = clamp((t - self.f0 - i * self.fd / self.n) / (self.fd / self.n))
            if p > 0:
                d.rounded_rectangle((x, pad, x + max(22, self.sw * ease_out_cubic(p)), pad + self.sh), 11, fill=ACCENT + (255,))
        self.img = img
        return st


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
    # 3.72-5.24  реплика-признание: облачко у лица (смена носителя)
    els.append(bubble([("НО ИНОГДА", 34, (0x5E, 0x58, 0x6B)), ("ПОДГЛЯДЫВАЮ", 44, INK)],
                      3.72, 5.24, cx=826, cy=650))
    # 5.24-6.63  тихий сброс (M15): только лицо и бегущая подпись
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
                 ("РАЗБОР", 128, ACCENT, 10.10, {})], t_end=11.06)
    # 11.10-12.74  «без пути» — редкая курсивная подпись + шкала-процесс
    els += card([("ответ не подглядеть", 58, WHITE, 11.10, {"italic": True}),
                 ("БЕЗ ПУТИ", 120, ACCENT, 11.66, {})], t_end=12.74, cy=1196)
    els.append(Steps(5, 540, 1372, 11.36, 12.74, fill_t0=11.46, fill_dur=1.0))
    # 12.78-14.98  CTA «ССЫЛКА В ШАПКЕ ПРОФИЛЯ» + стрелка вверх
    els += card([("ССЫЛКА", 62, WHITE, 12.78, {}),
                 ("В ШАПКЕ", 118, ACCENT, 13.30, {}),
                 ("ПРОФИЛЯ", 70, WHITE, 14.08, {})], t_end=DUR + 1)
    els.append(Arrow(190, False, 946, 1236, 13.62, DUR + 1, draw_time=0.3))
    els += build_captions()
    els.sort(key=lambda e: e.z)
    return els

def render(els, scrim, t):
    fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
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
            base = Image.open(f"{bg}/{ts}.png").convert("RGBA")
            base.alpha_composite(render(els, scrim, t))
            base.convert("RGB").save(f"qa/{ts}.png")
    elif sys.argv[1:2] == ["--groups"]:
        for g in caption_groups(word_times()): print(f"{g[1]:6.2f}-{g[2]:6.2f} {g[0]}")
    else:
        out = sys.stdout.buffer
        for i in range(NFR):
            out.write(render(els, scrim, i / FPS).tobytes())
