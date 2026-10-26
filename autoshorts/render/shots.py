"""Cut each chosen shot into a 1080x760 panel clip (seg/NN.mp4)."""
import subprocess
from .. import config

FPS, PW, PH = 30, 1080, 760


def build(job, shots, sources, end):
    seg = job / "seg"; seg.mkdir(exist_ok=True)
    for f in seg.glob("*.mp4"): f.unlink()
    for k, s in enumerate(shots):
        t1 = shots[k + 1]["t0"] if k + 1 < len(shots) else end
        n = round(t1 * FPS) - round(s["t0"] * FPS); dur = n / FPS
        src = sources[s["src"]]; cr = src.get("crop", {})
        w, h, ax, ay = src.get("active") or (src["w"], src["h"], 0, 0)
        top, bot = float(cr.get("top", 0.0)), float(cr.get("bottom", 1.0))
        if bot - top < 0.4: top, bot = 0.0, 1.0
        y0, ch = int(h * top), int(h * (bot - top))
        if h > w:   # portrait source: take a 1080x760-shaped window at yc
            ch = int(w * PH / PW); y0 = int(max(0, min(h - ch, h * float(cr.get("yc", 0.5)) - ch / 2)))
        vf = (f"crop={w}:{ch}:{ax}:{ay + y0},setpts=(PTS-STARTPTS)*{dur / (s['len'] + 0.0001):.5f},fps={FPS},"
              f"scale={PW}:{PH}:force_original_aspect_ratio=increase,crop={PW}:{PH},setsar=1")
        subprocess.run([config.FFMPEG, "-y", "-loglevel", "error", "-ss", f"{s['start']:.2f}", "-t", f"{s['len'] + 0.3:.2f}", "-i", src["path"],
                        "-vf", vf, "-frames:v", str(n), "-an", "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p",
                        str(seg / f"{k:02d}.mp4")], check=True)
