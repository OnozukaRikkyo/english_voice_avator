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

# 用語集の項目は行頭の "- **見出し語** — 説明" 形式。
# 説明文中の **強調** まで拾うと、辞書の見出しでない語句が大量に混ざる
# （実測: 見出し21件に対し61件を抽出し、29件が説明文からの巻き込みだった）。
_ENTRY = re.compile(r"^[-*]\s+\*\*(.+?)\*\*", re.M)

# 1項目に複数の見出しが並ぶことがある:
#   "FP-5 Flamingo, FP-7, and FP-9"
#   "Antipinsky Oil Refinery / Tyumen Oil Refinery branch"
#   "Partial mobilization, conscription, contract soldiers, and mobilization"
# これらは個別の語に割る。まとめて1語として渡しても綴りの矯正に効かない。
_SPLIT = re.compile(r"\s*/\s*|\s*,\s*(?:and\s+)?|\s+and\s+")

# 見出しが用語ではなく説明である場合を除く
#   "Ethnic slur in the quoted Russian post" ← これは指示であって用語ではない
_NOT_A_TERM = re.compile(
    r"^(Auto-generated|Verify|Use\b|Do not|Explain|Prefer|Treat|Keep|Retain|"
    r"Ethnic slur|Note\b|Important\b)", re.I
)

# 固有名詞・型式名らしさ（綴りの矯正効果が大きいものを優先する）
_LOOKS_PROPER = re.compile(r"[A-Z][a-z]|[0-9]|-")


def _clean(term: str) -> str:
    """引用符・末尾の句点を落とす。

    見出しを分割すると片方の引用符だけが残ることがあるため、
    端だけでなく全ての引用符を除く（例: 'Russian "Z-universe' → 'Russian Z-universe'）。
    """
    return re.sub(r"[“”\"'’]", "", term).strip().rstrip(".").strip()


def _terms_from_prompt(text: str) -> list[str]:
    """NotebookLM プロンプト1本から用語集の見出し語を抜き出す。

    説明文の強調は拾わず、複合見出しは個別の語に割る。
    """
    if _SECTION_START not in text:
        return []
    body = text[text.index(_SECTION_START):]
    if _SECTION_END in body:
        body = body[: body.index(_SECTION_END)]

    out: list[str] = []
    for head in _ENTRY.findall(body):
        head = _clean(head)
        if not head or _NOT_A_TERM.match(head):
            continue
        for part in _SPLIT.split(head):
            part = _clean(part)
            # 冠詞始まりは音声中に出る形ではないので落とす
            if part.lower().startswith(("the ", "a ", "an ")):
                part = part.split(" ", 1)[1].strip()
            if len(part) >= 2:
                out.append(part)
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

    # 予算を超えるときは、固有名詞・型式名を先に確保する。
    # 地名や兵器名の綴りこそ矯正したい対象で、"gray zone" のような
    # 一般語は書き起こしを誤らないため後回しでよい。
    # 実測で FP-5 Flamingo / FP-7 / FP-9 が予算切れで落ちていた。
    order = {t: i for i, t in enumerate(uniq)}
    priority = sorted(uniq, key=lambda t: (0 if _LOOKS_PROPER.search(t) else 1, len(t)))

    picked: list[str] = []
    total = 0
    for t in priority:
        if total + len(t) + 2 > max_chars:
            continue          # 短い語なら入るかもしれないので打ち切らない
        picked.append(t)
        total += len(t) + 2

    # 資料での登場順に戻して返す
    return ", ".join(sorted(picked, key=lambda t: order[t]))
