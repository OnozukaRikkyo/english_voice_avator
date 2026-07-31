"""APIエラーの分類 — 本物の障害だけを止め、無関係な数字では止まらないこと。

以前は例外メッセージに "401" や "400" が含まれるかだけで判定していたため、
動画IDやモデル名にたまたま同じ数字が入っただけで「APIキーが無効です」と
誤って停止する可能性があった。
"""
import pytest

from pipeline.api_status import status_code
from pipeline.gemini_client import GeminiApiError
from pipeline.gemini_client import check_api_error as check_gemini
from pipeline.openai_client import OpenAiApiError
from pipeline.openai_client import check_api_error as check_openai


class WithStatus(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.status_code = code


class WithResponse(Exception):
    def __init__(self, code):
        super().__init__("wrapped")
        self.response = type("R", (), {"status_code": code})()


# ── ステータスコードの取り出し ──────────────────────────────────────────────

def test_status_code_from_attribute():
    assert status_code(WithStatus(429)) == 429


def test_status_code_from_nested_response():
    assert status_code(WithResponse(503)) == 503


def test_status_code_from_numeric_string():
    e = Exception("x")
    e.code = "403"
    assert status_code(e) == 403


def test_status_code_absent_returns_none():
    assert status_code(RuntimeError("just a message")) is None


def test_boolean_is_not_mistaken_for_a_code():
    """bool は int のサブクラス。True を 1 と読んではいけない。"""
    e = Exception("x")
    e.code = True
    assert status_code(e) is None


# ── 本物の障害は止める ──────────────────────────────────────────────────────

def test_openai_auth_error_is_fatal():
    with pytest.raises(OpenAiApiError, match="APIキーが無効"):
        check_openai(WithStatus(401))


def test_openai_rate_limit_is_fatal():
    with pytest.raises(OpenAiApiError, match="レート制限"):
        check_openai(WithStatus(429))


def test_openai_server_error_is_fatal():
    with pytest.raises(OpenAiApiError, match="サーバーエラー"):
        check_openai(WithStatus(502))


def test_gemini_permission_error_is_fatal():
    with pytest.raises(GeminiApiError, match="アクセス権限"):
        check_gemini(WithStatus(403))


def test_gemini_recognises_its_own_error_words():
    with pytest.raises(GeminiApiError, match="レート制限"):
        check_gemini(RuntimeError("RESOURCE_EXHAUSTED: too many requests"))


def test_gemini_quota_wording_is_fatal():
    with pytest.raises(GeminiApiError, match="quota"):
        check_gemini(RuntimeError("You exceeded your current quota"))


# ── 無関係な数字では止めない ────────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "video_id=abc401def not found",
    "model gpt-400-turbo is unknown",
    "file /data/429/audio.mp3 missing",
    "processed 500 items",
])
def test_unrelated_numbers_do_not_trigger(message):
    e = RuntimeError(message)
    check_openai(e)   # 例外が飛ばなければ合格
    check_gemini(e)


def test_a_plain_error_passes_through():
    """分類できないものは握り潰さず、呼び出し元の raise に任せる。"""
    check_openai(ValueError("something went wrong"))
    check_gemini(ValueError("something went wrong"))


# ── reasoning 非対応モデルの検出 ────────────────────────────────────────────

class BadRequest(Exception):
    """OpenAI SDK の BadRequestError を模したもの。"""

    def __init__(self, code, param, msg="bad request"):
        super().__init__(msg)
        self.status_code = 400
        self.code = code
        self.param = param


def test_unsupported_reasoning_is_detected():
    """gpt-4.1-mini に effort を渡したときに実際に返る形。"""
    from pipeline.llm import is_unsupported_reasoning
    assert is_unsupported_reasoning(BadRequest("unsupported_parameter", "reasoning.effort"))


def test_detection_reads_the_body_when_attributes_are_absent():
    from pipeline.llm import is_unsupported_reasoning
    e = Exception("bad request")
    e.status_code = 400
    e.body = {"code": "unsupported_parameter", "param": "reasoning.effort"}
    assert is_unsupported_reasoning(e)


def test_detection_reads_a_nested_error_body():
    from pipeline.llm import is_unsupported_reasoning
    e = Exception("bad request")
    e.status_code = 400
    e.body = {"error": {"code": "unsupported_parameter", "param": "reasoning.effort"}}
    assert is_unsupported_reasoning(e)


def test_a_different_400_is_not_retried():
    """不正なモデル名などは reasoning を外しても直らない。再試行してはいけない。"""
    from pipeline.llm import is_unsupported_reasoning
    assert not is_unsupported_reasoning(BadRequest("model_not_found", "model"))


def test_unsupported_parameter_on_another_field_is_not_retried():
    from pipeline.llm import is_unsupported_reasoning
    assert not is_unsupported_reasoning(BadRequest("unsupported_parameter", "temperature"))


def test_a_429_is_not_treated_as_unsupported_reasoning():
    from pipeline.llm import is_unsupported_reasoning
    assert not is_unsupported_reasoning(WithStatus(429))


def test_message_wording_alone_does_not_trigger_a_retry():
    """文言依存をやめたことの回帰テスト。"""
    from pipeline.llm import is_unsupported_reasoning
    assert not is_unsupported_reasoning(
        RuntimeError("reasoning is not supported with this model")
    )
