#!/usr/bin/env python3
"""Main pipeline orchestrator.

Entry point is ./run.sh (this file is not meant to be run directly).

  ./run.sh [--steps STEP1,STEP2,...] [--project SLUG] [--force] [--max-chars N]
           [--provider {openai,gemini}] [--model-<step> MODEL]

Steps (default: all):
  convert          raw/             → audio/
  transcribe       audio/           → transcript/
  rewrite          transcript/      → narration/parts/
  concat_narration narration/parts/ → narration/*_full.txt
  translate        narration/       → translation/

Suspended (on hold — HeyGen caption issue unresolved):
  heygen           narration/parts/ → video/parts/
  concat_video     video/parts/     → video/*.mp4

Flags:
  --force          Force re-run even if output files already exist.
  --max-chars N    Override REWRITE_MAX_CHARS for the rewrite step only.
                   Use -1 for unlimited (single file), or N for max chars per segment.
  --provider {openai,gemini}
                   Switch every step to one provider for this run, using the
                   preset in pipeline/config.py.
  --model-transcribe / --model-rewrite / --model-translate MODEL
                   Override one step's model. Takes precedence over --provider.
                   The model name picks the provider: gpt-* → OpenAI, else Gemini.
                   To change it permanently, edit pipeline/config.py.

Each step is idempotent by default: already-generated files are skipped.
New audio files placed in data/inbox/ are automatically registered as projects.
"""
import argparse
import shutil
import sys
import time

from pipeline.config import (
    INBOX_DIR, DATA, MODEL_SLOTS, PRESETS,
    all_projects, current_models, ensure_project_dirs, resolve_models, slugify,
)

# SUSPENDED: heygen / concat_video are on hold until the HeyGen on-screen caption
# problem is resolved (see tools/investigate_caption.py). The modules themselves are
# left intact — uncomment the two entries below to re-enable video generation.
ALL_STEPS = [
    "convert",
    "transcribe",
    "rewrite",
    "concat_narration",
    "translate",
    # "heygen",        # on hold
    # "concat_video",  # on hold
]
_AUDIO_EXTS = {".m4a", ".mp4", ".mp3"}


