"""定型の挨拶とアウトロの差し込み（tools/assemble.py）。

台本全体に1回だけ現れるものは、塊ごとの生成ではなく連結の時点で足す。
モデルに書かせると文言が毎回ぶれるうえ、part01 だけの特別扱いが要る。

挨拶は <speak> の外には置けない。妥当な SSML でなくなると、
音声合成に渡した時点で壊れる。
"""
import re
import xml.etree.ElementTree as ET

import pytest

from pipeline import ssml
from pipeline.config import NARRATION_OPENING
from tools import assemble

PART = '<speak>\nThe announcement landed after midnight. <break time="0.5s"/> Here is why.\n</speak>'


def _parts(tmp_path, *bodies) -> list:
    d = tmp_path / "parts"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for i, b in enumerate(bodies, 1):
        f = d / f"ep_part{i:02d}.txt"
        f.write_text(b, encoding="utf-8")
        out.append(f)
    return out


def test_opening_comes_first_and_closing_last(tmp_path, monkeypatch):
    monkeypatch.setattr(assemble, "NARRATION_OPENING", "Hello everyone.")
    monkeypatch.setattr(assemble, "NARRATION_CLOSING", "That is where I leave it.")
    got = assemble._merge_ssml(_parts(tmp_path, PART))
    assert ssml.unwrap(got).startswith("Hello everyone.")
    assert ssml.unwrap(got).endswith("That is where I leave it.")


def test_original_text_is_kept(tmp_path):
    got = assemble._merge_ssml(_parts(tmp_path, PART))
    assert "The announcement landed after midnight." in got
    assert "Here is why." in got


def test_result_is_a_single_speak_element(tmp_path):
    got = assemble._merge_ssml(_parts(tmp_path, PART, PART))
    assert got.count("<speak>") == 1 and got.count("</speak>") == 1
    ET.fromstring(got)                       # 妥当でなければ例外で落ちる


def test_empty_opening_leaves_the_script_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(assemble, "NARRATION_OPENING", "")
    monkeypatch.setattr(assemble, "NARRATION_CLOSING", "")
    got = assemble._merge_ssml(_parts(tmp_path, PART))
    assert ssml.unwrap(got) == ssml.unwrap(PART)


def test_no_double_break_at_the_seam(tmp_path, monkeypatch):
    """挨拶の末尾の間と本文の先頭の間が重なると、そこだけ不自然に長く止まる。"""
    monkeypatch.setattr(assemble, "NARRATION_OPENING", 'Hello. <break time="1.5s"/>')
    monkeypatch.setattr(assemble, "NARRATION_CLOSING", "")
    got = assemble._merge_ssml(_parts(tmp_path, '<speak><break time="0.5s"/> Body.</speak>'))
    assert not re.search(r'<break[^>]*/>\s*<break[^>]*/>', got)


@pytest.mark.parametrize("word", ["Hello", "welcome", "Bogdan Parkhomenko"])
def test_default_opening_greets_and_names_the_presenter(word):
    assert word in NARRATION_OPENING


def test_opening_survives_heygen_splitting(tmp_path, monkeypatch):
    """heygen は1パートを1本の動画として送る。挨拶が先頭に残らないと読まれない。"""
    monkeypatch.setattr(assemble, "NARRATION_OPENING", "Hello everyone.")
    monkeypatch.setattr(assemble, "NARRATION_CLOSING", "")
    long_part = ssml.wrap(" ".join(f'Sentence {i}. <break time="1.0s"/>' for i in range(400)))
    pieces = ssml.split(assemble._merge_ssml(_parts(tmp_path, long_part)), 5000)
    assert len(pieces) > 1
    assert ssml.unwrap(pieces[0]).startswith("Hello everyone.")
    assert all(len(p) <= 5000 and p.count("<speak>") == 1 for p in pieces)


def test_hook_extraction_strips_the_greeting(tmp_path, monkeypatch):
    """後続チャンクへ渡すフックは台本の実質の冒頭であって、定型の挨拶ではない。"""
    from pipeline import rewrite
    monkeypatch.setattr(rewrite, "NARRATION_OPENING", "Hello everyone.")
    p = tmp_path / "p1.txt"
    p.write_text("<speak>\nHello everyone.\n\nThe hook itself. More text.\n</speak>",
                 encoding="utf-8")
    hook = rewrite._hook_text(p)
    assert hook.startswith("The hook itself.")
    assert "Hello everyone" not in hook
