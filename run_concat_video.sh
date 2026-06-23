#!/bin/bash
# PIPELINE_DEBUG=1 ./run_concat_video.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/concat_video.py
