"""Trending keyword -> finished Short (mp4 + thumbnail + upload metadata)."""
import json, re, shutil, string, threading, time, traceback
from datetime import datetime
from . import config, trends, research, planner, voice, footage
from .render import shots as shotlib, compose, thumb

HANJA = re.compile(r"[㐀-鿿豈-﫿]")


def log(job, msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(job / "log.txt", "a") as fh: fh.write(line + "\n")


def _slug(s):
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    return s[:40] or "topic"


def _clean(plan):
    """Strip hanja/emoji the fonts can't draw and keep key strings that actually occur in subtitles."""
    def fix(x):
        if isinstance(x, str): return HANJA.sub("", re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", x)).strip()
        if isinstance(x, list): return [fix(i) for i in x]
        if isinstance(x, dict): return {k: fix(v) for k, v in x.items()}
        return x
    plan = fix(plan)
    joined = " ".join(p for l in plan["lines"] for p in l.split(" / "))
    plan["keys"] = [k for k in plan.get("keys", []) if k and k in joined]
    return plan


def _choose_shots(segs, pick, srcs):
    used = {}; out = []; order = [s for s in pick.get("use", []) if s in srcs] or list(srcs)
    chosen = {p["i"]: p for p in pick.get("shots", []) if p.get("src") in srcs}
    for g in segs:
        L = g["t1"] - g["t0"]; p = chosen.get(g["i"])
        if p: sid, st = p["src"], float(p["start"])
        else:   # fallback: next unused scene of the preferred sources
            sid = order[g["i"] % len(order)]; st = used.get(sid, 0) + 1.0
        s = srcs[sid]
        st = footage.snap(st, L, s["scenes"], s["dur"])
        used[sid] = st + L
        out.append({"t0": g["t0"], "src": sid, "start": round(st, 2), "len": L})
    return out


def make_short(item, today=None):
    today = today or datetime.now().strftime("%Y-%m-%d")
    kw = item["keyword"]
    job = config.JOBS / f"{datetime.now():%Y%m%d_%H%M}_{_slug(kw)}"
    job.mkdir(parents=True, exist_ok=True)
    log(job, f"topic: {kw}  (traffic {item.get('traffic')}, score {item.get('score')})")
    try:
        res = research.collect(item)
        (job / "research.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        log(job, f"articles {len(res['articles'])}, headlines {len(res['headlines'])}")
        if not res["articles"] and len(res["headlines"]) < 3:
            return _finish(job, kw, "skipped", "기사 부족")

        plan = planner.write_plan(kw, res, today)
        if plan.get("skip"):
            (job / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
            return _finish(job, kw, "skipped", plan.get("skip_reason", ""))
        plan = _clean(plan)
        (job / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
        log(job, f"plan: {plan['header1']} / {plan['header2']}  risk={plan.get('risk')}")

        timing = voice.narrate(plan, job)
        end = round(timing["vo_end"] + 1.3, 2)
        log(job, f"narration {timing['vo_end']:.1f}s -> video {end}s")
        bgm_err = []
        th = threading.Thread(target=lambda: _safe(bgm_err, voice.music, plan.get("bgm_prompt", "news background, no vocals"), end + 3, job / "bgm.mp3"))
        th.start()

        src_dir = job / "src"; src_dir.mkdir(exist_ok=True)
        qs = plan.get("footage_queries", []) + [kw, f"{kw} 뉴스"]
        found = footage.search(qs)
        cands = footage.rank(found, config.MAX_SOURCES + 2)
        if len(cands) < 3:   # evergreen/social topics: allow older coverage, labelled as archive footage
            fresh = {c["yt"] for c in cands}
            more = footage.rank([c for c in found if c["yt"] not in fresh], config.MAX_SOURCES + 2, days=1100)
            for c in more: c["archive"] = True
            cands += more
        srcs = {}
        for c in cands:
            if len(srcs) >= config.MAX_SOURCES: break
            c = footage.download(c, src_dir)
            if not c: continue
            c["id"] = string.ascii_uppercase[len(srcs)]
            c["scenes"] = footage.scenes(c["path"])
            c["sheet"] = str(footage.sheet(c, job / f"sheet_{c['id']}.jpg"))
            srcs[c["id"]] = c
        log(job, f"footage: {[(k, v['channel'], v['title'][:30]) for k, v in srcs.items()]}")
        if not srcs:
            th.join(); return _finish(job, kw, "failed", "자료화면 없음")

        segs = voice.segments(timing, end)
        feedback = None
        for attempt in range(2):     # QA fails -> re-pick shots once with the reviewer's notes
            pick = planner.pick_shots(plan, segs, list(srcs.values()), [v["sheet"] for v in srcs.values()], cwd=str(job), feedback=feedback)
            (job / f"pick{attempt}.json").write_text(json.dumps(pick, ensure_ascii=False, indent=1))
            for sid, cr in pick.get("crop", {}).items():
                if sid in srcs: srcs[sid]["crop"] = cr
            shots = _choose_shots(segs, pick, srcs)
            (job / "shots.json").write_text(json.dumps(shots, ensure_ascii=False, indent=1))
            credit = pick.get("credit", {})
            credits = [credit.get(s["src"], srcs[s["src"]]["channel"]) + (" · 자료화면" if srcs[s["src"]].get("archive") else "") for s in shots]
            shotlib.build(job, shots, srcs, end)
            times = [1.0, end * 0.25, end * 0.45, end * 0.65, end * 0.85, end - 0.5]
            prev = compose.render(job, plan, timing, shots, credits, end, preview=times)
            q = planner.qa(plan, prev, cwd=str(job))
            (job / "qa.json").write_text(json.dumps(q, ensure_ascii=False, indent=1))
            log(job, f"QA[{attempt}] ok={q.get('ok')} issues={q.get('issues')}")
            for p_ in prev: p_.unlink(missing_ok=True)
            if q.get("ok"): break
            seg_at = lambda t: next((g["i"] for g in segs if g["t0"] <= t < g["t1"]), None)
            feedback = "\n".join(q.get("issues", [])) + "\n(미리보기 프레임 prev_NNNN = NNNN/30초. 해당 시각 구간: " + \
                       ", ".join(f"{int(t*30):04d}->구간{seg_at(t)}" for t in times) + ")"
        th.join()
        if bgm_err: raise bgm_err[0]

        compose.render(job, plan, timing, shots, credits, end)
        sfx = [("boom.mp3", 0.05, 0.25)] + [("whoosh.mp3", t, 0.2) for t in timing["line_start"][1:]]
        final = job / "final.mp4"
        compose.mix(job, end, sfx, final)

        ta, tb = pick.get("thumb", {}).get("a", {}), pick.get("thumb", {}).get("b", {})
        fa = footage._frame(srcs.get(ta.get("src"), next(iter(srcs.values())))["path"], float(ta.get("t", 5)), 1920)
        fb = footage._frame(srcs.get(tb.get("src"), list(srcs.values())[-1])["path"], float(tb.get("t", 5)), 1920)
        thumb.make(plan.get("thumbnail", {}), fa, fb, job / "thumb.png")

        status = "ready" if q.get("ok", False) and plan.get("risk") != "high" and len({s_["src"] for s_ in shots}) >= 2 else "needs_review"
        return _finish(job, kw, status, "; ".join(q.get("issues", [])), plan, srcs, res)
    except Exception as e:
        log(job, "ERROR " + traceback.format_exc())
        return _finish(job, kw, "failed", str(e)[:300])


def _safe(errs, fn, *a):
    try: fn(*a)
    except Exception as e: errs.append(e)


def _finish(job, kw, status, note, plan=None, srcs=None, res=None):
    slug = (plan or {}).get("slug") or _slug(kw)
    trends.mark_used(kw, slug, status)
    meta = {"keyword": kw, "status": status, "note": note, "job": str(job), "created": datetime.now().isoformat()}
    if plan and status in ("ready", "needs_review"):
        out = config.OUTPUT / (status if status == "needs_review" else "ready") / f"{datetime.now():%Y-%m-%d_%H%M}_{slug}"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(job / "final.mp4", out / "short.mp4")
        shutil.copy(job / "thumb.png", out / "thumb.png")
        up = plan.get("upload", {})
        credits = sorted({v["channel"] for v in (srcs or {}).values()})
        refs = sorted({a.get("source", "") for a in (res or {}).get("articles", []) if a.get("source")})
        desc = up.get("description", "") + "\n\n영상: " + ", ".join(credits) + ("\n참고: " + ", ".join(refs) if refs else "") + "\n" + " ".join(up.get("hashtags", []))
        meta.update(title=(up.get("titles") or [plan["header1"]])[0], titles=up.get("titles", []), description=desc,
                    tags=up.get("tags", []), video=str(out / "short.mp4"), thumbnail=str(out / "thumb.png"),
                    risk=plan.get("risk"), risk_notes=plan.get("risk_notes"), uploaded=False)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        (out / "업로드용.md").write_text(
            f"# {plan['header1']} / {plan['header2']}\n\n상태: {status} {('- ' + note) if note else ''}\n\n## 제목 (택1)\n" +
            "\n".join(f"- {t}" for t in up.get("titles", [])) + f"\n\n## 설명\n{desc}\n\n## 태그\n{', '.join(up.get('tags', []))}\n\n"
            f"## 리스크\n{plan.get('risk')} - {plan.get('risk_notes', '')}\n")
        meta["out"] = str(out)
    (job / "result.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    log(job, f"DONE {status} {note}")
    return meta


def run_once(n=None, progress=None):
    progress = progress or (lambda m: None)
    n = n or config.TOPICS_PER_RUN
    _cleanup()
    cands = trends.candidates()
    used = trends.recently_used()
    used_kw = {u["keyword"] for u in used}
    progress("주제 선택 중")
    sel = planner.select_topics([c for c in cands if c["keyword"] not in used_kw], used, n)
    by_kw = {c["keyword"]: c for c in cands}
    results = []
    for p in sel.get("picks", []):
        if sum(r["status"] in ("ready", "needs_review") for r in results) >= n: break
        it = by_kw.get(p["keyword"])
        if not it or p["keyword"] in used_kw: continue
        progress(f"제작 중: {p['keyword']} ({len(results) + 1}/{n})")
        results.append(make_short(it))
    return {"selected": sel, "results": results}


def _cleanup(days=3):
    """Delete downloaded footage/intermediates of old jobs (keeps logs + plan/result json)."""
    cut = time.time() - days * 86400
    for j in config.JOBS.glob("*"):
        if j.is_dir() and j.stat().st_mtime < cut:
            for sub in ("src", "seg"):
                shutil.rmtree(j / sub, ignore_errors=True)
            for f in j.glob("*.mp4"): f.unlink(missing_ok=True)
            for f in j.glob("*.mp3"): f.unlink(missing_ok=True)


def daemon(every_h=4.0):
    from . import settings
    while True:
        t0 = time.time()
        try:
            settings.apply()
            r = run_once()
            print(json.dumps([{k: x.get(k) for k in ("keyword", "status", "note", "out")} for x in r["results"]], ensure_ascii=False, indent=1))
        except Exception:
            traceback.print_exc()
        time.sleep(max(60, every_h * 3600 - (time.time() - t0)))
