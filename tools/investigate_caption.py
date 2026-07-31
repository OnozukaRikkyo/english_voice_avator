#!/usr/bin/env python3
"""Empirically investigate HeyGen caption behavior.

This script verifies facts from primary sources (actual API calls + video frame analysis),
not from web search interpretations.

Tests:
  1. Call HeyGen /v2/video/generate with different caption settings and log raw responses
  2. Extract a frame from an existing generated video and measure caption bar position

Output: data/caption_investigation/report.md

Usage:
  python tools/investigate_caption.py
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import HEYGEN_API_KEY, HEYGEN_BASE_URL, HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID

REPORT_DIR = Path(__file__).parent.parent / "data" / "caption_investigation"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT = REPORT_DIR / "report.md"

_TEST_TEXT = "This is a caption investigation test."


def _headers() -> dict:
    return {"X-Api-Key": HEYGEN_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}


# ── Test 1: API schema — what happens with different caption values ─────────

def test_api_caption_field() -> dict:
    """Send requests with different caption configurations. Record raw responses."""
    import requests

    results = {}
    cases = [
        ("no_caption_field",  {}),
        ("caption_false",     {"caption": False}),
        ("caption_true",      {"caption": True}),
        ("caption_obj_false", {"caption": {"type": "text", "enabled": False}}),
    ]

    base_payload = {
        "title": "caption_test_DO_NOT_USE",
        "video_inputs": [{
            "character": {"type": "avatar", "avatar_id": HEYGEN_AVATAR_ID, "avatar_style": "normal"},
            "voice": {"type": "text", "voice_id": HEYGEN_VOICE_ID, "input_text": _TEST_TEXT},
            "background": {"type": "color", "value": "#008000"},
        }],
        "aspect_ratio": "16:9",
        "test": True,  # use test mode to avoid credits
    }

    print("\n[Test 1] API caption field behavior")
    for name, extra in cases:
        payload = {**base_payload, **extra}
        resp = requests.post(
            f"{HEYGEN_BASE_URL}/v2/video/generate",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        result = {
            "status_code": resp.status_code,
            "response": resp.json(),
        }
        results[name] = result
        print(f"  {name}: HTTP {resp.status_code} → {json.dumps(resp.json())[:200]}")

    return results


# ── Test 2: Frame extraction — measure caption bar pixel position ──────────

def test_frame_caption_position() -> dict:
    """Extract a frame from an existing video and find where caption bar starts."""
    import requests

    data_dir = Path(__file__).parent.parent / "data"
    mp4_files = sorted(data_dir.rglob("video/parts/*.mp4"))
    if not mp4_files:
        mp4_files = sorted(data_dir.rglob("*.mp4"))
    if not mp4_files:
        return {"error": "No MP4 files found"}

    video = mp4_files[0]
    print(f"\n[Test 2] Analyzing frame from: {video.name}")

    # Extract frame at 5 seconds
    frame_path = REPORT_DIR / "frame_sample.png"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-ss", "5", "-vframes", "1", str(frame_path)],
        capture_output=True,
    )
    if r.returncode != 0:
        return {"error": f"ffmpeg failed: {r.stderr.decode()[-300:]}"}

    # Measure using Python PIL
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(frame_path).convert("RGB")
        arr = np.array(img)
        h, w = arr.shape[:2]

        # Background color #008000 = (0, 128, 0)
        bg = np.array([0, 128, 0])

        # Scan rows from bottom upward; find first row that differs significantly from bg
        # "differs" = mean abs diff > 20 across enough pixels (>5% of width)
        caption_start_y = None
        caption_end_y = h  # bottom of frame

        for y in range(h - 1, h // 2, -1):
            row = arr[y]
            diff = np.abs(row.astype(int) - bg).mean(axis=1)
            non_bg_ratio = (diff > 30).mean()
            if non_bg_ratio > 0.05:
                caption_end_y = y
                break

        for y in range(caption_end_y - 1, h // 2, -1):
            row = arr[y]
            diff = np.abs(row.astype(int) - bg).mean(axis=1)
            non_bg_ratio = (diff > 30).mean()
            if non_bg_ratio < 0.02:
                caption_start_y = y
                break

        result = {
            "video": str(video.name),
            "frame": str(frame_path),
            "width": w,
            "height": h,
            "caption_start_y": caption_start_y,
            "caption_end_y": caption_end_y,
            "caption_height_px": (caption_end_y - caption_start_y) if caption_start_y else None,
            "caption_height_pct": round((caption_end_y - caption_start_y) / h * 100, 1) if caption_start_y else None,
        }
        print(f"  Frame: {w}x{h}")
        if caption_start_y:
            print(f"  Caption bar: y={caption_start_y}–{caption_end_y} ({result['caption_height_px']}px, {result['caption_height_pct']}%)")
        else:
            print("  Caption bar: not detected (no non-background region found)")
        return result

    except ImportError:
        return {"error": "PIL/numpy not installed — run: .venv/bin/pip install pillow numpy"}


# ── Write report ───────────────────────────────────────────────────────────

def write_report(api_results: dict, frame_results: dict) -> None:
    lines = [
        f"# HeyGen Caption Investigation Report",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "## Test 1: API caption field behavior",
        "",
        "| Variant | HTTP | Response summary |",
        "|---------|------|------------------|",
    ]
    for name, r in api_results.items():
        summary = json.dumps(r["response"])[:120].replace("|", "\\|")
        lines.append(f"| `{name}` | {r['status_code']} | {summary} |")

    lines += [
        "",
        "## Test 2: Caption bar pixel position",
        "",
    ]
    if "error" in frame_results:
        lines.append(f"Error: {frame_results['error']}")
    else:
        fr = frame_results
        lines += [
            f"- Video analyzed: `{fr.get('video')}`",
            f"- Frame size: {fr.get('width')}×{fr.get('height')}",
            f"- Caption bar y start: {fr.get('caption_start_y')} px",
            f"- Caption bar y end: {fr.get('caption_end_y')} px",
            f"- Caption bar height: {fr.get('caption_height_px')} px ({fr.get('caption_height_pct')}%)",
            "",
            "### Recommended ffmpeg drawbox filter",
        ]
        if fr.get("caption_start_y"):
            y = fr["caption_start_y"]
            height = fr["caption_height_px"]
            lines.append(
                f'`drawbox=x=0:y={y}:w=iw:h={height}:color=0x008000:t=fill`'
            )
            lines.append(f"(or as ratio: `drawbox=x=0:y=ih*{round(y/fr['height'], 3)}:w=iw:h={round(height/fr['height'], 3)*1}*ih:color=0x008000:t=fill`)")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n→ Report written: {REPORT}")


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not HEYGEN_API_KEY:
        print("ERROR: HEYGEN_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    api_results = test_api_caption_field()
    frame_results = test_frame_caption_position()
    write_report(api_results, frame_results)
    print("\nDone. Review the report, then update pipeline/heygen.py accordingly.")
