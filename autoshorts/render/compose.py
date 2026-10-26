"""Frame compositor for the channel's v2 layout:
header 0-400 | footage panel 400-1160 | info card 1176-1412 | subtitles 1430 | progress bar on top."""
import glob, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from .. import config

W, H, FPS = 1080, 1920, 30
F_BK, F_PR = str(config.FONTS / "Pretendard-Black.otf"), str(config.FONTS / "Pretendard-ExtraBold.otf")
YEL, RED, WHITE, INK = (255, 214, 0), (225, 30, 45), (255, 255, 255), (12, 14, 20)
BLUE = (70, 130, 245)
ACCENT = {"yellow": YEL, "red": RED, "blue": BLUE}
PY0, PW, PH = 400, 1080, 760
IY0, IH, SUBY = 1176, 236, 1430
IW = 1010
CARD_BG, GREY = (20, 22, 30, 255), (190, 192, 204)
_fc = {}
def f(p, s):
    k = (p, s)
    if k not in _fc: _fc[k] = ImageFont.truetype(p, s)
    return _fc[k]
def fitf(s, path, size, maxw):
    while size > 16 and f(path, size).getlength(s) > maxw: size -= 2
    return f(path, size)
def card(w, h, fn):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); fn(ImageDraw.Draw(im)); return im
def tag(s, bg=RED, fg=WHITE, size=40):
    ft = f(F_BK, size); w = int(ft.getlength(s)) + 56; h = size + 40
    return card(w, h, lambda dr: (dr.rounded_rectangle((0, 0, w, h), 18, fill=bg), dr.text((28, 12), s, font=ft, fill=fg)))
