#!/bin/bash
# 【パイプラインの唯一の入口】音声から台本・日本語訳・アバター動画までを通す。
#
#   ./run.sh                          data/inbox/ にあるものをまとめて処理する
#   ./run.sh path/to/audio.m4a        音声を1本だけ指定して処理する
#   ./run.sh --again                  既存プロジェクトを上書きして作り直す（音声の置き直し不要）
#   ./run.sh --no-video               動画を作らず、台本と日本語訳まで
#   ./run.sh --keep-inbox             処理後も inbox に音声を残す
#   ./run.sh --force                  既存の出力を無視して作り直す
#   ./run.sh --steps rewrite,review   特定の工程だけ動かす
#   ./run.sh --provider openai        全工程を OpenAI に切り替える
#   ./run.sh --help                   全オプション（run_pipeline.py --help）
#
# 音声パスは第1引数。それ以外の引数は run_pipeline.py へそのまま渡ります。
#   ./run.sh audio.m4a --provider openai
#   ./run.sh audio.m4a --model-rewrite gemini-3.6-flash --force
#
# 完了後、処理済みの音声は data/inbox/ から取り除かれるので、
# 次のファイルを置いてまた実行するだけで繰り返せます。
set -euo pipefail
cd "$(dirname "$0")"

KEEP_INBOX=0
AGAIN=0
AUDIO=""
# 音声パスは第1引数のみ。残りは run_pipeline.py へそのまま渡す
# （--model-rewrite MODEL のように値を取るフラグも自然に通る）。
if [[ $# -gt 0 && "$1" != -* ]]; then
    AUDIO="$1"
    shift
fi
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --keep-inbox) KEEP_INBOX=1 ;;
        --again)      AGAIN=1 ;;
        # 冒頭のコメントをそのまま使い方として出す（行番号で切ると編集のたびに狂う）
        -h|--help)    awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
        *)            ARGS+=("$arg") ;;
    esac
done

# 音声を後ろに書いた場合（./run.sh --force audio.m4a）、それは
# run_pipeline.py へのオプションとして扱われてしまう。位置の誤りだと指摘する。
# 音声を指定しない使い方（inbox をまとめて処理）は正当なので、
# 「引数はあるが音声がない」では判定せず、音声らしき引数の混入だけを見る。
for a in ${ARGS[@]+"${ARGS[@]}"}; do
    case "${a,,}" in
        *.m4a|*.mp4|*.mp3)
            echo "ERROR: 音声パスは最初の引数に指定してください（オプションはその後ろ）" >&2
            echo "  誤: $0 $*" >&2
            echo "  正: $0 $a ${ARGS[*]/$a/}" >&2
            exit 1 ;;
    esac
done

# --again は「いまある raw/ からやり直す」ので、新しい音声とは併用できない
if [[ -n "$AUDIO" && $AGAIN -eq 1 ]]; then
    echo "ERROR: --again は既存プロジェクトを作り直すオプションです。音声の指定とは併用できません。" >&2
    echo "  新しい音声を処理する: $0 $AUDIO" >&2
    echo "  既存を作り直す      : $0 --again" >&2
    exit 1
fi

source .venv/bin/activate
mkdir -p data/inbox

# 成果物を表示する対象。空なら全プロジェクト。
SHOW=""

if [[ $AGAIN -eq 1 ]]; then
    # ── 既存プロジェクトを上書きして作り直す ──────────────────────────────
    case " ${ARGS[*]-} " in
        *" --project "*) ;;                      # 明示されているので選定しない
        *)
            # 空を返して正常終了する（ここで落とすと下のエラーメッセージに届かない）
            SHOW="$(python - <<'PY'
from pipeline.config import DATA, all_projects
projects = all_projects()
if projects:
    # 最終更新が新しいもの。生成物の更新時刻を見る（raw/ は変わらないため）
    def touched(p):
        files = [f for f in (DATA / p).rglob("*") if f.is_file()]
        return max((f.stat().st_mtime for f in files), default=0)
    print(max(projects, key=touched))
