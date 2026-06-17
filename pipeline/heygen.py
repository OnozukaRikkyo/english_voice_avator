"""HeyGen avatar video generation.

Two modes:
  text  — pass narration text directly; HeyGen uses its own TTS voice.
  audio — upload an external MP3 (e.g., MiniMax clone) and lip-sync the avatar to it.

Typical workflow (audio mode):
  1. upload_audio(mp3_path)  → audio_asset_id
  2. create_video(text, audio_asset_id=...)  → video_id
  3. wait_for_video(video_id)  → download_url
  4. download_video(download_url, output_path)
"""
import time
from pathlib import Path

import requests

from .config import (
    HEYGEN_API_KEY, HEYGEN_BASE_URL,
    HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID, HEYGEN_RATIO,
    DIR_CONCAT_TEXT, DIR_REGEN_MP3, DIR_AVATAR_VIDEO,
)

_HEADERS = lambda: {
    "X-Api-Key": HEYGEN_API_KEY,
    "Accept": "application/json",
}


# ── Asset upload ──────────────────────────────────────────────────────────────

def upload_audio(mp3_path: Path) -> str:
    """Upload an MP3 file as a HeyGen asset. Returns asset_id."""
    url = f"{HEYGEN_BASE_URL}/v1/asset"
    with open(mp3_path, "rb") as f:
        resp = requests.post(
            url,
            headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "audio/mp3"},
            data=f,
            timeout=120,
        )
    resp.raise_for_status()
    data = resp.json()
    asset_id = data["data"]["id"]
    print(f"    uploaded audio asset: {asset_id}")
    return asset_id


# ── Video generation ──────────────────────────────────────────────────────────

def create_video(
    text: str,
    *,
    audio_asset_id: str | None = None,
    avatar_id: str = HEYGEN_AVATAR_ID,
    voice_id: str = HEYGEN_VOICE_ID,
    ratio: str = HEYGEN_RATIO,
    title: str = "avatar_video",
) -> str:
    """Submit a video generation job. Returns video_id."""
    if audio_asset_id:
        voice_cfg = {
            "type": "audio",
            "audio_asset_id": audio_asset_id,
        }
    else:
        voice_cfg = {
            "type": "text",
            "voice_id": voice_id,
            "input_text": text,
        }

    payload = {
        "title": title,
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": voice_cfg,
                "background": {
                    "type": "color",
                    "value": "#008000",
                },
            }
        ],
        "aspect_ratio": ratio,
        "test": False,
    }

    url = f"{HEYGEN_BASE_URL}/v2/video/generate"
    resp = requests.post(url, headers={**_HEADERS(), "Content-Type": "application/json"},
                         json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    video_id = data["data"]["video_id"]
    print(f"    video_id: {video_id}")
    return video_id


def wait_for_video(video_id: str, poll_interval: int = 10, timeout: int = 1800) -> str:
    """Poll until video is ready. Returns download URL."""
    url = f"{HEYGEN_BASE_URL}/v1/video_status.get"
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = requests.get(url, headers=_HEADERS(), params={"video_id": video_id}, timeout=30)
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data.get("status", "")
        print(f"    status: {status}")

        if status == "completed":
            return data["video_url"]
        if status == "failed":
            raise RuntimeError(f"HeyGen video failed: {data.get('error')}")

        time.sleep(poll_interval)

    raise TimeoutError(f"HeyGen video {video_id} did not complete within {timeout}s")


def download_video(url: str, output_path: Path) -> Path:
    """Download the completed MP4 to output_path."""
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    print(f"    → {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return output_path


# ── High-level helper ─────────────────────────────────────────────────────────

def generate_avatar_video(
    text: str,
    output_path: Path,
    mp3_path: Path | None = None,
    title: str = "avatar_video",
) -> Path:
    """
    End-to-end: (optional) upload audio → create video → poll → download.

    If mp3_path is provided, uses audio lip-sync mode.
    Otherwise uses text-to-speech mode with HEYGEN_VOICE_ID.
    """
    audio_asset_id = upload_audio(mp3_path) if mp3_path else None
    video_id = create_video(text, audio_asset_id=audio_asset_id, title=title)
    download_url = wait_for_video(video_id)
    return download_video(download_url, output_path)


# ── Module entry point ────────────────────────────────────────────────────────

def run(mode: str = "audio") -> list[Path]:
    """
    mode="audio"  — use concat MP3 (MiniMax voice) as avatar audio source.
    mode="text"   — pass concat text directly to HeyGen TTS.
    """
    if not HEYGEN_API_KEY:
        print("  [skip] HEYGEN_API_KEY not set")
        return []

    DIR_AVATAR_VIDEO.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    txt_files = sorted(DIR_CONCAT_TEXT.glob("*.txt"))
    if not txt_files:
        print("  No concat text files found.")
        return []

    for txt_path in txt_files:
        base = txt_path.stem.replace("_concat", "")
        out = DIR_AVATAR_VIDEO / f"{base}.mp4"
        if out.exists():
            print(f"  [skip] {out.name} already exists")
            results.append(out)
            continue

        text = txt_path.read_text(encoding="utf-8").strip()
        mp3_path: Path | None = None
        if mode == "audio":
            mp3_candidate = DIR_REGEN_MP3 / f"{base}_concat.mp3"
            if not mp3_candidate.exists():
                mp3_candidate = DIR_REGEN_MP3 / txt_path.stem.replace("_concat", "_concat") \
                    .replace("_concat", "") + "_concat.mp3" if False else mp3_candidate
            mp3_path = mp3_candidate if mp3_candidate.exists() else None
            if mp3_path is None:
                print(f"  [warn] no concat MP3 for {base}, falling back to text mode")

        print(f"  Generating avatar video: {base} (mode={mode if mp3_path else 'text'})")
        generate_avatar_video(text, out, mp3_path=mp3_path, title=base)
        results.append(out)

    return results


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "audio"
    run(mode=mode)
