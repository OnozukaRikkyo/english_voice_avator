"""config.resolve_models() — 工程ごとに使うモデルを決める処理。

優先順位は 個別指定 > プリセット > .env > config.py の既定値。
"""
import pytest

from pipeline.config import MODEL_SLOTS, PRESETS, current_models, resolve_models


def test_no_argument_returns_the_configured_defaults():
    assert resolve_models() == current_models()


def test_every_slot_is_covered_by_every_preset():
    """プリセットに漏れがあると、その工程だけ切り替わらない。"""
    for name, preset in PRESETS.items():
        assert set(preset) == set(MODEL_SLOTS), f"{name} preset のスロットが不一致"


def test_openai_preset_sends_every_step_to_openai():
    for slot, model in resolve_models("openai").items():
        assert model.startswith("gpt-"), f"{slot} が OpenAI 経路でない: {model}"


def test_gemini_preset_sends_no_step_to_openai():
    for slot, model in resolve_models("gemini").items():
        assert not model.startswith("gpt-"), f"{slot} が Gemini 経路でない: {model}"


def test_per_step_override_beats_the_preset():
    models = resolve_models("openai", rewrite="gemini-3.6-flash")
    assert models["rewrite"] == "gemini-3.6-flash"
    assert models["translate"].startswith("gpt-")


def test_per_step_override_works_without_a_preset():
    assert resolve_models(rewrite="gpt-5.6-luna")["rewrite"] == "gpt-5.6-luna"


def test_none_override_is_ignored():
    """CLI で未指定のフラグは None で渡ってくる。既定値を潰してはいけない。"""
    assert resolve_models(rewrite=None) == current_models()


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="未知のプロバイダ"):
        resolve_models("claude")


def test_unknown_slot_is_rejected():
    with pytest.raises(ValueError, match="未知のスロット"):
        resolve_models(None, transcribe_english="gemini-3.6-flash")
