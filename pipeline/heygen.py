"""Stage narration→video: text → HeyGen avatar video (mp4).

HeyGen API v3（POST /v3/videos）を使う。v2 は 2026-10-31 で廃止される。
v3 で変わったところ:
  - payload が平坦になった（video_inputs[] の入れ子が無くなった）
  - 解像度が dimension {width,height} → resolution の列挙値（"4k"/"1080p"/"720p"）
  - engine を選べる。省略すると Avatar IV になり単価が 4 倍・4K 不可なので固定する
  - voice_settings が実際に効く（v2 は同じ値を送っても音声が変わらなかった）
  - 状態取得が /v1/video_status.get → GET /v3/videos/{id}
台本の <break> は v3 でも解釈される（読み上げられない）ことを実測で確認済み。
"""
import os
import re
import sys
import time
from pathlib import Path

import requests

from . import ssml
from .config import (
    HEYGEN_API_KEY, HEYGEN_BASE_URL, HEYGEN_MAX_CHARS,
    HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID, HEYGEN_RATIO,
    HEYGEN_RESOLUTION, HEYGEN_ENGINE,
    HEYGEN_VOICE_STABILITY, HEYGEN_VOICE_STYLE, HEYGEN_VOICE_SIMILARITY,
    stage_dir, parts_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["heygen"]

_HEADERS = lambda: {"X-Api-Key": HEYGEN_API_KEY, "Accept": "application/json"}


def upload_audio(mp3_path: Path) -> str:
    """自前の音声を上げて asset_id を得る（HeyGen の TTS を使わない経路）。"""
    with open(mp3_path, "rb") as f:
        resp = requests.post(
            f"{HEYGEN_BASE_URL}/v3/assets",
            headers={"X-Api-Key": HEYGEN_API_KEY},
            files={"file": (mp3_path.name, f, "audio/mpeg")}, timeout=120,
        )
    resp.raise_for_status()
    data = resp.json().get("data", resp.json())
    asset_id = data["asset_id"]
    print(f"    uploaded audio asset: {asset_id}")
    return asset_id


def create_video(
    text: str,
    *,
    audio_asset_id: str | None = None,
    avatar_id: str = HEYGEN_AVATAR_ID,
    voice_id: str = HEYGEN_VOICE_ID,
    ratio: str = HEYGEN_RATIO,
    resolution: str = HEYGEN_RESOLUTION,
    engine: str = HEYGEN_ENGINE,
    title: str = "avatar_video",
) -> str:
    # 音声を自前で渡すときは script/voice_id を送ってはならない（排他）。
    speech = (
        {"audio_asset_id": audio_asset_id}
        if audio_asset_id
        else {
            "script": text,
            "voice_id": voice_id,
            "voice_settings": {"engine_settings": {
                "engine_type": "elevenlabs",
                "stability": HEYGEN_VOICE_STABILITY,
                "style": HEYGEN_VOICE_STYLE,
                "similarity_boost": HEYGEN_VOICE_SIMILARITY,
                "use_speaker_boost": True,
            }},
        }
    )
    payload = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "title": title,
        "resolution": resolution,
        "aspect_ratio": ratio,
        "engine": {"type": engine},
        **speech,
    }
    resp = requests.post(
        f"{HEYGEN_BASE_URL}/v3/videos",
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
            f"{HEYGEN_BASE_URL}/v3/videos/{video_id}",
            headers=_HEADERS(), timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data.get("status", "")
        print(f"    status: {status}")
        if status == "completed":
            return data["video_url"]
        if status == "failed":
            raise RuntimeError(
                f"HeyGen video failed: {data.get('failure_code')} — {data.get('failure_message')}")
        time.sleep(poll_interval)
    raise TimeoutError(f"HeyGen video {video_id} did not complete within {timeout}s")


# 台本の末尾が <break time="Xs"/> で終わっていれば、その秒数だけ無音で終わるはず。
_TAIL_BREAK = re.compile(r'<break\s+time\s*=\s*"([\d.]+)s"\s*/>\s*(?:</speak>)?\s*$', re.I)

# 実測した無音が指定の何割を下回ったら異常とみなすか。
# 実測（同一実行の6本、2026-08-19）: 1.0s 指定 → 0.98〜1.07秒、1.5s 指定 → 1.35〜1.81秒。
# 正常なものは指定の 0.9 倍を下回らない。壊れた1本は 0.1秒未満だった。
# 判定を 0.5 に置けば、正常を弾かず壊れたものだけを捕まえられる。
_TAIL_TOLERANCE = 0.5


def _expected_tail_silence(script: str) -> float:
    """台本が末尾に要求している無音の秒数（指定が無ければ 0.0）。"""
    m = _TAIL_BREAK.search(script.strip())
    return float(m.group(1)) if m else 0.0


def _duration(path: Path) -> float:
    import subprocess
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True).stdout or 0)


