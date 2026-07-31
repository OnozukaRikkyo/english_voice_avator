"""slugify() — 音声ファイル名からプロジェクト名を作る処理。

区切り文字を潰すため別名でも同じスラグになりうる。その事実をテストで固定し、
衝突を検出する側（run_pipeline._scan_inbox）が必要であることを示す。
"""
from pipeline.config import slugify


def test_ascii_is_preserved():
    assert slugify("NATO_Summit_2026") == "NATO_Summit_2026"


def test_spaces_and_hyphens_become_underscores():
    assert slugify("NATO Summit June-2026") == "NATO_Summit_June_2026"


def test_runs_of_separators_collapse():
    assert slugify("a -- b") == "a_b"


def test_leading_and_trailing_separators_are_stripped():
    assert slugify("_-a b-_") == "a_b"


def test_smart_quotes_are_dropped():
    assert slugify("Russia’s_Map_Lie") == "Russias_Map_Lie"


def test_non_ascii_falls_back_to_hash():
    out = slugify("中東情勢レポート")
    assert len(out) == 8 and out.isalnum() and out.isascii()


def test_non_ascii_fallback_is_stable():
    assert slugify("中東情勢レポート") == slugify("中東情勢レポート")


def test_different_non_ascii_give_different_slugs():
    assert slugify("中東情勢") != slugify("欧州情勢")


def test_separator_variants_collide():
    """区切り文字だけが違う名前は同じスラグになる。

    これは仕様。だからこそ _scan_inbox が衝突を検出しなければならない。
    """
    assert slugify("a-b") == slugify("a_b") == slugify("a b") == "a_b"
