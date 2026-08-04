"""定型オープニングの差し込み（rewrite._with_opening）。

挨拶は part01 の <speak> の中に入る。外に置くと SSML として妥当でなくなり、
heygen が読み上げない。
"""
import pytest

from pipeline import ssml
from pipeline.config import NARRATION_OPENING
from pipeline.rewrite import _with_opening

PART = '<speak>The announcement landed after midnight. <break time="0.5s"/> Here is why.</speak>'


def test_opening_comes_first():
    got = _with_opening(PART)
    body = ssml.unwrap(got)
    assert body.startswith(NARRATION_OPENING.strip())


def test_original_text_is_kept():
    got = _with_opening(PART)
    assert "The announcement landed after midnight." in got
    assert "Here is why." in got


def test_result_is_a_single_speak_element():
    got = _with_opening(PART)
    assert got.count("<speak>") == 1
    assert got.count("</speak>") == 1
    assert got.startswith("<speak>")
    assert got.endswith("</speak>")


def test_result_parses_as_xml():
    import xml.etree.ElementTree as ET
    ET.fromstring(_with_opening(PART))   # 妥当でなければ例外で落ちる


def test_empty_opening_leaves_the_part_untouched(monkeypatch):
    monkeypatch.setattr("pipeline.rewrite.NARRATION_OPENING", "")
    assert _with_opening(PART) == PART


@pytest.mark.parametrize("word", ["Hello", "welcome", "Bogdan Parkhomenko"])
def test_default_opening_greets_and_names_the_presenter(word):
    assert word in NARRATION_OPENING


def test_opening_survives_heygen_splitting():
    """長いパートは heygen が割る。挨拶は必ず1本目の先頭に残る。"""
    long_part = ssml.wrap(
        " ".join(f'Sentence number {i}. <break time="1.0s"/>' for i in range(400))
    )
    pieces = ssml.split(_with_opening(long_part), 5000)
    assert len(pieces) > 1
    assert ssml.unwrap(pieces[0]).startswith(NARRATION_OPENING.strip())
    assert all(len(p) <= 5000 for p in pieces)
