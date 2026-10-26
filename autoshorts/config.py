"""Paths, keys and tunables. Everything can be overridden with environment variables (see .env.example)."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("AUTOSHORTS_ROOT", Path(__file__).resolve().parent.parent))
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
SFX = ASSETS / "sfx"
JOBS = Path(os.environ.get("AUTOSHORTS_JOBS", ROOT / "jobs"))
OUTPUT = Path(os.environ.get("AUTOSHORTS_OUTPUT", ROOT / "output"))
STATE = Path(os.environ.get("AUTOSHORTS_STATE", ROOT / "state"))


def _load_dotenv():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# "api" = Anthropic SDK (needs ANTHROPIC_API_KEY), "cli" = local `claude -p` (uses the logged-in Claude Code account)
LLM_BACKEND = os.environ.get("AUTOSHORTS_LLM", "api" if ANTHROPIC_API_KEY else "cli")
LLM_MODEL = os.environ.get("AUTOSHORTS_MODEL", "claude-opus-5-5")

VOICE_ID = os.environ.get("AUTOSHORTS_VOICE", "GLuWz93jOAhbFz7XKEDq")   # ElevenLabs voice used on the channel
VOICE_SPEED = float(os.environ.get("AUTOSHORTS_VOICE_SPEED", "1.2"))

TOPICS_PER_RUN = int(os.environ.get("AUTOSHORTS_TOPICS", "2"))
TOPIC_COOLDOWN_H = int(os.environ.get("AUTOSHORTS_COOLDOWN_H", "48"))   # don't redo a keyword within this window
MAX_SOURCES = int(os.environ.get("AUTOSHORTS_MAX_SOURCES", "5"))         # videos downloaded per topic
MAX_SOURCE_SEC = int(os.environ.get("AUTOSHORTS_MAX_SOURCE_SEC", "240")) # only the first N seconds of each video

YTDLP = os.environ.get("AUTOSHORTS_YTDLP", str(ROOT / ".venv/bin/yt-dlp"))
FFMPEG = os.environ.get("AUTOSHORTS_FFMPEG", "ffmpeg")
