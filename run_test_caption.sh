#!/bin/bash
# Test HeyGen caption behavior. Set CAPTION_MODE to switch test case:
#   CAPTION_MODE=false       ./run_test_caption.sh   (default)
#   CAPTION_MODE=enable_off  ./run_test_caption.sh
#   CAPTION_MODE=omit        ./run_test_caption.sh
#   CAPTION_MODE=obj         ./run_test_caption.sh
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/test_caption.py
