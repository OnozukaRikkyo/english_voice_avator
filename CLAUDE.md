# english_voice/avator — Claude Code Project Guide

## Purpose
HeyGen avatar video production pipeline.
Input: podcast/news audio (m4a/mp4/mp3).
Output: avatar MP4 video narrating the content.

## Full Pipeline

```
data/input/          raw audio (m4a / mp4 / mp3)
    ↓ pipeline/audio_convert.py  (ffmpeg)
data/eng_mp3/        converted mp3
    ↓ pipeline/transcribe.py     (Gemini 2.5 Flash)
data/eng_text/       English transcript
    ↓ pipeline/rewrite.py        (Gemini 2.5 Pro — rewrite + split ≤4000 chars)
data/eng_split/      narration segments  (*_part01.txt, *_part02.txt, …)
    ↓ pipeline/tts.py            (MiniMax speech-2.8-hd, cloned voice)
data/regen_mp3/      per-segment mp3
    ↓ pipeline/concat.py         (moviepy)
data/voice_concat/   full-length mp3
data/concat_text/    full-length narration text
    ↓ pipeline/heygen.py         (HeyGen v2 API)
data/avatar_video/   final avatar mp4
```

## Run

```bash
# Full pipeline
python run_pipeline.py

# Specific steps only
python run_pipeline.py --steps convert,transcribe

# HeyGen text mode (no external audio)
python run_pipeline.py --steps heygen --heygen-mode text
```

Each step is **idempotent** — already-generated files are skipped.

## Modules

| File | Role |
|------|------|
| `pipeline/config.py` | Centralized paths, constants, API keys |
| `pipeline/audio_convert.py` | m4a/mp4 → mp3 via ffmpeg |
| `pipeline/transcribe.py` | mp3 → English text via Gemini |
| `pipeline/rewrite.py` | Dialogue → narration segments via Gemini |
| `pipeline/tts.py` | Text → mp3 via MiniMax (cloned voice) |
| `pipeline/concat.py` | Per-part mp3 + text → single files |
| `pipeline/heygen.py` | Avatar video generation via HeyGen API |
| `run_pipeline.py` | CLI orchestrator |

## Environment

Python 3.12 venv at `.venv/`. Required env vars in `.env`:

```
GEMINI_API_KEY      Google AI Studio
MINIMAX_API_KEY     MiniMax TTS API
HEYGEN_API_KEY      HeyGen API key (from app.heygen.com/settings → API)
HEYGEN_AVATAR_ID    Avatar ID (from HeyGen avatar library)
HEYGEN_VOICE_ID     HeyGen voice ID (used in text mode only)
```

## Key Constants (pipeline/config.py)

- `MINIMAX_VOICE_ID` — cloned voice ID for MiniMax TTS
- `REWRITE_MAX_CHARS = 4000` — max chars per narration segment
- `MINIMAX_MAX_CHARS = 5000` — max chars per TTS chunk
- `GEMINI_REWRITE_MODEL = "gemini-2.5-pro-preview-06-05"`
- `HEYGEN_RATIO = "16:9"`

## HeyGen Modes

- **audio** (default): Upload MiniMax MP3 → HeyGen lip-syncs avatar to it.
- **text**: Pass narration text → HeyGen generates voice + avatar.

## GitHub

Repository: `git@github.com:OnozukaRikkyo/english_voice_avator.git`