def _scan_inbox() -> None:
    """Create projects from any audio files found in data/inbox/."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    audio_files = [f for f in sorted(INBOX_DIR.iterdir()) if f.suffix.lower() in _AUDIO_EXTS]
    if not audio_files:
        return
    print(f"Inbox: {len(audio_files)} file(s) found")
    for audio in audio_files:
        slug = slugify(audio.stem)
        raw_dir = DATA / slug / "raw"
        dst = raw_dir / audio.name

        # 同名ファイルが既にある。中身も同じなら取り込み済み、違うなら別物。
        # 黙って読み飛ばすと実行全体が無言の no-op になるので、違えば止める。
        if dst.exists():
            if dst.stat().st_size == audio.stat().st_size:
                print(f"  [skip] {audio.name} (取り込み済み: data/{slug}/)")
                continue
            sys.exit(
                f"ERROR: {audio.name} は data/{slug}/raw/ の同名ファイルと内容が違います"
                f"（{audio.stat().st_size:,} / {dst.stat().st_size:,} バイト）。\n"
                f"  作り直す  : rm -rf data/{slug}\n"
                f"  別物として: inbox のファイル名を変えてください"
            )

        # slugify は区切り文字を潰すため、別名でも同じスラグになりうる
        # （'a-b' と 'a_b' → いずれも 'a_b'）。別の音声に合流させない。
        if raw_dir.is_dir() and any(raw_dir.iterdir()):
            existing = ", ".join(f.name for f in sorted(raw_dir.iterdir()))
            sys.exit(
                f"ERROR: スラグ '{slug}' は別のファイルで使用済みです。\n"
                f"  取り込もうとした: {audio.name}\n"
                f"  既にあるもの    : {existing}\n"
                f"  inbox のファイル名を変えてください"
            )

        ensure_project_dirs(slug)
        shutil.copy2(audio, dst)
        print(f"  {audio.name} → data/{slug}/raw/")


def main() -> None:
    _scan_inbox()
    parser = argparse.ArgumentParser(description="English Voice Avatar pipeline")
    parser.add_argument(
        "--steps",
        default=",".join(ALL_STEPS),
        help=f"Comma-separated steps to run (default: all). Choices: {', '.join(ALL_STEPS)}",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Run only this project slug (default: all projects)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run even if output files already exist",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        dest="max_chars",
        help="Override REWRITE_MAX_CHARS for the rewrite step (-1 = unlimited)",
    )
    # モデル名がプロバイダを決める（gpt-* → OpenAI、それ以外 → Gemini）。
    # 恒久的に変えるなら pipeline/config.py 側を書き換える。
    parser.add_argument(
        "--provider",
        default=None,
        choices=sorted(PRESETS),
        help="Switch every step to one provider for this run (preset in config.py)",
    )
    defaults = current_models()
    for slot in MODEL_SLOTS:
        if slot == "notebooklm":
            continue  # パイプライン外（./gen_notebooklm_prompt.sh で指定する）
        parser.add_argument(
            f"--model-{slot.replace('_', '-')}",
            default=None,
            dest=f"model_{slot}",
            metavar="MODEL",
            help=f"Override the {slot} model for this run (default: {defaults[slot]})",
        )
    args = parser.parse_args()

    # 優先順位: 個別指定 > --provider > config.py の定数
    try:
        models = resolve_models(
            args.provider,
            **{slot: getattr(args, f"model_{slot}")
               for slot in MODEL_SLOTS if slot != "notebooklm"},
        )
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    steps = [s.strip() for s in args.steps.split(",")]
    unknown = set(steps) - set(ALL_STEPS)
    if unknown:
        print(f"Unknown steps: {unknown}", file=sys.stderr)
        sys.exit(1)

    # --project の綴り間違いで空ディレクトリを作って正常終了しないよう、先に実在を確認する
    if args.project and not (DATA / args.project / "raw").is_dir():
        print(f"プロジェクトがありません: {args.project}", file=sys.stderr)
        print(f"  存在するもの: {', '.join(all_projects()) or '(なし)'}", file=sys.stderr)
        sys.exit(1)

    projects = [args.project] if args.project else all_projects()
    if not projects:
        print("No projects found. Place source files in data/inbox/", file=sys.stderr)
        sys.exit(1)

    if args.force:
        print("[--force] Existing output files will be overwritten.")
    if args.max_chars is not None:
        print(f"[--max-chars {args.max_chars}] Overriding REWRITE_MAX_CHARS for rewrite step.")
    if args.provider or models != current_models():
        label = f"--provider {args.provider}" if args.provider else "model override"
        print(f"[{label}] " + ", ".join(f"{s}={models[s]}" for s in MODEL_SLOTS if s != "notebooklm"))

    t0 = time.time()

    for project in projects:
        ensure_project_dirs(project)
        print(f"\n{'='*60}")
        print(f"  Project: {project}")
        print(f"{'='*60}")

        for step in steps:
            print(f"\n--- {step} ---")
            t1 = time.time()

            if step == "convert":
                from pipeline import convert
                convert.run(project, force=args.force)

            elif step == "transcribe":
                from pipeline import transcribe
                transcribe.run(
                    project, force=args.force,
                    model=models["transcribe"],
                )

            elif step == "rewrite":
                from pipeline import rewrite
                rewrite.run(
                    project, force=args.force, max_chars=args.max_chars,
                    model=models["rewrite"],
                )

            elif step == "concat_narration":
                from tools.concat_narration import concat_narration
                concat_narration(project, force=args.force)

            elif step == "translate":
                from pipeline import translate
                translate.run(project, force=args.force, model=models["translate"])

            # SUSPENDED — see ALL_STEPS above.
            # elif step == "heygen":
            #     from pipeline import heygen
            #     heygen.run(project, force=args.force)
            #
            # elif step == "concat_video":
            #     from tools.concat_video import concat_video
            #     concat_video(project, force=args.force)

            print(f"  done in {time.time() - t1:.1f}s")

    print(f"\n{'='*60}")
    print(f"  Pipeline complete in {time.time() - t0:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