PY
)"
            if [[ -z "$SHOW" ]]; then
                echo "プロジェクトがありません。まず $0 音声.m4a で作ってください。" >&2
                exit 1
            fi
            ;;
    esac

    # 何をやり直すのかを先に示す（API を呼ぶので黙って走らせない）
    if [[ -n "$SHOW" ]]; then
        COUNT="$(python -c "from pipeline.config import all_projects; print(len(all_projects()))")"
        echo "対象: $SHOW"
        [[ "$COUNT" -gt 1 ]] && echo "  （他に $((COUNT - 1)) 件あります。--project で切り替えられます）"
        python run_pipeline.py --force --project "$SHOW" ${ARGS[@]+"${ARGS[@]}"}
    else
        python run_pipeline.py --force ${ARGS[@]+"${ARGS[@]}"}
    fi
else
    # ── 音声を指定されたら inbox に入れる ─────────────────────────────────
    if [[ -n "$AUDIO" ]]; then
        [[ -f "$AUDIO" ]] || { echo "ERROR: ファイルが見つかりません: $AUDIO" >&2; exit 1; }
        case "${AUDIO,,}" in
            *.m4a|*.mp4|*.mp3) ;;
            *) echo "ERROR: 対応形式は .m4a / .mp4 / .mp3 です: $AUDIO" >&2; exit 1 ;;
        esac
        BASE="$(basename "$AUDIO")"
        SHOW="$(python -c "import sys;from pipeline.config import slugify;print(slugify(sys.argv[1]))" "${BASE%.*}")"

        # 同名プロジェクトがあると run_pipeline.py が黙って読み飛ばすため、ここで止める
        if [[ -d "data/$SHOW" ]]; then
            echo "ERROR: プロジェクトが既に存在します: data/$SHOW" >&2
            echo "  作り直す  : $0 --again --project $SHOW" >&2
            echo "  別物として: ファイル名を変えてから実行してください" >&2
            exit 1
        fi
        cp -f "$AUDIO" "data/inbox/$BASE"
        echo "inbox に配置: $BASE"
    fi

    # inbox が空でもここでは止めない。既存プロジェクトの工程をやり直すだけの
    # 使い方（./run.sh --steps rewrite）が正当なため。音声もプロジェクトも無い場合は
    # run_pipeline.py が「No projects found」と案内して止まる。
    shopt -s nullglob
    FILES=(data/inbox/*.m4a data/inbox/*.mp4 data/inbox/*.mp3)

    # 音声を指定されたときは、そのプロジェクトだけを処理する
    if [[ -n "$SHOW" ]]; then
        python run_pipeline.py --project "$SHOW" ${ARGS[@]+"${ARGS[@]}"}
    else
        python run_pipeline.py ${ARGS[@]+"${ARGS[@]}"}
    fi

    # 取り込み済みの音声を inbox から片付ける（raw/ に複製済み）
    if [[ $KEEP_INBOX -eq 0 ]]; then
        for f in "${FILES[@]}"; do
            S="$(python -c "import sys;from pipeline.config import slugify;print(slugify(sys.argv[1]))" "$(basename "${f%.*}")")"
            [[ -f "data/$S/raw/$(basename "$f")" ]] && rm -f "$f"
        done
    fi
fi

echo
echo "=== 成果物 ==="
DIRS=(data/*/)
[[ -n "$SHOW" ]] && DIRS=("data/$SHOW/")
for d in "${DIRS[@]}"; do
    [[ -d "$d/narration" ]] || continue
    for t in "$d"narration/*_full.txt "$d"translation/*_ja.txt "$d"video/*.mp4; do
        [[ -f "$t" ]] || continue
        case "$t" in
            *.mp4) printf "  %7s    %s\n" "$(du -h "$t" | cut -f1)" "$t" ;;
            *)     printf "  %7s字  %s\n" "$(wc -m < "$t" | tr -d ' ')" "$t" ;;
        esac
    done
done
