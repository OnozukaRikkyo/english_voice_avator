#!/bin/bash
# 【音声1本を指定して】台本と日本語訳を作る。何度も繰り返す用。
# inbox にあるものをまとめて処理したいときは ./run.sh を使う。
#
#   ./run_audio.sh path/to/audio.m4a        音声を指定して処理する
#   ./run_audio.sh                          data/inbox/ にあるものを処理する
#   ./run_audio.sh audio.m4a --keep-inbox   処理後も inbox にファイルを残す
#
# 動画生成（heygen / concat_video）は保留中のため実行されません。
# 完了後、処理済みの音声は data/inbox/ から取り除かれるので、
# 次のファイルを置いてまた実行するだけで繰り返せます。
set -euo pipefail
cd "$(dirname "$0")"

KEEP_INBOX=0
AUDIO=""
for arg in "$@"; do
    case "$arg" in
        --keep-inbox) KEEP_INBOX=1 ;;
        -h|--help)    sed -n '2,10p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *)            AUDIO="$arg" ;;
    esac
done

source .venv/bin/activate
mkdir -p data/inbox

# 音声を指定されたら inbox に入れる
if [[ -n "$AUDIO" ]]; then
    [[ -f "$AUDIO" ]] || { echo "ERROR: ファイルが見つかりません: $AUDIO" >&2; exit 1; }
    case "${AUDIO,,}" in
        *.m4a|*.mp4|*.mp3) ;;
        *) echo "ERROR: 対応形式は .m4a / .mp4 / .mp3 です: $AUDIO" >&2; exit 1 ;;
    esac
    BASE="$(basename "$AUDIO")"
    SLUG="$(python -c "import sys;from pipeline.config import slugify;print(slugify(sys.argv[1]))" "${BASE%.*}")"

    # 同名プロジェクトがあると run_pipeline.py が黙って読み飛ばすため、ここで止める
    if [[ -d "data/$SLUG" ]]; then
        echo "ERROR: プロジェクトが既に存在します: data/$SLUG" >&2
        echo "  作り直す  : rm -rf data/$SLUG && $0 \"$AUDIO\"" >&2
        echo "  別物として: ファイル名を変えてから実行してください" >&2
        exit 1
    fi
    cp -f "$AUDIO" "data/inbox/$BASE"
    echo "inbox に配置: $BASE"
fi

# inbox が空なら何もしない
shopt -s nullglob
FILES=(data/inbox/*.m4a data/inbox/*.mp4 data/inbox/*.mp3)
if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "data/inbox/ に音声がありません。" >&2
    echo "  使い方: $0 path/to/audio.m4a" >&2
    exit 1
fi

python run_pipeline.py

# 取り込み済みの音声を inbox から片付ける（raw/ に複製済み）
if [[ $KEEP_INBOX -eq 0 ]]; then
    for f in "${FILES[@]}"; do
        SLUG="$(python -c "import sys;from pipeline.config import slugify;print(slugify(sys.argv[1]))" "$(basename "${f%.*}")")"
        [[ -f "data/$SLUG/raw/$(basename "$f")" ]] && rm -f "$f"
    done
fi

echo
echo "=== 成果物 ==="
for d in data/*/; do
    [[ -d "$d/narration" ]] || continue
    for t in "$d"narration/*_full.txt "$d"translation/*_ja.txt; do
        [[ -f "$t" ]] && printf "  %7s字  %s\n" "$(wc -m < "$t" | tr -d ' ')" "$t"
    done
done
