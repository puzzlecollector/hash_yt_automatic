"""ElevenLabs narration (with character timestamps) and background music."""
import base64, json
import requests
from . import config


def to_tts(s, rep):
    for a, b in rep:
        s = s.replace(a, b)
    return s


def narrate(plan, job):
    rep = [tuple(x) for x in plan.get("tts_replace", [])]
    if ("'", "") not in rep: rep.append(("'", ""))
    disp = plan["lines"]
    lines = [to_tts(d.replace(" / ", " "), rep) for d in disp]
    text = " ".join(lines)
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{config.VOICE_ID}/with-timestamps",
                      headers={"xi-api-key": config.ELEVENLABS_API_KEY}, timeout=300,
                      json=dict(text=text, model_id="eleven_multilingual_v2",
                                voice_settings=dict(stability=0.4, similarity_boost=0.8, style=0.35, use_speaker_boost=True, speed=config.VOICE_SPEED)))
    d = r.json()
    if "audio_base64" not in d:
        raise RuntimeError(f"TTS failed: {str(d)[:300]}")
    (job / "vo.mp3").write_bytes(base64.b64decode(d["audio_base64"]))
    al = d["alignment"]
    cs, ce = al["character_start_times_seconds"], al["character_end_times_seconds"]
    # chunk start times: where each " / " piece's first word is spoken
    chunks, pos = [], 0
    for li, L in enumerate(lines):
        i = text.index(L, pos); cur = i; pos = i + len(L)
        for p in disp[li].split(" / "):
            tp = to_tts(p, rep); w0 = tp.split(" ")[0]
            j = text.find(w0, cur)
            if j < 0: j = cur
            cur = j + max(1, len(tp) - 2)
            chunks.append({"line": li, "t": round(cs[min(j, len(cs) - 1)], 3), "text": p.strip()})
    vo_end = ce[-1]
    for k, c in enumerate(chunks):
        c["end"] = chunks[k + 1]["t"] if k + 1 < len(chunks) else vo_end + 0.5
    timing = {"vo_end": vo_end, "chunks": chunks,
              "line_start": [next(c["t"] for c in chunks if c["line"] == li) for li in range(len(disp))]}
    (job / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1))
    return timing


def music(prompt, seconds, out):
    r = requests.post("https://api.elevenlabs.io/v1/music", headers={"xi-api-key": config.ELEVENLABS_API_KEY},
                      json=dict(prompt=prompt, music_length_ms=int(seconds * 1000), force_instrumental=True), timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"music failed {r.status_code}: {r.text[:200]}")
    out.write_bytes(r.content)


def segments(timing, end):
    """Group subtitle chunks into shots of ~1.8-4.2 s."""
    ch = timing["chunks"]; segs = []; cur = None
    for c in ch:
        if cur is None:
            cur = {"t0": c["t"], "t1": c["end"], "text": c["text"], "line": c["line"]}
            continue
        new_line = c["line"] != cur["line"]
        if (cur["t1"] - cur["t0"] < 1.8 and not new_line) or (c["end"] - cur["t0"] < 3.2 and not new_line):
            cur["t1"] = c["end"]; cur["text"] += " " + c["text"]
        else:
            segs.append(cur); cur = {"t0": c["t"], "t1": c["end"], "text": c["text"], "line": c["line"]}
    if cur: segs.append(cur)
    segs[0]["t0"] = 0.0
    for k in range(len(segs) - 1): segs[k]["t1"] = segs[k + 1]["t0"]
    segs[-1]["t1"] = end
    # split very long shots
    out = []
    for s in segs:
        d = s["t1"] - s["t0"]
        if d > 4.6:
            n = int(d // 3.2) + 1; step = d / n
            for j in range(n): out.append({**s, "t0": s["t0"] + j * step, "t1": s["t0"] + (j + 1) * step})
        else:
            out.append(s)
    for i, s in enumerate(out): s["i"] = i
    return out
