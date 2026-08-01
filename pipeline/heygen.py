"""Stage narration→video: text → HeyGen avatar video (mp4)."""
import os
import time
from pathlib import Path

import requests

from . import ssml
from .config import (
    HEYGEN_API_KEY, HEYGEN_BASE_URL, HEYGEN_MAX_CHARS,
    HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID, HEYGEN_RATIO,
    stage_dir, parts_dir, all_projects, STEP_IO,
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
        "caption": False,
        "test": False,
    }
    resp = requests.post(
        f"{HEYGEN_BASE_URL}/v2/video/generate",
        headers={**_HEADERS(), "Content-Type": "application/json"},
        json=payload, timeout=60,
    )
    if not resp.ok:
        err = (resp.json().get("error") or {})
        raise RuntimeError(f"HeyGen {resp.status_code}: {err.get('code')} — {err.get('message')}")
    video_id = resp.json()["data"]["video_id"]
    print(f"    video_id: {video_id}")
    return video_id


def wait_for_video(video_id: str, poll_interval: int = 3, timeout: int = 1800) -> str:
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


def _validate_mp4(path: Path) -> bool:
    """Return True if the file is a valid MP4 (has moov atom)."""
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1", str(path)],
        capture_output=True,   # 検証のたびに ffprobe の出力を混ぜない
    )
    return result.returncode == 0


def download_raw(url: str, output_path: Path) -> Path:
    """Download the video as-is from HeyGen.

    後処理は無い。`caption: False` で画面字幕が出ないことを実機で確認済み
    （字幕を塗り潰す ffmpeg 処理を入れていたが、不要と分かったため削除した）。
    """
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"    → {output_path.name} ({size_mb:.1f} MB)")
    if not _validate_mp4(output_path):
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is not a valid MP4 (moov atom not found): {output_path.name}")
    return output_path


def generate_video(text: str, output_path: Path, *, mp3_path: Path | None = None, title: str) -> Path:
    audio_asset_id = upload_audio(mp3_path) if mp3_path else None
    video_id = create_video(text, audio_asset_id=audio_asset_id, title=title)
    url = wait_for_video(video_id)
    return download_raw(url, output_path)


def run(project: str, *, force: bool = False) -> list[Path]:
    if not HEYGEN_API_KEY:
        print("  [skip] HEYGEN_API_KEY not set")
        return []

    src_dir = parts_dir(project, _IN)   # ← reads from narration/parts/
    dst_dir = parts_dir(project, _OUT)  # ← writes to video/parts/
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    if not src_dir.exists() or not list(src_dir.glob("*.txt")):
        print(f"  [skip] no parts found in {src_dir.relative_to(src_dir.parent.parent.parent)}")
        return []

    debug = bool(os.environ.get("PIPELINE_DEBUG"))
    if debug:
        print("  [debug] PIPELINE_DEBUG: 1 newly generated part only")

    generated = 0
    for txt in sorted(src_dir.glob("*.txt")):
        text = txt.read_text(encoding="utf-8").strip()

        # HeyGen の入力上限は 5,000 字。台本パートはこれを超えることがあるので、
        # <break> の位置（話題の切れ目）で割ってから送る。
        pieces = ssml.split(text, HEYGEN_MAX_CHARS)
        if len(pieces) > 1:
            print(f"  {txt.name} は {len(text):,}字 > 上限 {HEYGEN_MAX_CHARS:,}字 → "
                  f"{len(pieces)} 本に分けて生成します")

        for n, piece in enumerate(pieces, 1):
            # 1本のときは従来どおりの名前、分けたときだけ枝番を付ける
            stem = txt.stem if len(pieces) == 1 else f"{txt.stem}_{n:02d}"
            out = dst_dir / (stem + ".mp4")

            if out.exists() and not force:
                if not _validate_mp4(out):
                    print(f"  [invalid] {out.name} — moov atom not found, regenerating")
                    out.unlink()
                else:
                    print(f"  [skip] {out.name}")
                    results.append(out)
                    continue
            if out.exists() and force:
                out.unlink()

            print(f"  Generating: {out.stem} ({len(piece)} chars)")
            generate_video(piece, out, title=out.stem)
            results.append(out)
            generated += 1
            if debug and generated >= 1:
                print("  [debug] stopping after 1 generated part")
                return results

    return results


def run_all() -> None:
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] heygen")
        run(project)


if __name__ == "__main__":
    run_all()
