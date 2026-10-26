"""Runtime settings edited from the admin page (state/settings.json, chmod 600). They override env/.env values."""
import json, os
from . import config

FILE = config.STATE / "settings.json"
DEFAULTS = {
    "enabled": False,            # scheduler on/off
    "interval_h": 4.0,           # hours between cycles
    "topics_per_run": 2,
    "llm_backend": config.LLM_BACKEND,   # api | cli
    "llm_model": config.LLM_MODEL,
    "voice_id": config.VOICE_ID,
    "voice_speed": config.VOICE_SPEED,
    "elevenlabs_api_key": "",
    "anthropic_api_key": "",
    "max_sources": config.MAX_SOURCES,
}
SECRET = ("elevenlabs_api_key", "anthropic_api_key")


def load():
    s = dict(DEFAULTS)
    if FILE.exists():
        s.update(json.loads(FILE.read_text()))
    return s


def save(s):
    config.STATE.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1))
    os.chmod(FILE, 0o600)


def apply(s=None):
    """Push settings into the config module before a run."""
    s = s or load()
    if s.get("elevenlabs_api_key"): config.ELEVENLABS_API_KEY = s["elevenlabs_api_key"]
    if s.get("anthropic_api_key"): config.ANTHROPIC_API_KEY = s["anthropic_api_key"]
    config.LLM_BACKEND = s.get("llm_backend") or config.LLM_BACKEND
    if config.LLM_BACKEND == "api" and not config.ANTHROPIC_API_KEY:
        import shutil
        if shutil.which("claude"): config.LLM_BACKEND = "cli"   # no API key -> fall back to the local Claude Code login
    config.LLM_MODEL = s.get("llm_model") or config.LLM_MODEL
    config.VOICE_ID = s.get("voice_id") or config.VOICE_ID
    config.VOICE_SPEED = float(s.get("voice_speed") or config.VOICE_SPEED)
    config.TOPICS_PER_RUN = int(s.get("topics_per_run") or config.TOPICS_PER_RUN)
    config.MAX_SOURCES = int(s.get("max_sources") or config.MAX_SOURCES)
    return s


def masked(s):
    out = dict(s)
    for k in SECRET:
        v = out.get(k) or ""
        out[k] = (v[:6] + "…" + v[-4:]) if len(v) > 10 else ("(설정됨)" if v else "")
    return out
