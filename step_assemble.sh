#!/bin/bash
# 【単一工程】パートを1本の台本に連結する。全工程なら ./run.sh
# PIPELINE_DEBUG=1 ./step_assemble.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/assemble.py
