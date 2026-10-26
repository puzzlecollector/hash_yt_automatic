"""Find, download and index YouTube footage for a topic."""
import json, subprocess, urllib.parse
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from . import config

NEWS_CH = ["YTN", "연합뉴스", "KBS", "MBC", "SBS", "JTBC", "채널A", "TV조선", "TVCHOSUN", "MBN", "뉴스1", "한국경제TV", "머니투데이", "SBS Biz", "OBS"]


def _yt(args, timeout=600):
    extra = []
    ck = config.STATE / "youtube_cookies.txt"      # optional: helps on cloud IPs that YouTube rate-limits
    if ck.exists(): extra += ["--cookies", str(ck)]
    return subprocess.run([config.YTDLP, *extra, *args], capture_output=True, text=True, timeout=timeout)


def search(queries, per_query=8):
    seen, out = set(), []
    for q in queries:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp=CAI%253D"   # newest first
        r = _yt(["--flat-playlist", "--playlist-end", str(per_query), "--print", "%(id)s\t%(channel)s\t%(duration)s\t%(title)s", url], 120)
        for line in r.stdout.splitlines():
            p = line.split("\t")
            if len(p) < 4 or p[0] in seen: continue
            try: dur = float(p[2])
            except ValueError: continue
            if not (15 <= dur <= 3600): continue
            seen.add(p[0]); out.append({"yt": p[0], "channel": p[1], "dur": dur, "title": p[3]})
    return out


def _upload_date(vid):
    r = _yt(["--skip-download", "--print", "%(upload_date)s", f"https://youtu.be/{vid}"], 60)
    return r.stdout.strip()


def rank(cands, max_n, days=4):
    """Prefer recent videos from broadcasters; drop old ones."""
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    scored = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        for c, d in zip(cands[:30], ex.map(lambda c: _upload_date(c["yt"]), cands[:30])): c["date"] = d
    for c in cands[:30]:
        if c["date"] and c["date"] < cut: continue
        s = (2 if any(n.lower() in c["channel"].lower() for n in NEWS_CH) else 0) + (1 if 60 < c["dur"] <= 400 else 0) - (1.5 if c["dur"] <= 60 else 0)
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:max_n]]


def download(c, dst):
    out = dst / f"{c['yt']}.mp4"
    if not out.exists():
        _yt(["-q", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba", "--merge-output-format", "mp4",
             "--download-sections", f"*0-{config.MAX_SOURCE_SEC}", "-o", str(out), "--", c["yt"]], 900)
    if not out.exists(): return None
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height:format=duration",
                         "-of", "json", str(out)], capture_output=True, text=True)
    j = json.loads(pr.stdout)
    st = j["streams"][0]; c.update(path=str(out), w=st["width"], h=st["height"], dur=float(j["format"]["duration"]))
    c["active"] = active_area(str(out), c["dur"], c["w"], c["h"])
    return c


def active_area(path, dur, w, h):
    """Detect letter/pillar-box bars; returns (w, h, x, y) of the picture area."""
    import re as _re
    r = subprocess.run([config.FFMPEG, "-ss", str(min(20, dur * 0.3)), "-t", "6", "-i", path, "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = _re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
    if not m: return (w, h, 0, 0)
    cw, ch, x, y = map(int, m[-1])
    if cw * ch < 0.15 * w * h or (cw > 0.97 * w and ch > 0.97 * h): return (w, h, 0, 0)
    return (cw, ch, x, y)


def scenes(path):
    p = subprocess.run([config.FFMPEG, "-loglevel", "error", "-i", path, "-vf", "fps=10,scale=64:36,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True).stdout
    a = np.frombuffer(p, np.uint8).reshape(-1, 36 * 64).astype(np.int16)
    if len(a) < 3: return [(0.0, len(a) / 10)]
    d = np.abs(np.diff(a, axis=0)).mean(1)
    med = np.array([np.median(d[max(0, i - 6):i + 7]) for i in range(len(d))])
    cuts = [0.0] + [round((i + 1) / 10, 1) for i in np.where((d > 9) & (d > 2.2 * med))[0]] + [len(a) / 10]
    return [(float(cuts[i]), float(cuts[i + 1])) for i in range(len(cuts) - 1) if cuts[i + 1] - cuts[i] >= 0.8]


def sheet(c, out):
    """Contact sheet: one big frame on top + up to 60 small frames labelled with seconds."""
    ft = ImageFont.truetype(str(config.FONTS / "Pretendard-Black.otf"), 18)
    n = 60; step = max(1.5, c["dur"] / n); ts = [round(i * step, 1) for i in range(int(c["dur"] / step))][:n]
    W, H, cols = 170, 96, 10
    if c["h"] > c["w"]: W, H, cols = 72, 128, 15
    rows = (len(ts) + cols - 1) // cols
    big = _frame(c["path"], c["dur"] * 0.4, 640)
    S = Image.new("RGB", (max(W * cols, big.width), big.height + H * rows + 30), (0, 0, 0)); dr = ImageDraw.Draw(S)
    S.paste(big, (0, 0)); dr.text((6, big.height + 4), f"{c['id']}  {c['channel']}  {c['title'][:50]}", font=ft, fill=(0, 255, 255))
    for i, t in enumerate(ts):
        im = _frame(c["path"], t, W, H)
        x, y = (i % cols) * W, big.height + 30 + (i // cols) * H
        S.paste(im, (x, y)); dr.text((x + 3, y + 2), f"{t:g}", font=ft, fill=(255, 255, 0), stroke_width=2, stroke_fill=0)
    S.save(out, quality=85)
    return out


def _frame(path, t, w, h=None):
    vf = f"scale={w}:{h if h else -2}"
    b = subprocess.run([config.FFMPEG, "-loglevel", "error", "-ss", str(t), "-i", path, "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True).stdout
    from io import BytesIO
    try: return Image.open(BytesIO(b)).convert("RGB")
    except Exception: return Image.new("RGB", (w, h or int(w * 9 / 16)))


def snap(start, length, scs, dur):
    """Move a shot start so [start, start+length] stays inside one scene if possible."""
    for a, b in scs:
        if a - 0.05 <= start < b:
            if b - a >= length + 0.2:
                return max(a + 0.1, min(start, b - length - 0.1))
            break
    best = min((s for s in scs if s[1] - s[0] >= length + 0.2), key=lambda s: abs(s[0] - start), default=None)
    if best: return max(best[0] + 0.1, min(start, best[1] - length - 0.1))
    return max(0.0, min(start, dur - length - 0.1))