_FRAME = 0.02          # 音量を測る刻み（秒）
_FLOOR = 300           # これ以下の RMS を無音とみなす（16bit, 約 -41dBFS）


def _tail_frames(path: Path, window: float) -> tuple[list[bool], float]:
    """末尾 window 秒を 20ms ごとに「音があるか」で並べて返す。

    ffmpeg の silencedetect の出力を読むのはやめた。音声ストリームが映像より
    わずかに短い（実測 0.11秒）ファイルでは、末尾まで続く無音なのか途中で
    終わった無音なのかを、ログの秒数だけでは区別できなかったためである。
    生の波形を見れば、その曖昧さは無い。
    """
    import array
    import subprocess
    window = min(window, _duration(path))
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-sseof", f"-{window}", "-i", str(path),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True).stdout
    samples = array.array("h")
    samples.frombytes(pcm[:len(pcm) // 2 * 2])
    step = int(16000 * _FRAME)
    loud = []
    for i in range(0, len(samples), step):
        block = samples[i:i + step]
        if not block:
            break
        rms = (sum(v * v for v in block) / len(block)) ** 0.5
        loud.append(rms > _FLOOR)
    return loud, window


def _measured_tail_silence(path: Path, window: float = 12.0) -> float:
    """動画の末尾が何秒無音で終わっているかを測る。"""
    loud, window = _tail_frames(path, window)
    if not any(loud):
        return window
    last = len(loud) - 1 - loud[::-1].index(True)
    return window - (last + 1) * _FRAME


def _expected_vs_measured(path: Path, script: str) -> tuple[float, float]:
    return _expected_tail_silence(script), _measured_tail_silence(path)


def _tail_problem(path: Path, script: str) -> str | None:
    """台本が無音を要求している末尾に音が残っていれば、その説明を返す。

    合成音声が末尾の間を無音ではなく喋り声で埋めることがある（実例: 1.5秒の
    指定に対し、台本に無い音が 1.2秒続いた）。台本と映像だけを見ても分からず、
    公開して初めて気づく類の壊れ方なので、生成の直後にここで測る。
    """
    want = _expected_tail_silence(script)
    if not want:
        return None
    got = _measured_tail_silence(path)
    if got >= want * _TAIL_TOLERANCE:
        return None
    return f"末尾の無音が {got:.2f}秒しかありません（台本の指定は {want:.1f}秒）"


def _audio_params(path: Path) -> dict:
    """結合し直せるよう、元の音声と同じ設定で書き戻すための値を読む。"""
    import subprocess
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=sample_rate,channels,bit_rate", "-of", "default=nw=1:nk=0", str(path)],
        capture_output=True, text=True).stdout
    got = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    return {
        "ar": got.get("sample_rate", "48000"),
        "ac": got.get("channels", "2"),
        "b:a": got.get("bit_rate") if (got.get("bit_rate") or "").isdigit() else "130000",
    }


def _last_gap_before_end(path: Path, window: float) -> float | None:
    """末尾 window 秒の中で、最後に音が途切れた位置（終端からの秒数）を返す。

    幻聴は台本の最後の一文が終わったあとに始まる。その境目には必ず短い無音が
    ある（実例では 0.1秒）。そこを消音の開始点にすれば、本物の発話は削らない。
    途切れが1つも無ければ、末尾まで喋り続けている＝台本にある文を読んでいる
    可能性があるので、消さずに None を返して人に委ねる。
    """
    loud, window = _tail_frames(path, window)
    if not any(loud):
        return window
    last = len(loud) - 1 - loud[::-1].index(True)      # 最後に音があった位置
    gap_end = None
    for i in range(last, 0, -1):                       # そこから遡って直近の無音を探す
        if not loud[i - 1]:
            gap_end = i
            break
    if gap_end is None:
        return None
    gap_start = gap_end
    while gap_start > 0 and not loud[gap_start - 1]:
        gap_start -= 1
    if (gap_end - gap_start) * _FRAME < 0.08:          # 短すぎる途切れは語中の閉鎖音
        return None
    return window - gap_start * _FRAME


def repair_tail(path: Path, script: str) -> str | None:
    """末尾の「無音であるべき区間」に残った音を消す。直したら説明、不要なら None。

    映像は触らず（`-c:v copy`）、音声だけを書き戻す。作り直しは1本あたり数ドル
    かかるうえ、確率的な事故なので直る保証もない。台本が無音を指定している
    区間を無音にするだけなら、費用ゼロで確実に台本どおりになる。
    """
    import subprocess
    problem = _tail_problem(path, script)
    if problem is None:
        return None

    want = _expected_tail_silence(script)
    from_end = _last_gap_before_end(path, want + 1.0)
    if from_end is None:
        raise RuntimeError(
            f"{problem}。末尾 {want + 1.0:.1f}秒に音の途切れが無く、"
            "どこからが台本外の音か決められません（手で確認してください）")

    at = _duration(path) - from_end
    par = _audio_params(path)
    tmp = path.with_suffix(".repair.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-c:v", "copy", "-c:a", "aac",
         "-b:a", par["b:a"], "-ar", par["ar"], "-ac", par["ac"],
         "-af", f"volume=0:enable='gte(t,{at:.3f})'", str(tmp)],
        check=True, capture_output=True)

    still = _tail_problem(tmp, script)
    if still:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{problem}。消音しても直りませんでした（{still}）")
    tmp.replace(path)
    return f"{problem} → 終端 {from_end:.2f}秒を消音しました"


