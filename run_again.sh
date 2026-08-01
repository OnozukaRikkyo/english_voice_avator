#!/bin/bash
# 【既存のプロジェクトを上書きして作り直す】引数は不要。
# 音声を置き直す必要はなく、いまある raw/ からやり直します。
#
#   ./run_again.sh                        既存のプロジェクトを全工程やり直す
#   ./run_again.sh --steps rewrite        特定の工程だけやり直す
#   ./run_again.sh --project スラッグ名    対象を明示する（複数あるとき）
#   ./run_again.sh --provider openai      モデルを変えてやり直す
#
# プロジェクトが複数あるときは、最後に更新されたものを選びます。
# 既存の成果物は上書きされます（元音声 raw/ と辞書 senario_jp/ は残ります）。
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

for arg in "$@"; do
    case "$arg" in
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \?//'; exit 0 ;;
    esac
done

# --project が指定されていなければ、最後に更新されたプロジェクトを選ぶ
TARGET=""
case " $* " in
    *" --project "*) ;;                      # 明示されているので選定しない
    *)
        # 空を返して正常終了する（ここで落とすと下のエラーメッセージに届かない）
        TARGET="$(python - <<'PY'
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
        if [[ -z "$TARGET" ]]; then
            echo "プロジェクトがありません。まず ./run_audio.sh 音声.m4a で作ってください。" >&2
            exit 1
        fi
        ;;
esac

# 何をやり直すのかを先に示す（API を呼ぶので黙って走らせない）
if [[ -n "$TARGET" ]]; then
    COUNT="$(python -c "from pipeline.config import all_projects; print(len(all_projects()))")"
    echo "対象: $TARGET"
    [[ "$COUNT" -gt 1 ]] && echo "  （他に $((COUNT - 1)) 件あります。--project で切り替えられます）"
    python run_pipeline.py --force --project "$TARGET" "$@"
else
    python run_pipeline.py --force "$@"
fi

echo
echo "=== 成果物 ==="
DIRS=(data/*/)
[[ -n "$TARGET" ]] && DIRS=("data/$TARGET/")
for d in "${DIRS[@]}"; do
    [[ -d "$d/narration" ]] || continue
    for t in "$d"narration/*_full.txt "$d"translation/*_ja.txt; do
        [[ -f "$t" ]] && printf "  %7s字  %s\n" "$(wc -m < "$t" | tr -d ' ')" "$t"
    done
done
