#!/bin/bash
# 設定中のモデルとAPIキーを確認する。
#   ./run_llm_check.sh            設定の表示のみ
#   ./run_llm_check.sh --live     実際に呼び出して疎通確認
#   ./run_llm_check.sh --models   利用可能なモデル一覧
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/llm_check.py "$@"
