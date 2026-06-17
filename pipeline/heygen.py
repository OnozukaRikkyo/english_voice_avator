"""Stage narration→video: text → HeyGen avatar video (mp4)."""
import time
from pathlib import Path

import requests

from .config import (
    HEYGEN_API_KEY, HEYGEN_BASE_URL,
    HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID, HEYGEN_RATIO,
    stage_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["heygen"]

_HEADERS = lambda: {"X-Api-Key": HEYGEN_API_KEY, "Accept": "application/json"}


def upload_audio(mp3_path: Path) -> str:
    with open(mp3_path, "rb") as f:
        resp = requests.post(
            f"{HEYGEN_BASE_URL}/v1/asset",
            headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "audio/mp3"},
            data=f, timeout=120,
        )
    resp.raise_for_status()
    asset_id = resp.json()["data"]["id"]
    print(f"    uploaded audio asset: {asset_id}")
    return asset_id


def create_video(
    text: str,
    *,
    audio_asset_id: str | None = None,
    avatar_id: str = HEYGEN_AVATAR_ID,
    voice_id: str = HEYGEN_VOICE_ID,
    ratio: str = HEYGEN_RATIO,
    title: str = "avatar_video",
) -> str:
    voice_cfg = (
        {"type": "audio", "audio_asset_id": audio_asset_id}
        if audio_asset_id
        else {"type": "text", "voice_id": voice_id, "input_text": text}
    )
    payload = {
        "title": title,
        "video_inputs": [{
            "character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
            "voice": voice_cfg,
            "background": {"type": "color", "value": "#008000"},
        }],
        "aspect_ratio": ratio,
        "test": False,
    }
    resp = requests.post(
        f"{HEYGEN_BASE_URL}/v2/video/generate",
        headers={**_HEADERS(), "Content-Type": "application/json"},
        json=payload, timeout=60,
    )
    resp.raise_for_status()
    video_id = resp.json()["data"]["video_id"]
    print(f"    video_id: {video_id}")
    return video_id


def wait_for_video(video_id: str, poll_interval: int = 10, timeout: int = 1800) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(
            f"{HEYGEN_BASE_URL}/v1/video_status.get",
            headers=_HEADERS(), params={"video_id": video_id}, timeout=30,
        )
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
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    print(f"    → {output_path.name} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return output_path


def generate_video(text: str, output_path: Path, *, mp3_path: Path | None = None, title: str) -> Path:
    audio_asset_id = upload_audio(mp3_path) if mp3_path else None
    video_id = create_video(text, audio_asset_id=audio_asset_id, title=title)
    url = wait_for_video(video_id)
    return download_video(url, output_path)


def run(project: str) -> list[Path]:
    if not HEYGEN_API_KEY:
        print("  [skip] HEYGEN_API_KEY not set")
        return []

    src_dir = stage_dir(project, _IN)
    dst_dir = stage_dir(project, _OUT)
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for txt in sorted(src_dir.glob("*.txt")):
        out = dst_dir / (txt.stem + ".mp4")
        if out.exists():
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        text = txt.read_text(encoding="utf-8").strip()
        print(f"  Generating: {txt.name} ({len(text)} chars)")
        generate_video(text, out, title=txt.stem)
        results.append(out)

    return results


def run_all() -> None:
    for project in all_projects():
        print(f"\n[{project}] heygen")
        run(project)


if __name__ == "__main__":
    run_all()
