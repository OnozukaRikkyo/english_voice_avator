"""SSML 台本の分割 — HeyGen の 5,000 字上限に収めつつ、話題の途中で切らない。

rewrite が作る台本パートは 6,416〜9,483 字になることがあり、そのままでは送れない。
切る場所は <break> に合わせる。rewrite が間の長さを意味づけているため、
1.5s（章の転換）> 1.0s（段落）> 0.5s（文間）の順に切りたい。
"""
import re
import xml.etree.ElementTree as ET

import pytest

from pipeline.ssml import split, unwrap, wrap


def build(sentences_per_gap: dict[float, int], sentence: str = "This is one sentence. ") -> str:
    """指定した間の長さで区切られた SSML を組み立てる。"""
    body = ""
    for gap, n in sentences_per_gap.items():
        body += sentence * n + f'<break time="{gap}s"/>'
    return wrap(body)


# ── 包む・外す ──────────────────────────────────────────────────────────────

def test_unwrap_removes_the_speak_element():
    assert unwrap("<speak>\nBody here.\n</speak>") == "Body here."


def test_unwrap_tolerates_no_wrapper():
    assert unwrap("Body here.") == "Body here."


def test_wrap_produces_a_parseable_document():
    assert ET.fromstring(wrap("Body here.")).tag == "speak"


# ── 上限に収まっているものは触らない ────────────────────────────────────────

def test_short_text_is_returned_unchanged():
    t = wrap('Short. <break time="0.5s"/> Also short.')
    assert split(t, 5000) == [t]


def test_text_exactly_at_the_limit_is_not_split():
    t = wrap("x" * (5000 - len(wrap(""))))
    assert len(split(t, 5000)) == 1


# ── 上限を超えたら割る ──────────────────────────────────────────────────────

def test_every_piece_fits_the_limit():
    t = build({0.5: 400})
    for piece in split(t, 2000):
        assert len(piece) <= 2000


def test_every_piece_is_valid_ssml():
    for piece in split(build({0.5: 400}), 2000):
        assert ET.fromstring(piece).tag == "speak"


def test_no_content_is_lost():
    t = build({0.5: 200}, sentence="Alpha bravo charlie. ")
    joined = " ".join(re.sub(r"<[^>]+>", " ", p) for p in split(t, 2000))
    original = re.sub(r"<[^>]+>", " ", t)
    assert len(joined.split()) == len(original.split())


def test_pieces_are_not_cut_inside_a_tag():
    for piece in split(build({0.5: 400}), 2000):
        assert piece.count("<break") == piece.count("/>")


# ── 切れ目の選び方 ──────────────────────────────────────────────────────────

def test_prefers_the_longest_break_available():
    """1.5s で割れるなら、0.5s では割らない（章の途中で切らない）。"""
    # 1.5s ごとに約1,200字の塊が3つ。上限2,000ならすべて1.5sで割れる。
    t = build({1.5: 50, 1.5: 50})
    body = unwrap(build({0.5: 25})) * 3
    t = wrap('<break time="1.5s"/>'.join(
        unwrap(build({0.5: 25})) for _ in range(3)))
    pieces = split(t, 2000)
    # 各ピースの末尾が 1.5s の break で終わっている（最後を除く）
    for p in pieces[:-1]:
        last = list(re.finditer(r'time="([\d.]+)s"', p))
        assert last and last[-1].group(1) == "1.5"


def test_falls_back_to_shorter_breaks_when_needed():
    """1.5s の間隔が上限より広ければ、0.5s まで降りて割る。"""
    t = build({0.5: 400})     # 0.5s しかない
    pieces = split(t, 2000)
    assert len(pieces) > 1
    assert all(len(p) <= 2000 for p in pieces)


def test_splits_by_sentence_when_there_is_no_break():
    """break が1つも無くても、文末で割って上限に収める。"""
    t = wrap("This is a sentence. " * 300)
    pieces = split(t, 2000)
    assert len(pieces) > 1
    assert all(len(p) <= 2000 for p in pieces)
    for p in pieces:
        assert ET.fromstring(p).tag == "speak"


def test_a_single_oversized_sentence_still_fits():
    """極端に長い一文でも、上限を超えたまま返さない。"""
    t = wrap("word " * 2000)   # 文末が無い
    assert all(len(p) <= 2000 for p in split(t, 2000))


# ── 属性の書き方の揺れ ──────────────────────────────────────────────────────

@pytest.mark.parametrize("tag", [
    '<break time="1.0s"/>',
    '<break time="1.0s" />',
    '<BREAK TIME="1.0s"/>',
])
def test_break_variants_are_recognised(tag):
    body = ("This is one sentence. " * 60 + tag) * 4
    pieces = split(wrap(body), 2000)
    assert all(len(p) <= 2000 for p in pieces)


def test_merge_breaks_keeps_the_longest():
    """塊の継ぎ目で 0.5s と 1.0s が並ぶ。合成音声はそこで不自然に長く止まる。"""
    from pipeline.ssml import merge_breaks
    got = merge_breaks('a. <break time="0.5s"/><break time="1.0s"/> b. <break time="1.5s"/> c')
    assert got == 'a. <break time="1s"/> b. <break time="1.5s"/> c'


def test_merge_breaks_leaves_single_tags_alone():
    from pipeline.ssml import merge_breaks
    t = 'a. <break time="0.5s"/> b. <break time="1.0s"/> c'
    assert merge_breaks(t) == t
