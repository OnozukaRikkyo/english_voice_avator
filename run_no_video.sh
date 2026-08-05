#!/bin/bash
# 【動画なし】台本と日本語訳まで作る。動画は ./run.sh --steps heygen,concat_video で。
# 入口は ./run.sh 一本で、これはその近道です。引数はそのまま渡ります。
#
#   ./run_no_video.sh                  inbox の全件を、翻訳まで
#   ./run_no_video.sh audio.m4a        音声を1本だけ指定して、翻訳まで
#   ./run_no_video.sh --again          既存プロジェクトを翻訳まで作り直す
# 音声パスは run.sh の第1引数でなければならないので、--no-video は後ろに置く
exec "$(dirname "$0")/run.sh" "$@" --no-video
