"""Single entry point for Claude calls. Returns parsed JSON.

Two backends:
  api : Anthropic SDK (ANTHROPIC_API_KEY) - use this on the server.
  cli : `claude -p` headless (the Claude Code login on this machine) - handy for local testing.
"""
import base64, json, re, subprocess, time
from pathlib import Path
from . import config


def _extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def _api(prompt, images, max_tokens):
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    content = []
    for p in images:
        data = base64.b64encode(Path(p).read_bytes()).decode()
        mt = "image/png" if str(p).endswith(".png") else "image/jpeg"
        content.append({"type": "text", "text": f"[image: {Path(p).name}]"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(model=config.LLM_MODEL, max_tokens=max_tokens,
                                 messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _cli(prompt, images, cwd):
    if images:
        prompt = ("먼저 Read 도구로 다음 이미지들을 모두 열어서 본 뒤 답하세요:\n" +
                  "\n".join(str(Path(p).resolve()) for p in images) + "\n\n" + prompt)
    cmd = ["claude", "-p", "--output-format", "json", "--allowedTools", "Read", "--model", config.LLM_MODEL, prompt]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"claude cli failed: {r.stderr[-500:]}")
    return json.loads(r.stdout)["result"]


def ask_json(prompt, images=(), max_tokens=8000, cwd=None, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            text = _api(prompt, images, max_tokens) if config.LLM_BACKEND == "api" else _cli(prompt, images, cwd)
            return _extract_json(text)
        except Exception as e:   # bad JSON / transient API error -> retry
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"LLM call failed: {last}")
