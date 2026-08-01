"""音声分割の切れ目 — 文の途中で切らないこと。

25MB を超える音声は分割して送るしかないが、時間で機械的に等分すると
文の途中で切れ、その文が両側で欠けたり重複したりする。
目標時刻の近くに無音があればそこへ寄せる。
"""
from pipeline.llm import _split_times

DURATION = 2160.0  # 36分


def test_no_split_point_for_a_single_chunk():
    assert _split_times(DURATION, 1, []) == []


def test_falls_back_to_even_division_without_silence():
    """無音が1つも見つからなければ等分のまま（分割自体は成立させる）。"""
    assert _split_times(DURATION, 2, []) == [1080.0]


def test_three_chunks_give_two_split_points():
    assert len(_split_times(DURATION, 3, [])) == 2


def test_snaps_to_a_nearby_silence():
    """等分点 1080 の近くに無音 1075 があればそちらを使う。"""
    assert _split_times(DURATION, 2, [1075.0]) == [1075.0]


def test_picks_the_closest_silence():
    assert _split_times(DURATION, 2, [1000.0, 1075.0, 1160.0]) == [1075.0]


def test_ignores_silence_that_is_too_far():
    """遠い無音へ寄せるとチャンクの長さが偏り、上限を超えかねない。"""
    # 許容幅は seg*0.15 と 30秒の小さい方 = 30秒。100秒離れた無音は使わない。
    assert _split_times(DURATION, 2, [980.0]) == [1080.0]


def test_tolerance_is_capped_at_30_seconds():
    assert _split_times(DURATION, 2, [1049.0]) == [1080.0]   # 31秒離れ → 不採用
    assert _split_times(DURATION, 2, [1051.0]) == [1051.0]   # 29秒離れ → 採用


def test_tolerance_shrinks_for_short_segments():
    """短い音声では 30秒 ではなく seg*0.15 が効く。"""
    # 100秒を2分割 → seg=50、許容は 7.5秒
    assert _split_times(100.0, 2, [44.0]) == [44.0]   # 6秒離れ → 採用
    assert _split_times(100.0, 2, [40.0]) == [50.0]   # 10秒離れ → 不採用（等分のまま）


def test_each_split_point_is_chosen_independently():
    """片方だけ無音がある場合、もう片方は等分のまま。"""
    assert _split_times(DURATION, 3, [715.0]) == [715.0, 1440.0]


def test_split_points_stay_in_order():
    times = _split_times(DURATION, 4, [530.0, 1075.0, 1630.0])
    assert times == sorted(times)
