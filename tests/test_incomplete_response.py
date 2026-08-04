"""打ち切られた応答の検出（llm._require_complete）。

出力上限に当たると JSON が途中で切れたまま返り、json.loads が
「Expecting value: line 6 column 72」で落ちる。原因が読み取れないので、
打ち切りの時点で検出して作り直せる失敗として投げ直す。
"""
import pytest

from pipeline import llm


class _Reason:
    def __init__(self, name):
        self.name = name


class _Candidate:
    def __init__(self, reason):
        self.finish_reason = reason


class _Resp:
    def __init__(self, candidates):
        self.candidates = candidates


def test_normal_completion_passes():
    llm._require_complete(_Resp([_Candidate(_Reason("STOP"))]))


def test_prefixed_enum_name_passes():
    llm._require_complete(_Resp([_Candidate(_Reason("FINISH_REASON_STOP"))]))


def test_missing_finish_reason_passes():
    """finish_reason を持たない応答は判断材料が無い。落とさない。"""
    llm._require_complete(_Resp([_Candidate(None)]))


@pytest.mark.parametrize("reason", ["MAX_TOKENS", "SAFETY", "RECITATION", "OTHER"])
def test_truncation_is_reported(reason):
    with pytest.raises(llm.IncompleteResponse) as e:
        llm._require_complete(_Resp([_Candidate(_Reason(reason))]))
    assert reason in str(e.value)


def test_no_candidates_is_reported():
    with pytest.raises(llm.IncompleteResponse):
        llm._require_complete(_Resp([]))


def test_it_is_a_runtime_error():
    """既存の except RuntimeError を素通りしてしまわないことの確認。"""
    assert issubclass(llm.IncompleteResponse, RuntimeError)
