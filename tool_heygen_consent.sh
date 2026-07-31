#!/bin/bash
# 【ツール】HeyGen アバターの同意リンクを取得する
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/heygen_consent.py