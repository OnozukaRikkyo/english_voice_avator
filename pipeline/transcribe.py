"""Stage audio→transcript: mp3 → English text.

出力は ALWAYS 英語。音声が何語であっても英語になる。

プロバイダは config.TRANSCRIBE_MODEL のモデル名で決まる（gpt-* → OpenAI、
それ以外 → Gemini）。呼び分けは pipeline/llm.py が担当する。
"""
import os
from pathlib import Path

from . import llm
from .config import TRANSCRIBE_MODEL, stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["transcribe"]


def run(project: str, *, force: bool = False, model: str | None = None) -> list[Path]:
    """Run transcribe for a project.

    Args:
        force: 既存の出力を消して再実行する。
        model: config.TRANSCRIBE_MODEL を上書きする（gpt-* なら OpenAI 経路）。
    """
    active_model = model or TRANSCRIBE_MODEL
    src_dir = stage_dir(project, _IN)
    dst_dir = stage_dir(project, _OUT)
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for mp3 in sorted(src_dir.glob("*.mp3")):
        out = dst_dir / (mp3.stem + ".txt")
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        if out.exists() and force:
            out.unlink()

        print(f"  Transcribing: {mp3.name}  [{active_model} / {llm.provider(active_model)}]")
        text = llm.transcribe(active_model, mp3)
        out.write_text(text, encoding="utf-8")
        print(f"  → {out.name} ({len(text)} chars)")
        results.append(out)

    return results


def run_all() -> None:
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] transcribe")
        run(project)


if __name__ == "__main__":
    run_all()
