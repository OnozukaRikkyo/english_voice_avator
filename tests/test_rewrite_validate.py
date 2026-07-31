"""rewrite._validate() — 生成された台本を書き出す前の検証。

2026-07-31 に実際に起きた障害の回帰テストを含む:
gemini-3.5-flash が `<speak>In the shadows... <break time=` で切れた
101字の台本を返し、当時の「50字未満なら例外」を通過して翻訳まで流れた。
"""
import pytest

from pipeline.rewrite import _validate

SRC = 9000  # transcript の文字数


def part(index: int, body_len: int = 3000) -> dict:
    return {"index": index, "text": "<speak>" + "x" * body_len + "</speak>"}


def test_valid_result_passes():
    assert _validate([part(1), part(2)], SRC) is None


def test_empty_result_is_rejected():
    assert "空" in _validate([], SRC)


def test_truncated_mid_tag_is_rejected():
    """実際に起きた障害: SSML がタグの途中で切れている。"""
    broken = [{"index": 1, "text": '<speak>In the shadows of diplomacy, a shift unfolds. <break time='}]
    problem = _validate(broken, SRC)
    assert problem is not None and "</speak>" in problem


def test_missing_closing_tag_is_rejected():
    assert "</speak>" in _validate([{"index": 1, "text": "<speak>" + "x" * 3000}], SRC)


def test_too_short_part_is_rejected():
    assert "短すぎ" in _validate([{"index": 1, "text": "<speak>tiny</speak>"}], SRC)


def test_nested_speak_is_rejected():
    bad = [{"index": 1, "text": "<speak><speak>" + "x" * 3000 + "</speak>"}]
    assert "<speak>" in _validate(bad, SRC)


def test_total_below_ratio_is_rejected():
    """全網羅を指示しているのに入力の30%未満しか返らないのは失敗。"""
    problem = _validate([part(1, 1000)], SRC)
    assert problem is not None and "%" in problem


def test_duplicate_index_is_rejected():
    """index が重複すると同じ _part01.txt に2回書いて1つ失われる。"""
    assert "連番" in _validate([part(1), part(1)], SRC)


def test_gap_in_index_is_rejected():
    assert "連番" in _validate([part(1), part(3)], SRC)


def test_index_not_starting_at_one_is_rejected():
    assert "連番" in _validate([part(0), part(1)], SRC)


def test_non_integer_index_is_rejected():
    assert "整数" in _validate([{"index": "1", "text": part(1)["text"]}], SRC)


def test_missing_index_is_rejected_without_crashing():
    """index キーが無い要素で KeyError を投げず、理由を返すこと。"""
    assert _validate([{"text": part(1)["text"]}], SRC) is not None
