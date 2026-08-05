#!/bin/bash
# 【単一工程】台本を HeyGen の上限で分割する。全工程なら ./run.sh
# PIPELINE_DEBUG=1 ./step_split.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/split_narration.py
