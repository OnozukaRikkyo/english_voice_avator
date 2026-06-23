#!/bin/bash
# PIPELINE_DEBUG=1 ./run_concat_narration.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/concat_narration.py
