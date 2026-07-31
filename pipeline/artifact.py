"""成果物の書き出し口。**検証を通ったものだけを書く。**

各工程が個別に `path.write_text(...)` を呼ぶと、API が空や極端に短い結果を
返したときにそのままファイルになる。しかも0バイトでもファイルは存在するため、
次回実行時に「出力あり」とみなされ [skip] され、壊れた状態が固定化する。

書き込み口をここ1箇所に集めることで、その穴を工程ごとに塞ぎ忘れないようにする。
"""
from pathlib import Path


class EmptyResultError(RuntimeError):
    """生成結果が空・短すぎる・入力に対して不足している。"""


def write_checked(
    path: Path,
    text: str,
    *,
    min_chars: int = 50,
    src_chars: int | None = None,
    min_ratio: float = 0.0,
    label: str = "",
) -> Path:
    """検証を通った結果だけをファイルに書き、書いたパスを返す。

    検証に落ちたときは **ファイルを作らずに** EmptyResultError を送出する。
    既存ファイルがあっても壊さない。

    Args:
        min_chars: これ未満なら失敗とみなす。
        src_chars: 入力の文字数。min_ratio と併せて使う。
        min_ratio: 出力が入力の何割を下回ったら失敗とみなすか（0 なら無効）。
        label: エラーメッセージに出す呼び出し元の名前。既定はファイル名。
    """
    who = label or path.name
    t = (text or "").strip()

    if len(t) < min_chars:
        raise EmptyResultError(
            f"{who}: 生成結果が空か短すぎます（{len(t)}字 < 下限 {min_chars}字）。"
            f"ファイルは作成していません。"
        )

    if src_chars and min_ratio > 0 and len(t) < src_chars * min_ratio:
        raise EmptyResultError(
            f"{who}: 生成結果 {len(t):,}字 は入力 {src_chars:,}字 の "
            f"{len(t) / src_chars * 100:.0f}%しかありません（下限 {min_ratio * 100:.0f}%）。"
            f"ファイルは作成していません。"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(t, encoding="utf-8")
    return path
