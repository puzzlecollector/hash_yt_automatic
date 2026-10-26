"""1080x1920 Shorts thumbnail: header text on top, two footage frames, big word, red badge."""
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from .. import config

BK = str(config.FONTS / "Pretendard-Black.otf")
YEL, RED, WHITE, INK = (255, 214, 0), (225, 30, 45), (255, 255, 255), (12, 14, 20)
f = lambda s: ImageFont.truetype(BK, s)
def fit(t, s, w):
    while s > 20 and f(s).getlength(t) > w: s -= 2
    return f(s)
def cover(im, w, h, yc=0.4):
    s = max(w / im.width, h / im.height); im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1))
    x, y = (im.width - w) // 2, int((im.height - h) * yc); return im.crop((x, y, x + w, y + h))


def make(th, img_a, img_b, out):
    c = Image.new("RGB", (1080, 1920), INK)
    c.paste(cover(img_a, 1080, 860), (0, 400))
    c.paste(ImageEnhance.Brightness(cover(img_b, 1080, 660)).enhance(0.6), (0, 1260))
    d = ImageDraw.Draw(c)
    def txt(y, t, ft, fill, sw=12): d.text((540, y), t, font=ft, fill=fill, anchor="mt", stroke_width=sw, stroke_fill=(0, 0, 0))
    p = th.get("pill", ""); pf = fit(p, 52, 900); pw = pf.getlength(p) / 2 + 40
    d.rounded_rectangle((540 - pw, 60, 540 + pw, 142), 20, fill=RED); d.text((540, 101), p, font=pf, fill=WHITE, anchor="mm")
    txt(170, th.get("line1", ""), fit(th.get("line1", ""), 120, 1000), WHITE)
    txt(300, th.get("line2", ""), fit(th.get("line2", ""), 80, 1000), YEL, 10)
    txt(1110, th.get("big", ""), fit(th.get("big", ""), 170, 1020), YEL, 14)
    b = th.get("badge", "")
    d.rounded_rectangle((80, 1700, 1000, 1840), 30, fill=RED, outline=WHITE, width=6)
    d.text((540, 1770), b, font=fit(b, 80, 860), fill=WHITE, anchor="mm")
    c.save(out)