def big(top, num, bot, accent=YEL):
    def fn(dr):
        dr.rounded_rectangle((0, 0, IW, IH), 28, fill=CARD_BG, outline=accent, width=4)
        fn_ = fitf(num, F_BK, 124, 520); nw = fn_.getlength(num)
        dr.text((40, IH // 2), num, font=fn_, fill=accent, anchor="lm")
        x = 40 + nw + 44; mw = IW - x - 30
        dr.text((x, IH // 2 - 8), top, font=fitf(top, F_BK, 50, mw), fill=WHITE, anchor="ls")
        dr.text((x, IH // 2 + 12), bot, font=fitf(bot, F_PR, 38, mw), fill=GREY, anchor="lt")
    return card(IW, IH, fn)
def end_card(q, sub):
    def fn(dr):
        dr.rounded_rectangle((0, 0, IW, IH), 28, fill=CARD_BG, outline=RED, width=4)
        dr.text((IW // 2, 18), "여러분 생각은?", font=f(F_BK, 84), fill=YEL, anchor="mt")
        dr.text((IW // 2, 120), q, font=fitf(q, F_BK, 48, IW - 60), fill=WHITE, anchor="mt")
        dr.text((IW // 2, 184), sub, font=fitf(sub, F_PR, 34, IW - 60), fill=(255, 140, 150), anchor="mt")
    return card(IW, IH, fn)
def ease(x):
    x = min(max(x, 0), 1); c = 1.70158; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def render(job, plan, timing, shots, credits, end, preview=None):
    keys = sorted(plan.get("keys", []), key=len, reverse=True)
    chunks = [(c["t"], c["end"], c["text"].rstrip(",.")) for c in timing["chunks"]]

    def render_sub(s):
        ft = f(F_BK, 76); segs, i = [], 0
        while i < len(s):
            hit = next((k for k in keys if k and s.startswith(k, i)), None)
            if hit: segs.append((hit, YEL)); i += len(hit)
            else:
                if segs and segs[-1][1] == WHITE: segs[-1] = (segs[-1][0] + s[i], WHITE)
                else: segs.append((s[i], WHITE))
                i += 1
        tw = sum(ft.getlength(t) for t, _ in segs)
        im = Image.new("RGBA", (int(tw) + 60, 120), (0, 0, 0, 0)); dr = ImageDraw.Draw(im); x = 30
        for t, c in segs:
            dr.text((x, 14), t, font=ft, fill=c, stroke_width=9, stroke_fill=(0, 0, 0)); x += ft.getlength(t)
        if im.width > W - 40: im = im.resize((W - 40, int(im.height * (W - 40) / im.width)), Image.LANCZOS)
        return im
    sub_imgs = [render_sub(w) for _, _, w in chunks]

    ls = timing["line_start"]; cards = []
    cl = sorted(plan.get("cards", []), key=lambda c: c["line"])
    last_line = len(plan["lines"]) - 1
    for k, c in enumerate(cl):
        li = min(c["line"], last_line)
        a = ls[li]; b = ls[min(cl[k + 1]["line"], last_line)] if k + 1 < len(cl) else ls[last_line]
        if b - a < 0.5: continue
        cards.append((a, b - 0.05, big(c["top"], c["num"], c["bot"], ACCENT.get(c.get("accent", "yellow"), YEL))))
    ec = plan.get("end_card", {})
    cards.append((ls[last_line], end + 1, end_card(ec.get("q", ""), ec.get("sub", "댓글로 의견 남겨주세요"))))

    base = Image.new("RGB", (W, H), INK); hd = ImageDraw.Draw(base)
    t0 = tag(plan.get("tag", "실시간 트렌드")); base.paste(t0, ((W - t0.width) // 2, 70), t0)
    hd.text((W // 2, 150), plan["header1"], font=fitf(plan["header1"], F_BK, 96, 1000), fill=WHITE, anchor="mt")
    hd.text((W // 2, 262), plan["header2"], font=fitf(plan["header2"], F_BK, 96, 1000), fill=YEL, anchor="mt")

    def reader(path):
        p = subprocess.Popen([config.FFMPEG, "-loglevel", "quiet", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        try:
            while True:
                b = p.stdout.read(PW * PH * 3)
                if len(b) < PW * PH * 3: break
                yield Image.frombuffer("RGB", (PW, PH), b)
        finally:
            p.kill(); p.wait()
    def panel_frames():
        for k, seg in enumerate(sorted(glob.glob(str(job / "seg/*.mp4")))):
            for fr in reader(seg): yield k, fr
    pf = panel_frames()

    NF = int(end * FPS); prev = [int(x * FPS) for x in (preview or [])]; saved = []
    out = None if prev else subprocess.Popen([config.FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                              "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                                              str(job / "video_noaudio.mp4")], stdin=subprocess.PIPE)
    last_k, last_fr, shot_t0, bgfull = 0, None, 0, None
    for n in range(NF):
        t = n / FPS
        try: k, fr = next(pf)
        except StopIteration: k, fr = last_k, last_fr
        if fr is None: fr = Image.new("RGB", (PW, PH))
        if k != last_k or n == 0: shot_t0 = t
        last_k, last_fr = k, fr
        panel = fr.convert("RGBA"); lt = t - shot_t0
        if lt < 0.2:
            z = 1 + 0.04 * (1 - lt / 0.2); cw, ch = int(PW / z), int(PH / z)
            panel = panel.crop(((PW - cw) // 2, (PH - ch) // 2, (PW - cw) // 2 + cw, (PH - ch) // 2 + ch)).resize((PW, PH), Image.BILINEAR)
        if n % 3 == 0 or prev or bgfull is None:
            small = panel.convert("RGB").resize((54, 96), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
            bgfull = ImageEnhance.Brightness(small.resize((W, H), Image.BILINEAR)).enhance(0.35)
        frame = bgfull.copy(); frame.paste(base.crop((0, 0, W, PY0)), (0, 0))
        cr = credits[min(k, len(credits) - 1)] if credits else ""
        if cr:
            ImageDraw.Draw(panel).text((PW - 16, PH - 14), f"영상: {cr}", font=f(F_PR, 24), fill=(235, 235, 235), anchor="rs", stroke_width=2, stroke_fill=(0, 0, 0))
        frame.paste(panel.convert("RGB"), (0, PY0))
        for a, b, im in cards:
            if a <= t < b:
                e = ease((t - a) / 0.25)
                if e < 0.999: im = im.resize((max(1, int(im.width * e)), max(1, int(im.height * e))), Image.BILINEAR)
                frame.paste(im, ((W - im.width) // 2, IY0 + (IH - im.height) // 2), im); break
        for ci, (a, b, w) in enumerate(chunks):
            if a - 0.05 <= t < b:
                si = sub_imgs[ci]; p = ease((t - a + 0.05) / 0.15)
                if p < 0.999: si = si.resize((max(1, int(si.width * (0.85 + 0.15 * p))), max(1, int(si.height * (0.85 + 0.15 * p)))), Image.BILINEAR)
                frame.paste(si, ((W - si.width) // 2, SUBY + (120 - si.height) // 2), si); break
        ImageDraw.Draw(frame).rectangle((0, 0, int(W * t / end), 10), fill=YEL)
        if prev:
            if n in prev:
                pth = job / f"prev_{n:04d}.jpg"; frame.save(pth, quality=85); saved.append(pth)
            if n >= max(prev): pf.close(); break
            continue
        out.stdin.write(frame.tobytes())
    if out:
        out.stdin.close(); out.wait()
    return saved


def mix(job, end, sfx_times, out_path):
    vo_end = __import__("json").load(open(job / "timing.json"))["vo_end"]
    inp = ["-i", str(job / "video_noaudio.mp4"), "-i", str(job / "vo.mp3"), "-i", str(job / "bgm.mp3")]
    fl = [f"[1:a]atrim=0:{vo_end + 0.25:.2f},afade=t=out:st={vo_end + 0.1:.2f}:d=0.15,apad[vo]",
          f"[2:a]volume=0.17,atrim=0:{end},afade=t=out:st={end - 1.5:.2f}:d=1.5[bg]"]
    labels = ["[vo]", "[bg]"]; n = 3
    for name, t, vol in sfx_times:
        inp += ["-i", str(config.SFX / name)]; d = int(t * 1000)
        fl.append(f"[{n}:a]volume={vol},adelay={d}|{d}[s{n}]"); labels.append(f"[s{n}]"); n += 1
    fl.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11,volume=2.4dB,alimiter=limit=0.85:level=false[a]")
    subprocess.run([config.FFMPEG, "-y", "-loglevel", "error", *inp, "-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", str(end), str(out_path)], check=True)
