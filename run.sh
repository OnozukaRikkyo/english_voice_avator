#!/bin/bash
# 【data/inbox/ にあるものをまとめて】台本と日本語訳を作る。パイプラインの標準入口。
# 音声を1本だけ指定して処理したいときは ./run_audio.sh を使う。
#
#   ./run.sh                        inbox の全件を処理する
#   ./run.sh --force                既存の出力を無視して作り直す
#   ./run.sh --steps transcribe     特定の工程だけ動かす
#   ./run.sh --provider openai      全工程を OpenAI に切り替える
#   ./run.sh --help                 全オプション
#
# 動画生成（heygen / concat_video）は保留中のため実行されません。
cd "$(dirname "$0")"
source .venv/bin/activate
python run_pipeline.py "$@"
