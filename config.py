"""Settings for the AI MC, read from .env (same keys as the MBRGEA-Nominies orb)."""

import os
import sys
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

FROZEN = getattr(sys, "frozen", False)
# ROOT holds data/ and an optional .env: the source folder, or the folder of the exe.
# ASSETS holds web/: the same folder, or PyInstaller's unpack dir when frozen.
ROOT = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
ASSETS = getattr(sys, "_MEIPASS", ROOT)

# A .env here wins; the orb project's .env is the fallback so the same Azure
# keys work without copying them. load_dotenv never overrides a set variable.
load_dotenv(os.path.join(ROOT, ".env"))
load_dotenv(os.getenv("FALLBACK_ENV", os.path.join(
    ROOT, "..", "MBRGEA-nominies", "python", "MBRGEA-Nominies", ".env")))

# Last resort: the .env values build.py baked into the exe.
try:
    from _embedded_env import VALUES as _EMBEDDED
except ImportError:
    _EMBEDDED = {}
for _k, _v in _EMBEDDED.items():
    os.environ.setdefault(_k, _v)

# Windows consoles default to cp1252, which cannot print Arabic.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def env(*names: str, default: str = "") -> str:
    """First non-empty match. Accepts the usual spellings of each setting."""
    for n in names:
        v = os.getenv(n)
        if v:
            return v.strip().strip('"').strip("'")
    return default


def _url(value: str):
    return urlparse(value if "//" in value else "https://" + value)


_RAW_ENDPOINT = env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_BASE_URL",
                    "AZURE_ENDPOINT", "OPENAI_ENDPOINT", "ENDPOINT")
_p = _url(_RAW_ENDPOINT) if _RAW_ENDPOINT else None
ENDPOINT = f"{_p.scheme}://{_p.netloc}" if _p and _p.netloc else _RAW_ENDPOINT.rstrip("/")
API_KEY = env("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_KEY",
              "AZURE_API_KEY", "OPENAI_API_KEY", "API_KEY", "KEY")
# NOTE: the deployment *name*, not the model name.
DEPLOYMENT = env("AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME",
                 "AZURE_DEPLOYMENT", "DEPLOYMENT_NAME", "DEPLOYMENT",
                 default=(parse_qs(_p.query).get("model", [""])[0] if _p else "")
                 or "gpt-realtime-2.1")
HTTP_BASE = f"{ENDPOINT}/openai/v1"
WS_BASE = HTTP_BASE.replace("https://", "wss://", 1).replace("http://", "ws://", 1)

# Realtime voices and the gender each one sounds (male only, as on the nominees orb).
VOICES = {
    "ash": "male", "cedar": "male", "echo": "male", "verse": "male", "ballad": "male",
}
VOICE_SPEED = 1.125      # default; the admin panel can change it. The realtime API allows 0.25-1.5
VOICE_STYLES = {
    "natural": "Speak like a normal, cheerful person in a real conversation: relaxed and "
               "joyful, upbeat, with a smile in the voice, friendly and polite, never stiff, "
               "not like a presenter or an announcer.",
    "formal": "Speak like a formal news presenter: clear, measured, steady pace, "
              "confident and authoritative.",
    "warm": "Speak like a warm, friendly event host: gentle, welcoming, a soft smile "
            "in the voice, relaxed pace.",
    "ceremony": "Speak like a grand award-ceremony announcer: rich, celebratory, "
                "dramatic pauses before names, building excitement.",
}
SAMPLE_RATE = 24000      # realtime API returns 24 kHz mono PCM16

HOST = env("MC_HOST", default="0.0.0.0")
PORT = int(env("MC_PORT", default="8090"))
DATA_DIR = os.path.join(ROOT, "data")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
