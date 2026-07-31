"""artifact.write_checked() — 成果物の書き出し口。

空の結果をファイルにしてしまうと、次回実行時に「出力あり」とみなされ
[skip] され、壊れた状態が固定化する。書かないことを保証する。
"""
import pytest

from pipeline.artifact import EmptyResultError, write_checked


def test_valid_text_is_written(tmp_path):
    out = tmp_path / "a.txt"
    write_checked(out, "x" * 100, min_chars=50)
    assert out.read_text(encoding="utf-8") == "x" * 100


def test_text_is_stripped(tmp_path):
    out = tmp_path / "a.txt"
    write_checked(out, "  hello  " + "x" * 100, min_chars=50)
    assert not out.read_text(encoding="utf-8").startswith(" ")


def test_empty_text_creates_no_file(tmp_path):
    out = tmp_path / "a.txt"
    with pytest.raises(EmptyResultError):
        write_checked(out, "")
    assert not out.exists()


def test_whitespace_only_creates_no_file(tmp_path):
    out = tmp_path / "a.txt"
    with pytest.raises(EmptyResultError):
        write_checked(out, "   \n\t ")
    assert not out.exists()


def test_none_creates_no_file(tmp_path):
    out = tmp_path / "a.txt"
    with pytest.raises(EmptyResultError):
        write_checked(out, None)  # type: ignore[arg-type]
    assert not out.exists()


def test_too_short_creates_no_file(tmp_path):
    out = tmp_path / "a.txt"
    with pytest.raises(EmptyResultError):
        write_checked(out, "short", min_chars=50)
    assert not out.exists()


def test_existing_file_is_not_destroyed_on_failure(tmp_path):
    """検証に落ちても既存の成果物を壊さないこと。"""
    out = tmp_path / "a.txt"
    out.write_text("前回の結果", encoding="utf-8")
    with pytest.raises(EmptyResultError):
        write_checked(out, "")
    assert out.read_text(encoding="utf-8") == "前回の結果"


def test_ratio_below_minimum_creates_no_file(tmp_path):
    out = tmp_path / "a.txt"
    with pytest.raises(EmptyResultError):
        write_checked(out, "x" * 100, min_chars=50, src_chars=10_000, min_ratio=0.20)
    assert not out.exists()


def test_ratio_above_minimum_is_written(tmp_path):
    out = tmp_path / "a.txt"
    write_checked(out, "x" * 3000, min_chars=50, src_chars=10_000, min_ratio=0.20)
    assert out.exists()


def test_parent_directory_is_created(tmp_path):
    out = tmp_path / "nested" / "deep" / "a.txt"
    write_checked(out, "x" * 100, min_chars=50)
    assert out.exists()
