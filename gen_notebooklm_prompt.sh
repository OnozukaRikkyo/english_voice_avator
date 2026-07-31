#!/bin/bash
# 【資料 → NotebookLM プロンプト】data/senario_jp/ の docx/pdf からプロンプトを生成する。
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/gen_notebooklm_prompt.py "$@"
