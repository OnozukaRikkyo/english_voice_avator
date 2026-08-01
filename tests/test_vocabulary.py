"""文字起こしに渡す用語ヒントの収集。

NotebookLM プロンプトの用語集を抜き出して gpt-transcribe の prompt に渡すと、
固有名詞の綴りが安定する（実測で "Kostyantynivka" → "Kostiantynivka"）。
"""
from pipeline.vocabulary import _terms_from_prompt

PROMPT = """\
You are a senior OSINT analyst.

## Document-Specific Vocabulary Guide

### Auto-generated from source document — verify before use

- **Huliaipole** — Use the Ukrainian transliteration, located in **Zaporizhzhia Oblast**.
- **Antipinsky Oil Refinery / Tyumen Oil Refinery branch** — The Japanese phrase may be ambiguous.
- **Kostiantynivka** — the Ukrainian transliteration of the frontline city.
- **Verify at** — https://example.com/
- **Do not use this** — an instruction, not a term.

## Core Instructions

Use **Google Search** actively before drafting.
"""


def test_extracts_bolded_terms():
    terms = _terms_from_prompt(PROMPT)
    assert "Huliaipole" in terms
    assert "Kostiantynivka" in terms
    assert "Zaporizhzhia Oblast" in terms


def test_keeps_only_the_first_of_a_slash_pair():
    """「A / B」は最初の表記だけ。両方入れても綴り矯正の役に立たない。"""
    terms = _terms_from_prompt(PROMPT)
    assert "Antipinsky Oil Refinery" in terms
    assert not any("/" in t for t in terms)


def test_stops_at_core_instructions():
    """用語集の外にある強調語（Google Search）を拾わない。"""
    assert "Google Search" not in _terms_from_prompt(PROMPT)


def test_drops_instruction_lines():
    terms = _terms_from_prompt(PROMPT)
    assert "Verify at" not in terms
    assert "Do not use this" not in terms


def test_drops_the_section_subheading():
    assert not any(t.startswith("Auto-generated") for t in _terms_from_prompt(PROMPT))


def test_returns_nothing_without_a_vocabulary_section():
    assert _terms_from_prompt("A prompt with no vocabulary guide at all.") == []


def test_hint_is_empty_when_there_is_no_vocabulary():
    from pipeline.llm import _vocab_hint
    assert _vocab_hint("") == ""
    assert _vocab_hint("   ") == ""


def test_hint_embeds_the_terms():
    from pipeline.llm import _vocab_hint
    assert "Huliaipole" in _vocab_hint("Huliaipole, Stepnohirsk")


def test_collect_respects_the_character_budget(monkeypatch, tmp_path):
    """prompt が長すぎると効きが落ちるため上限で切る。"""
    from pipeline import vocabulary
    monkeypatch.setattr(vocabulary, "PROMPTS_DIR", tmp_path / "none")
    manual = tmp_path / "vocabulary.txt"
    manual.write_text("\n".join(f"term{i:03d}" for i in range(500)), encoding="utf-8")
    monkeypatch.setattr(vocabulary, "MANUAL_FILE", manual)
    assert len(vocabulary.collect(max_chars=100)) <= 100


def test_collect_is_empty_when_nothing_is_available(monkeypatch, tmp_path):
    from pipeline import vocabulary
    monkeypatch.setattr(vocabulary, "PROMPTS_DIR", tmp_path / "none")
    monkeypatch.setattr(vocabulary, "MANUAL_FILE", tmp_path / "none.txt")
    assert vocabulary.collect() == ""
