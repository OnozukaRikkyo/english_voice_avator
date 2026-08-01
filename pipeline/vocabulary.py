"""文字起こしに渡す用語ヒントを集める。

NotebookLM プロンプト（data/senario_jp/prompts/*_prompt.txt）には
「Document-Specific Vocabulary Guide」があり、資料に出てくる固有名詞の
正式な英語表記が Web 検索で確認済みの状態で並んでいる。
音声はその資料から作られているので、同じ語が出てくる。

gpt-transcribe の prompt パラメータは公式に
「製品名・専門用語・略語を正しく書き起こす」ための用途とされている。
用語集をそこへ渡すと綴りが安定する（実測で "Kostyantynivka" が
用語集どおりの "Kostiantynivka" に矯正された）。

自前で用語集を書きたい場合は data/senario_jp/vocabulary.txt に
1行1語で置く。プロンプトから抽出したものと合わせて使う。
"""
import re
from pathlib import Path

from .config import DATA

PROMPTS_DIR = DATA / "senario_jp" / "prompts"
MANUAL_FILE = DATA / "senario_jp" / "vocabulary.txt"

# gpt-transcribe の prompt は長すぎると効きが落ちるため上限を設ける
MAX_CHARS = 900

# 用語集セクションの見出し。ここから Core Instructions までを対象にする。
_SECTION_START = "Vocabulary Guide"
_SECTION_END = "## Core Instructions"

# **term** で強調された語を拾う
_BOLD = re.compile(r"\*\*([^*\n]{2,60})\*\*")

# 用語ではない見出し・説明文を除く
_NOT_A_TERM = re.compile(r"^(Auto-generated|Verify|Use |Do not|Explain|Prefer|Treat|Keep|Retain)", re.I)


def _terms_from_prompt(text: str) -> list[str]:
    """NotebookLM プロンプト1本から用語を抜き出す。"""
    if _SECTION_START not in text:
        return []
    body = text[text.index(_SECTION_START):]
    if _SECTION_END in body:
        body = body[: body.index(_SECTION_END)]
    out = []
    for t in _BOLD.findall(body):
        t = t.strip().strip("“”\"'")
        # 「A / B」形式は最初の表記だけ採る（両方入れると冗長）
        t = t.split(" / ")[0].strip()
        if t and not _NOT_A_TERM.match(t):
            out.append(t)
    return out


def collect(max_chars: int = MAX_CHARS) -> str:
    """使える用語をカンマ区切りで返す。無ければ空文字。

    重複は最初の出現を残して除き、短い語から詰めて max_chars に収める
    （長い説明的な語より、地名・型式名のような短い固有名詞のほうが
    綴り矯正の効果が大きいため）。
    """
    terms: list[str] = []

    if MANUAL_FILE.exists():
        terms += [ln.strip() for ln in MANUAL_FILE.read_text(encoding="utf-8").splitlines()]

    if PROMPTS_DIR.is_dir():
        for p in sorted(PROMPTS_DIR.glob("*_prompt.txt")):
            terms += _terms_from_prompt(p.read_text(encoding="utf-8"))

    seen: set[str] = set()
    uniq: list[str] = []
    for t in terms:
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)

    picked: list[str] = []
    total = 0
    for t in sorted(uniq, key=len):
        if total + len(t) + 2 > max_chars:
            break
        picked.append(t)
        total += len(t) + 2

    # 元の並び（資料での登場順）に戻して返す
    order = {t: i for i, t in enumerate(uniq)}
    return ", ".join(sorted(picked, key=lambda t: order[t]))
