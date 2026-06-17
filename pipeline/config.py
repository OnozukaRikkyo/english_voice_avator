"""Centralized configuration — paths, constants, and API clients."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── API keys ────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MINIMAX_API_KEY = os.environ["MINIMAX_API_KEY"]
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")

# ── MiniMax TTS ──────────────────────────────────────────────────────────────
MINIMAX_TTS_URL = "https://api.minimax.io/v1/t2a_v2"
MINIMAX_VOICE_ID = "moss_audio_10fc0153-4b51-11f1-8d50-22f63c968931"
MINIMAX_MODEL = "speech-2.8-hd"
MINIMAX_EMOTION = "calm"
MINIMAX_MAX_CHARS = 5000

# ── Gemini models ─────────────────────────────────────────────────────────────
GEMINI_TRANSCRIBE_MODEL = "gemini-2.5-flash"
GEMINI_REWRITE_MODEL = "gemini-2.5-pro-preview-06-05"
REWRITE_MAX_CHARS = 4000

# ── HeyGen ────────────────────────────────────────────────────────────────────
HEYGEN_BASE_URL = "https://api.heygen.com"
HEYGEN_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID", "")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID", "")  # used in text mode
HEYGEN_RATIO = "16:9"

# ── Data directories (relative to project root) ──────────────────────────────
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

DIR_INPUT = DATA / "input"
DIR_ENG_MP3 = DATA / "eng_mp3"
DIR_ENG_TEXT = DATA / "eng_text"
DIR_ENG_SPLIT = DATA / "eng_split"
DIR_REGEN_MP3 = DATA / "regen_mp3"
DIR_VOICE_CONCAT = DATA / "voice_concat"
DIR_CONCAT_TEXT = DATA / "concat_text"
DIR_AVATAR_VIDEO = DATA / "avatar_video"

ALL_DATA_DIRS = [
    DIR_INPUT, DIR_ENG_MP3, DIR_ENG_TEXT, DIR_ENG_SPLIT,
    DIR_REGEN_MP3, DIR_VOICE_CONCAT, DIR_CONCAT_TEXT, DIR_AVATAR_VIDEO,
]


def ensure_dirs() -> None:
    for d in ALL_DATA_DIRS:
        d.mkdir(parents=True, exist_ok=True)
