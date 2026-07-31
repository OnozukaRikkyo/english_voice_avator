#!/bin/bash
# Run caption investigation: empirical API tests + frame analysis
# Output: data/caption_investigation/report.md
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/investigate_caption.py