def _ensure_tail(path: Path, script: str) -> None:
    """末尾に台本外の音が残っていれば消す。生成した回だけでなく毎回通す。

    検査は 1本 0.12秒で終わる（末尾だけを復号するため、4K で 150MB あっても
    変わらない）。生成の分単位に対して無視できる。作り直しが中断した回の
    パートや、検査を入れる前に作ったパートを見落とさないほうが価値が大きい。
    """
    try:
        fixed = repair_tail(path, script)
        if fixed:
            print(f"  [repair] {path.name}: {fixed}")
    except RuntimeError as e:
        print(f"  WARNING: {path.name}: {e}", file=sys.stderr)


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

    後処理は無い。v3 は caption を送らなければ画面に字幕が焼き込まれない
    （実機のフレームで確認済み。字幕は別ファイルで返るだけ）。
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
                    _ensure_tail(out, piece)
                    results.append(out)
                    continue
            if out.exists() and force:
                out.unlink()

            print(f"  Generating: {out.stem} ({len(piece)} chars)")
            generate_video(piece, out, title=out.stem)

            # 末尾の間を合成音声が喋り声で埋めることがある。台本が無音を指定して
            # いる区間なので、作り直さずその場で消音する（費用ゼロで台本どおり）。
            _ensure_tail(out, piece)
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
