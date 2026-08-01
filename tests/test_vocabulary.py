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
- **FP-5 Flamingo, FP-7, and FP-9** — do not collapse these into one category.
- **Ethnic slur in the quoted Russian post** — an instruction, not a term.
- **Verify at** — https://example.com/
- **Do not use this** — an instruction, not a term.

## Core Instructions

Use **Google Search** actively before drafting. The **refinery yield** matters.
"""


def test_extracts_the_headwords():
    """行頭の "- **見出し語**" だけを拾う。"""
    terms = _terms_from_prompt(PROMPT)
    assert "Huliaipole" in terms
    assert "Kostiantynivka" in terms
    # Zaporizhzhia Oblast は Huliaipole の説明文中の強調であり、見出しではない
    assert "Zaporizhzhia Oblast" not in terms


def test_splits_a_slash_pair_into_separate_terms():
    """「A / B」は両方が音声に出うるので個別に渡す。"""
    terms = _terms_from_prompt(PROMPT)
    assert "Antipinsky Oil Refinery" in terms
    assert "Tyumen Oil Refinery branch" in terms
    assert not any("/" in t for t in terms)


def test_splits_a_comma_and_list_into_separate_terms():
    """"FP-5 Flamingo, FP-7, and FP-9" をまとめて渡しても綴り矯正に効かない。"""
    terms = _terms_from_prompt(PROMPT)
    for t in ("FP-5 Flamingo", "FP-7", "FP-9"):
        assert t in terms, t


def test_ignores_bold_inside_explanations():
    """説明文の強調は辞書の見出しではない（実測で29件が混入していた）。"""
    terms = _terms_from_prompt(PROMPT)
    assert "refinery yield" not in terms


def test_drops_a_headword_that_is_an_instruction():
    terms = _terms_from_prompt(PROMPT)
    assert not any(t.startswith("Ethnic slur") for t in terms)


def test_strips_leading_articles():
    """音声には "the ..." の形では出ない。"""
    assert not any(t.lower().startswith("the ") for t in _terms_from_prompt(PROMPT))


def test_strips_quotes_anywhere_in_a_term():
    """見出しを分割すると片方の引用符だけ残ることがある。"""
    from pipeline.vocabulary import _clean
    assert _clean('Russian "Z-universe') == "Russian Z-universe"


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


def test_proper_nouns_survive_a_tight_budget(monkeypatch, tmp_path):
    """予算切れで固有名詞が落ちてはいけない（実測で FP-5 Flamingo が落ちていた）。"""
    from pipeline import vocabulary
    monkeypatch.setattr(vocabulary, "PROMPTS_DIR", tmp_path / "none")
    manual = tmp_path / "vocabulary.txt"
    manual.write_text("gray zone\nmartial law\nFP-5 Flamingo\nHuliaipole\n", encoding="utf-8")
    monkeypatch.setattr(vocabulary, "MANUAL_FILE", manual)
    got = vocabulary.collect(max_chars=32)
    assert "FP-5 Flamingo" in got or "Huliaipole" in got


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
