#!/bin/bash
# 【ツール】自動テストを実行する（APIは呼ばない・課金なし）
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pytest "$@"
