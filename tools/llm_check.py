#!/usr/bin/env python3
"""設定中のモデルとAPIキーを確認する。

heygen_check.py の LLM 版。工程ごとにどちらのプロバイダを使う設定になっているかを
表示し、--live を付けると実際に1回ずつ呼び出して疎通を確認する。

Usage:
  python tools/llm_check.py           # 設定の表示のみ（APIは呼ばない）
  python tools/llm_check.py --live    # 実際に呼び出して疎通確認
  python tools/llm_check.py --models  # 利用可能なモデル一覧を取得
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import llm
from pipeline.config import (
    GEMINI_API_KEY, OPENAI_API_KEY,
    TRANSCRIBE_MODEL, REWRITE_MODEL, TRANSLATE_MODEL, TRANSCRIBE_ENGLISH_MODEL,
)

_STEPS = [
    ("transcribe", TRANSCRIBE_MODEL),
    ("  └ 英語化", TRANSCRIBE_ENGLISH_MODEL),
    ("rewrite", REWRITE_MODEL),
    ("translate", TRANSLATE_MODEL),
]


def show_config() -> None:
    print("\n=== APIキー ===")
    print(f"  GEMINI_API_KEY : {'設定済み' if GEMINI_API_KEY else '(未設定)'}")
    print(f"  OPENAI_API_KEY : {'設定済み' if OPENAI_API_KEY else '(未設定)'}")

    print("\n=== 工程ごとのモデル ===")
    for step, model in _STEPS:
        note = ""
        if step.startswith("  └") and not llm.is_openai(TRANSCRIBE_MODEL):
            note = "  ← Gemini経路では使われない"
        print(f"  {step:<12} {model:<22} {llm.provider(model)}{note}")

    needed = {llm.provider(m) for _, m in _STEPS}
    if not llm.is_openai(TRANSCRIBE_MODEL):
        needed.discard(llm.provider(TRANSCRIBE_ENGLISH_MODEL))
        needed = {llm.provider(m) for s, m in _STEPS if not s.startswith("  └")}
    missing = [
        p for p in needed
        if (p == "Gemini" and not GEMINI_API_KEY) or (p == "OpenAI" and not OPENAI_API_KEY)
    ]
    if missing:
        print(f"\n  ✗ 必要なキーが未設定: {', '.join(missing)}")
    else:
        print(f"\n  ✓ 必要なキー（{', '.join(sorted(needed))}）はすべて設定済み")


def check_live() -> None:
    print("\n=== 疎通確認（実際に呼び出します）===")
    tested: set[str] = set()
    for step, model in _STEPS:
        if model in tested:
            continue
        tested.add(model)
        if model == TRANSCRIBE_MODEL:
            print(f"  {model:<22} 音声モデルのため疎通確認はスキップ（./run_transcribe.sh で確認）")
            continue
        try:
            out = llm.generate_text(model, "Reply with exactly: OK")
            status = "✓" if "OK" in out.upper() else "△"
            print(f"  {status} {model:<22} {llm.provider(model):<7} → {out[:40]!r}")
        except Exception as e:
            print(f"  ✗ {model:<22} {llm.provider(model):<7} → {type(e).__name__}: {str(e)[:120]}")


def list_models() -> None:
    print("\n=== 利用可能なモデル ===")
    if OPENAI_API_KEY:
        from pipeline.openai_client import get_openai_client
        ids = sorted(m.id for m in get_openai_client().models.list())
        print(f"\n  OpenAI ({len(ids)}件) — 音声関連:")
        for i in ids:
            if any(k in i for k in ("transcri", "whisper", "audio")):
                print(f"    {i}")
    if GEMINI_API_KEY:
        from pipeline.gemini_client import get_genai_client
        names = sorted(m.name.removeprefix("models/") for m in get_genai_client().models.list())
        print(f"\n  Gemini ({len(names)}件):")
        for n in names:
            print(f"    {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="設定中のモデルとAPIキーを確認する")
    parser.add_argument("--live", action="store_true", help="実際に呼び出して疎通確認する")
    parser.add_argument("--models", action="store_true", help="利用可能なモデル一覧を取得する")
    args = parser.parse_args()

    show_config()
    if args.live:
        check_live()
    if args.models:
        list_models()


if __name__ == "__main__":
    main()
