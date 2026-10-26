"""Admin page: API keys, scheduler on/off + interval, results review, logs.
Run: python -m autoshorts.web   (ADMIN_PASSWORD must be set; listens on 0.0.0.0:8080 by default)"""
import json, os, secrets, shutil, subprocess, threading
from functools import wraps
from pathlib import Path
from flask import Flask, request, redirect, session, send_file, abort, render_template_string, url_for
from . import config, settings, scheduler, trends

app = Flask(__name__)
_sk = config.STATE / "flask_secret"
config.STATE.mkdir(parents=True, exist_ok=True)
if not _sk.exists(): _sk.write_text(secrets.token_hex(32)); os.chmod(_sk, 0o600)
app.secret_key = _sk.read_text()
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

BASE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auto Shorts 관리자</title><style>
:root{--bg:#0f1115;--card:#181b22;--line:#2a2f3a;--txt:#e8eaf0;--mut:#9aa1b1;--acc:#ffd600;--red:#e11e2d;--grn:#2fbf71}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
a{color:var(--acc);text-decoration:none}header{display:flex;gap:18px;align-items:center;padding:14px 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}
header b{font-size:18px}main{max-width:1200px;margin:0 auto;padding:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
button,.btn{background:#2a2f3a;color:var(--txt);border:0;border-radius:9px;padding:9px 14px;font-weight:700;cursor:pointer}
.btn-acc{background:var(--acc);color:#111}.btn-red{background:var(--red)}.btn-grn{background:var(--grn);color:#071}
input,select{background:#0c0e12;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:120px}
label{display:block;color:var(--mut);font-size:13px;margin:10px 0 4px}.mut{color:var(--mut)}.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700}
.on{background:var(--grn);color:#062}.off{background:#3a3f4a}.ready{background:var(--grn);color:#052}.needs_review{background:#d98b00;color:#000}.rejected{background:#555}.approved{background:#3b82f6}
.item img{width:100%;border-radius:10px;aspect-ratio:9/16;object-fit:cover;background:#000}pre{white-space:pre-wrap;background:#0c0e12;padding:12px;border-radius:8px;max-height:480px;overflow:auto;font-size:12px}
table{width:100%;border-collapse:collapse}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}
</style></head><body><header><b>Auto Shorts</b><a href="/">대시보드</a><a href="/results">결과물</a><a href="/settings">설정</a><a href="/logs">로그</a><a href="/trends">트렌드</a><span style="flex:1"></span><a href="/logout" class="mut">로그아웃</a></header><main>{{ body|safe }}</main></body></html>"""


def page(body, **kw):
    return render_template_string(BASE, body=render_template_string(body, **kw))


def auth(fn):
    @wraps(fn)
    def w(*a, **k):
        if not session.get("ok"): return redirect("/login")
        return fn(*a, **k)
    return w


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        if PASSWORD and secrets.compare_digest(request.form.get("pw", ""), PASSWORD):
            session["ok"] = True; return redirect("/")
        err = "비밀번호가 틀렸습니다" if PASSWORD else "서버에 ADMIN_PASSWORD가 설정되지 않았습니다"
    return render_template_string(BASE, body=f"""<div class="card" style="max-width:360px;margin:60px auto"><h3>관리자 로그인</h3>
    <form method="post"><input type="password" name="pw" placeholder="비밀번호" style="width:100%"><p></p><button class="btn-acc" style="width:100%">로그인</button></form>
    <p class="mut">{err}</p></div>""")


@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")


def _items():
    out = []
    for st in ("ready", "needs_review", "approved", "rejected"):
        for d in sorted((config.OUTPUT / st).glob("*"), reverse=True) if (config.OUTPUT / st).exists() else []:
            m = d / "meta.json"
            if m.exists():
                j = json.loads(m.read_text()); j["dir"] = d.name; j["bucket"] = st; out.append(j)
    out.sort(key=lambda j: j.get("created", ""), reverse=True)
    return out


@app.route("/")
@auth
def dash():
    st = scheduler.status(); s = settings.load(); settings.apply(s); eff = config.LLM_BACKEND
    keys_ok = bool(s.get("elevenlabs_api_key") or config.ELEVENLABS_API_KEY)
    llm_ok = s["llm_backend"] == "cli" or bool(s.get("anthropic_api_key") or config.ANTHROPIC_API_KEY) or bool(shutil.which("claude"))
    return page("""
<div class="card"><div class="row"><h3 style="margin:0">자동 제작</h3>
 {% if st.enabled %}<span class="pill on">켜짐</span>{% else %}<span class="pill off">꺼짐</span>{% endif %}
 {% if st.running %}<span class="pill needs_review">제작 중 · {{ st.current }}</span>{% endif %}</div>
 <p class="mut">Claude 실행 방식: <b>{{ '서버의 Claude Code (claude -p)' if eff=='cli' else 'Anthropic API 키' }}</b>{{ ' — API 키가 없어 Claude Code로 자동 전환됨' if eff=='cli' and s.llm_backend=='api' }}</p>
 <p class="mut">주기 {{ st.interval_h }}시간 · 1회 {{ s.topics_per_run }}개 · 다음 실행: {{ st.next_run or '-' }} · 마지막 실행: {{ st.last_start or '-' }}</p>
 {% if not keys_ok or not llm_ok %}<p style="color:#ff8a8a">⚠ 설정에서 {{ '' if keys_ok else 'ElevenLabs 키 ' }}{{ '' if llm_ok else 'Claude 키' }}를 먼저 입력하세요.</p>{% endif %}
 <div class="row">
  <form method="post" action="/control"><input type="hidden" name="a" value="{{ 'stop' if st.enabled else 'start' }}">
   <button class="{{ 'btn-red' if st.enabled else 'btn-grn' }}">{{ '정지' if st.enabled else '시작' }}</button></form>
  <form method="post" action="/control"><input type="hidden" name="a" value="now"><button class="btn-acc" {{ 'disabled' if st.running }}>지금 1회 실행</button></form>
  <form method="post" action="/control" class="row"><input type="hidden" name="a" value="interval">
   <input type="number" step="0.5" min="0.5" name="h" value="{{ st.interval_h }}" style="width:90px">시간마다 <input type="number" min="1" max="5" name="n" value="{{ s.topics_per_run }}" style="width:70px">개 <button>저장</button></form>
 </div>
 <form method="post" action="/make" class="row" style="margin-top:12px"><input name="kw" placeholder="키워드로 직접 1개 만들기" style="flex:1"><button>만들기</button></form>
 {% if st.last_error %}<pre>{{ st.last_error }}</pre>{% endif %}
</div>
<div class="card"><h3>최근 결과</h3><div class="grid">
{% for it in items[:8] %}<div class="item"><a href="/item/{{ it.bucket }}/{{ it.dir }}"><img src="/media/{{ it.bucket }}/{{ it.dir }}/thumb.png"></a>
 <span class="pill {{ it.bucket }}">{{ it.bucket }}</span> <b>{{ it.title }}</b><div class="mut">{{ it.keyword }} · {{ it.created[:16] }}</div></div>{% endfor %}
</div></div>""", st=st, s=s, items=_items(), keys_ok=keys_ok, llm_ok=llm_ok, eff=eff)


@app.route("/control", methods=["POST"])
@auth
def control():
    a = request.form.get("a")
    if a == "start": scheduler.set_enabled(True)
    elif a == "stop": scheduler.set_enabled(False)
    elif a == "now": scheduler.run_now()
    elif a == "interval":
        scheduler.set_interval(request.form.get("h", 4))
        s = settings.load(); s["topics_per_run"] = max(1, min(5, int(request.form.get("n", 2)))); settings.save(s)
    return redirect("/")


@app.route("/make", methods=["POST"])
@auth
def make():
    kw = request.form.get("kw", "").strip()
    if kw:
        def job():
            from . import pipeline
            settings.apply()
            cands = {c["keyword"]: c for c in trends.candidates()}
            pipeline.make_short(cands.get(kw) or {"keyword": kw, "traffic": 0, "score": 0, "news": []})
        threading.Thread(target=job, daemon=True).start()
    return redirect("/logs")


@app.route("/results")
@auth
def results():
    return page("""<div class="card"><h3>결과물</h3><p class="mut">ready = 자동검수 통과 · needs_review = 사람 확인 필요 · approved = 업로드 대기(2단계에서 자동 업로드)</p><div class="grid">
{% for it in items %}<div class="item"><a href="/item/{{ it.bucket }}/{{ it.dir }}"><img src="/media/{{ it.bucket }}/{{ it.dir }}/thumb.png"></a>
 <span class="pill {{ it.bucket }}">{{ it.bucket }}</span> <b>{{ it.title }}</b><div class="mut">{{ it.keyword }} · {{ it.created[:16] }} · 위험도 {{ it.risk }}</div></div>{% endfor %}
</div></div>""", items=_items())


@app.route("/item/<bucket>/<name>")
@auth
def item(bucket, name):
    d = config.OUTPUT / bucket / name
    if not (d / "meta.json").exists(): abort(404)
    j = json.loads((d / "meta.json").read_text())
    return page("""<div class="card"><div class="row" style="align-items:flex-start">
<video src="/media/{{ b }}/{{ n }}/short.mp4" controls style="width:320px;border-radius:12px"></video>
<div style="flex:1;min-width:280px"><span class="pill {{ b }}">{{ b }}</span><h3>{{ j.title }}</h3>
<p class="mut">키워드 {{ j.keyword }} · 위험도 {{ j.risk }} — {{ j.risk_notes }}</p>
{% if j.note %}<p><b>자동검수 메모</b><br><span class="mut">{{ j.note }}</span></p>{% endif %}
<label>제목 후보</label><ul>{% for t in j.titles %}<li>{{ t }}</li>{% endfor %}</ul>
<label>설명</label><pre>{{ j.description }}</pre><label>태그</label><div class="mut">{{ ', '.join(j.tags) }}</div>
<div class="row" style="margin-top:14px">
<form method="post" action="/item/{{ b }}/{{ n }}/move"><input type="hidden" name="to" value="approved"><button class="btn-grn">승인(업로드 대기열)</button></form>
<form method="post" action="/item/{{ b }}/{{ n }}/move"><input type="hidden" name="to" value="rejected"><button class="btn-red">반려</button></form>
<a class="btn" href="/media/{{ b }}/{{ n }}/short.mp4" download>mp4 다운로드</a><a class="btn" href="/media/{{ b }}/{{ n }}/thumb.png" download>썸네일</a></div>
</div></div></div>""", j=j, b=bucket, n=name)


@app.route("/item/<bucket>/<name>/move", methods=["POST"])
@auth
def move(bucket, name):
    to = request.form.get("to")
    if to not in ("approved", "rejected", "ready"): abort(400)
    src = config.OUTPUT / bucket / name
    if not src.exists(): abort(404)
    (config.OUTPUT / to).mkdir(parents=True, exist_ok=True)
    m = json.loads((src / "meta.json").read_text()); m["status"] = to; (src / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
    shutil.move(str(src), str(config.OUTPUT / to / name))
    return redirect(f"/item/{to}/{name}")


@app.route("/media/<bucket>/<name>/<fn>")
@auth
def media(bucket, name, fn):
    p = (config.OUTPUT / bucket / name / fn).resolve()
    if not str(p).startswith(str(config.OUTPUT.resolve())) or not p.exists(): abort(404)
    return send_file(p)


@app.route("/settings", methods=["GET", "POST"])
@auth
def settings_page():
    s = settings.load(); msg = ""
    if request.method == "POST":
        for k in ("llm_backend", "llm_model", "voice_id"):
            if request.form.get(k): s[k] = request.form[k].strip()
        for k in ("voice_speed",):
            if request.form.get(k): s[k] = float(request.form[k])
        if request.form.get("max_sources"): s["max_sources"] = int(request.form["max_sources"])
        bad = []
        for k in settings.SECRET:
            v = request.form.get(k, "").strip()
            if v == "-": s[k] = ""
            elif "…" in v or v == "(설정됨)": continue   # masked value shown in the field = unchanged
            elif v:
                ok = v.isascii() and " " not in v and 20 <= len(v) <= 300 and (v.startswith("sk_") if k == "elevenlabs_api_key" else v.startswith("sk-ant-"))
                if ok: s[k] = v
                else: bad.append("ElevenLabs" if k == "elevenlabs_api_key" else "Anthropic")
        settings.save(s)
        ck = request.files.get("cookies")
        if ck and ck.filename:
            ck.save(config.STATE / "youtube_cookies.txt"); os.chmod(config.STATE / "youtube_cookies.txt", 0o600)
        msg = "저장했습니다" if not bad else f"저장했습니다. 단, {', '.join(bad)} 키 형식이 올바르지 않아 저장하지 않았습니다 (ElevenLabs는 sk_ 로, Anthropic은 sk-ant- 로 시작해야 합니다)"
    cli = subprocess.run(["sh", "-c", "command -v claude && claude --version"], capture_output=True, text=True).stdout.strip()
    has_ck = (config.STATE / "youtube_cookies.txt").exists()
    return page("""<div class="card"><h3>설정</h3><p class="mut">{{ msg }}</p><form method="post" enctype="multipart/form-data">
<label>ElevenLabs API 키 {% if m.elevenlabs_api_key %}<span class="pill on">저장됨 ✓</span>{% else %}<span class="pill off">없음</span>{% endif %} — 바꿀 때만 새 키를 붙여넣으세요. '-' 입력 시 삭제</label>
<input name="elevenlabs_api_key" value="{{ m.elevenlabs_api_key }}" onfocus="if(this.value.indexOf('…')>=0)this.select()" style="width:100%;font-family:monospace">
<label>Claude 사용 방식</label><select name="llm_backend"><option value="api" {{ 'selected' if s.llm_backend=='api' }}>API 키 (Anthropic API, 권장)</option>
<option value="cli" {{ 'selected' if s.llm_backend=='cli' }}>서버의 Claude Code 로그인 사용 (claude -p)</option></select>
<p class="mut">API 키를 선택했는데 키가 비어 있으면 자동으로 Claude Code로 실행합니다.</p>
<p class="mut">Claude Code CLI: {{ cli or '설치 안 됨' }}</p>
<label>Anthropic API 키 {% if m.anthropic_api_key %}<span class="pill on">저장됨 ✓</span>{% else %}<span class="pill off">없음</span>{% endif %}</label>
<input name="anthropic_api_key" value="{{ m.anthropic_api_key }}" onfocus="if(this.value.indexOf('…')>=0)this.select()" style="width:100%;font-family:monospace">
<label>모델</label><input name="llm_model" value="{{ s.llm_model }}">
<label>ElevenLabs 보이스 ID / 속도</label><div class="row"><input name="voice_id" value="{{ s.voice_id }}"><input name="voice_speed" value="{{ s.voice_speed }}" style="width:80px"></div>
<label>주제당 다운로드할 자료영상 수</label><input name="max_sources" type="number" min="2" max="8" value="{{ s.max_sources }}">
<label>YouTube 쿠키 파일 (cookies.txt, 클라우드 IP 차단 회피용) — 현재 {{ '있음' if has_ck else '없음' }}</label><input type="file" name="cookies">
<p></p><button class="btn-acc">저장</button></form></div>""", s=s, m=settings.masked(s), msg=msg, cli=cli, has_ck=has_ck)


@app.route("/logs")
@auth
def logs():
    jobs = sorted(config.JOBS.glob("*"), reverse=True)[:30] if config.JOBS.exists() else []
    sel = request.args.get("j") or (jobs[0].name if jobs else None)
    txt = (config.JOBS / sel / "log.txt").read_text() if sel and (config.JOBS / sel / "log.txt").exists() else ""
    res = {}
    for j in jobs:
        r = j / "result.json"; res[j.name] = json.loads(r.read_text()).get("status") if r.exists() else "진행 중/중단"
    return page("""<div class="card"><h3>작업 로그</h3><div class="row" style="align-items:flex-start"><table style="max-width:420px">
{% for j in jobs %}<tr><td><a href="/logs?j={{ j.name }}">{{ j.name }}</a></td><td><span class="pill {{ res[j.name] }}">{{ res[j.name] }}</span></td></tr>{% endfor %}</table>
<pre style="flex:1;min-width:300px">{{ txt }}</pre></div></div>""", jobs=jobs, txt=txt, res=res)


@app.route("/trends")
@auth
def trends_page():
    c = trends.candidates()
    return page("""<div class="card"><h3>실시간 트렌드 (상승 점수순)</h3><table><tr><th>점수</th><th>검색량</th><th>경과</th><th>상승(최근/이전)</th><th>키워드</th><th>뉴스</th></tr>
{% for x in c %}<tr><td>{{ x.score }}</td><td>{{ x.traffic }}+</td><td>{{ x.age_h }}h</td><td>{{ x.curve.ratio if x.curve else '-' }}</td><td><b>{{ x.keyword }}</b></td><td class="mut">{{ x.news[0].title if x.news else '' }}</td></tr>{% endfor %}</table></div>""", c=c)


def main():
    if not PASSWORD:
        raise SystemExit("ADMIN_PASSWORD 환경변수를 설정하세요 (.env)")
    settings.apply()
    threading.Thread(target=scheduler.loop, daemon=True).start()
    app.run(host=os.environ.get("ADMIN_HOST", "0.0.0.0"), port=int(os.environ.get("ADMIN_PORT", "8080")), threaded=True)


if __name__ == "__main__":
    main()
