import json, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

WORK = "/home/user/MyVideo/work"
W, H = 1080, 1920
FPS = 30

plan = json.load(open(f"{WORK}/subtitle_plan.json"))
TOTAL = plan["total"]
N_FRAMES = int(round(TOTAL * FPS))

ACCENT = (201, 245, 255, 255)
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)

font_black = f"{WORK}/fonts/GolosTextBlack.ttf"
font_semibold = f"{WORK}/fonts/ManropeSemiBold.ttf"

def F(path, size):
    return ImageFont.truetype(path, size)

MAIN_SIZE = 108
SEC_SIZE = 54
LINE_SPACING = 0.90
CAPTION_SIZE = 46

def text_size(draw, text, font, stroke=0):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox

def render_card(parts):
    """parts: list of (text, is_main). Returns RGBA image tightly cropped."""
    tmp = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(tmp)
    lines = []
    for text, is_main in parts:
        size = MAIN_SIZE if is_main else SEC_SIZE
        color = ACCENT if is_main else WHITE
        font = F(font_black, size)
        w, h, bbox = text_size(d, text, font, stroke=max(2, size // 22))
        lines.append({"text": text, "font": font, "color": color, "size": size, "w": w, "h": h, "bbox": bbox})

    line_heights = [MAIN_SIZE if p[1] else SEC_SIZE for p in parts]
    total_h = sum(int(lh * LINE_SPACING) for lh in line_heights) + int(line_heights[-1] * 0.15)
    max_w = max(l["w"] for l in lines)
    pad = 40
    canvas = Image.new("RGBA", (max_w + pad * 2, total_h + pad * 2), (0, 0, 0, 0))
    cd = ImageDraw.Draw(canvas)
    y = pad
    for l, lh in zip(lines, line_heights):
        x = pad + (max_w - l["w"]) // 2
        stroke_w = max(2, l["size"] // 22)
        cd.text((x - l["bbox"][0], y - l["bbox"][1]), l["text"], font=l["font"],
                 fill=l["color"], stroke_width=stroke_w, stroke_fill=BLACK)
        y += int(lh * LINE_SPACING)
    return canvas

def render_caption(text):
    font = F(font_semibold, CAPTION_SIZE)
    tmp = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(tmp)
    w, h, bbox = text_size(d, text, font)
    pad = 30
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    # soft shadow
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.text((pad - bbox[0] + 2, pad - bbox[1] + 4), text, font=font, fill=(0, 0, 0, 180))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    canvas = Image.alpha_composite(canvas, shadow)
    cd = ImageDraw.Draw(canvas)
    cd.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=WHITE)
    return canvas

def ease_out_back(x, c1=1.25):
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

# ---- precompute card render cache (by parts tuple) ----
card_img_cache = {}
def get_card_img(idx):
    key = idx
    if key not in card_img_cache:
        card_img_cache[key] = render_card(plan["cards"][idx]["parts"])
    return card_img_cache[key]

caption_img_cache = {}
def get_caption_img(text):
    if text not in caption_img_cache:
        caption_img_cache[text] = render_caption(text)
    return caption_img_cache[text]

# icon
icon_img = Image.open(f"{WORK}/../IMG_0884.png").convert("RGBA")
ICON_W = 272
icon_ratio = icon_img.height / icon_img.width
icon_img = icon_img.resize((ICON_W, int(ICON_W * icon_ratio)), Image.LANCZOS)
ICON_X = W - ICON_W - 60
ICON_Y = 300

CARD_BAND_Y = int(H * 0.68)  # pushed down to clear mouth on tight face crops
CAPTION_Y = 240

def find_card(t):
    for i, c in enumerate(plan["cards"]):
        if c["start"] <= t < c["end"]:
            return i, c
    return None, None

def find_caption(t):
    for c in plan["captions"]:
        if c["start"] <= t < c["end"]:
            return c["text"]
    return plan["captions"][-1]["text"]

def card_alpha_scale(t, c):
    dur_in_scale = 0.32
    dur_in_alpha = 0.14
    dur_out_alpha = 0.09
    rel = t - c["start"]
    rem = c["end"] - t
    if rem <= dur_out_alpha:
        alpha = max(0.0, rem / dur_out_alpha)
    elif rel <= dur_in_alpha:
        alpha = min(1.0, rel / dur_in_alpha)
    else:
        alpha = 1.0
    if rel <= dur_in_scale:
        scale = ease_out_back(min(1.0, rel / dur_in_scale))
    else:
        scale = 1.0
    return alpha, scale

def icon_alpha(t):
    ic = plan["icon"]
    fade = 0.32
    if t < ic["start"] or t > ic["end"]:
        return 0.0
    if t - ic["start"] < fade:
        return (t - ic["start"]) / fade
    if ic["end"] - t < fade:
        return (ic["end"] - t) / fade
    return 1.0

def compose_frame(base_rgb, t):
    frame = Image.fromarray(base_rgb, "RGB").convert("RGBA")

    # caption layer
    cap_text = find_caption(t)
    cap_img = get_caption_img(cap_text)
    cx = (W - cap_img.width) // 2
    cy = CAPTION_Y - cap_img.height // 2
    frame.alpha_composite(cap_img, (cx, cy))

    # card layer
    idx, c = find_card(t)
    if c is not None:
        alpha, scale = card_alpha_scale(t, c)
        if alpha > 0.001:
            base_img = get_card_img(idx)
            if abs(scale - 1.0) > 0.01:
                nw = max(1, int(base_img.width * scale))
                nh = max(1, int(base_img.height * scale))
                img = base_img.resize((nw, nh), Image.LANCZOS)
            else:
                img = base_img
            if alpha < 0.999:
                a = img.split()[3].point(lambda p: int(p * alpha))
                img = img.copy()
                img.putalpha(a)
            x = (W - img.width) // 2
            y = CARD_BAND_Y - img.height // 2
            frame.alpha_composite(img, (x, y))

    # icon layer
    ia = icon_alpha(t)
    if ia > 0.001:
        icon = icon_img
        if ia < 0.999:
            a = icon.split()[3].point(lambda p: int(p * ia))
            icon = icon.copy()
            icon.putalpha(a)
        frame.alpha_composite(icon, (ICON_X, ICON_Y))

    return np.array(frame.convert("RGB"))

def main():
    in_proc = subprocess.Popen(
        ["ffmpeg", "-i", f"{WORK}/cut.mp4", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8,
    )
    out_proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
         f"{WORK}/composited.mp4"],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frame_bytes = W * H * 3
    n = 0
    while True:
        buf = in_proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 3)
        t = n / FPS
        out = compose_frame(arr, t)
        out_proc.stdin.write(out.tobytes())
        n += 1
        if n % 300 == 0:
            print(f"{n}/{N_FRAMES} frames", file=sys.stderr)
    out_proc.stdin.close()
    in_proc.stdout.close()
    out_proc.wait()
    print("done", n, "frames")

if __name__ == "__main__":
    main()
