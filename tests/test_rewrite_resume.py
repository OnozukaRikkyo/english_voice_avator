"""途中で失敗した rewrite の扱い。

長い transcript は塊ごとにAPIを呼ぶ。7塊のうち2塊で落ちると、
パートは2件だけディスクに残る。この状態を「生成済み」と判定してしまうと、
欠けた台本が翻訳と動画生成まで流れる。

進捗の記録ファイルが残っている間は未完成として扱う。
"""
import json

from pipeline import rewrite


def _write_state(d, stem, **kw):
    p = rewrite.state_path(d, stem)
    p.write_text(json.dumps(kw), encoding="utf-8")
    return p


def test_no_state_file_means_complete(tmp_path):
    assert rewrite._load_state(rewrite.state_path(tmp_path, "x"), 7, 45862) is None


def test_state_is_read_back(tmp_path):
    _write_state(tmp_path, "x", chunks=7, src_chars=45862, done=2, parts=["a.txt", "b.txt"])
    state = rewrite._load_state(rewrite.state_path(tmp_path, "x"), 7, 45862)
    assert state["done"] == 2
    assert state["parts"] == ["a.txt", "b.txt"]


def test_state_is_discarded_when_the_transcript_changed(tmp_path):
    """文字起こしをやり直すと分割位置が変わる。前回のパートは繋がらない。"""
    _write_state(tmp_path, "x", chunks=7, src_chars=45862, done=2, parts=["a.txt"])
    assert rewrite._load_state(rewrite.state_path(tmp_path, "x"), 7, 30000) is None


def test_state_is_discarded_when_the_chunk_count_changed(tmp_path):
    _write_state(tmp_path, "x", chunks=7, src_chars=45862, done=2, parts=["a.txt"])
    assert rewrite._load_state(rewrite.state_path(tmp_path, "x"), 6, 45862) is None


def test_state_is_discarded_when_all_chunks_are_done(tmp_path):
    """done == chunks は完成。記録は消されているはずで、残っていても再開しない。"""
    _write_state(tmp_path, "x", chunks=7, src_chars=45862, done=7, parts=["a.txt"])
    assert rewrite._load_state(rewrite.state_path(tmp_path, "x"), 7, 45862) is None


def test_broken_state_file_is_ignored(tmp_path):
    rewrite.state_path(tmp_path, "x").write_text("{ not json", encoding="utf-8")
    assert rewrite._load_state(rewrite.state_path(tmp_path, "x"), 7, 45862) is None


def test_save_then_load_round_trip(tmp_path):
    parts = [tmp_path / "s_part01.txt", tmp_path / "s_part02.txt"]
    rewrite._save_state(rewrite.state_path(tmp_path, "s"),
                        chunks=7, src_chars=45862, done=2, parts=parts)
    state = rewrite._load_state(rewrite.state_path(tmp_path, "s"), 7, 45862)
    assert state["parts"] == ["s_part01.txt", "s_part02.txt"]


def test_state_file_is_not_mistaken_for_a_part(tmp_path):
    """結合処理は *_part*.txt を集める。記録ファイルが混ざってはならない。"""
    rewrite._save_state(rewrite.state_path(tmp_path, "s"),
                        chunks=7, src_chars=1, done=2, parts=[])
    (tmp_path / "s_part01.txt").write_text("x", encoding="utf-8")
    assert [f.name for f in sorted(tmp_path.glob("*_part*.txt"))] == ["s_part01.txt"]
