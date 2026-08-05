"""完成した台本から欠陥を機械的に検出する。**書き換えはしない。**

生成時に「Xを使うな」と禁じる設計は3度失敗した。禁じた表現の代わりに別の
単一テンプレートへ収束するだけで（"caught my attention" を禁じたら
"When I first saw that figure" が5回になった）、モデルは自分の口癖を
書きながら数えられない。**完成文から数えるのは確実にできる。**

ここに置くのは、モデルを呼ばずに判定できるものだけである:

    反復フレーズ    3語以上・3回以上（禁止語リストは持たない）
    壊れたタグ      <speak> と <break> 以外、閉じ損ない
    連続 break      隣り合う間
    桁数字          読み上げが不安定になる表記
    表記揺れ        同一固有名詞の綴り違い

判断の要るもの（修辞機能の反復、文意の破綻、必須要素の有無、帰属とヘッジ）は
モデルの仕事で、pipeline/polish.py にある。
"""
import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Defect:
    """1件の欠陥。`quote` は原文に厳密一致する文字列でなければならない。

    パッチはこの `quote` を検索して当てるため、ここが原文とずれると
    当たらない（そして当たらなかったパッチは棄却される）。
    """
    category: str
    quote: str
    detail: str
    fix: str = ""
    occurrences: list[str] = field(default_factory=list)

    def as_markdown(self) -> str:
        lines = [f"### [{self.category}] {self.quote[:70]}", f"- 問題: {self.detail}"]
        if self.fix:
            lines.append(f"- 対処: {self.fix}")
        if self.occurrences:
            lines.append(f"- 出現箇所: {len(self.occurrences)}件")
            lines += [f"    - {o[:100]}" for o in self.occurrences[:6]]
        return "\n".join(lines) + "\n"


# ── 台本を読むための下ごしらえ ────────────────────────────────────────────────

_TAG = re.compile(r"<[^>]*>")
_BREAK = re.compile(r'<break\s+time\s*=\s*"[\d.]+s"\s*/>', re.I)
_VALID_TAG = re.compile(r'^(</?speak>|<break\s+time\s*=\s*"[\d.]+s"\s*/>)$', re.I)


def spoken_text(ssml: str) -> str:
    """読み上げられる部分だけを返す（タグを除いた本文）。"""
    return re.sub(r"\s+", " ", _TAG.sub(" ", ssml)).strip()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# ── 反復フレーズ ──────────────────────────────────────────────────────────────
#
# 禁止語リストは効かない。"caught my attention" を禁じたら "When I first saw that
# figure" が5回になっただけだった。**列挙するのではなく数える。**
# 3語未満は普通の言い回し（"in the"）を拾い、3回未満は偶然が混じる。

_MIN_WORDS, _MIN_HITS = 3, 3

# 数える価値のない機能語だけの並び。内容語を1つも含まない n-gram は落とす。
_FUNCTION = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "that", "this", "it", "its",
    "as", "by", "with", "from", "not", "no", "so", "than", "then", "there",
    "which", "who", "what", "when", "where", "how", "into", "out", "up",
    "has", "have", "had", "will", "would", "can", "could", "more", "most",
}


def repeated_phrases(text: str, min_words: int = _MIN_WORDS,
                     min_hits: int = _MIN_HITS) -> list[Defect]:
    """同じ言い回しの繰り返しを数える。

    長いものを優先して報告し、その一部でしかない短い n-gram は省く
    （"When I first saw that figure" を報告したら "I first saw" は要らない）。
    """
    words = text.split()
    lowered = [w.strip(".,;:!?\"'—–()").lower() for w in words]

    counts: Counter[str] = Counter()
    for size in range(min_words, min_words + 5):
        for i in range(len(lowered) - size + 1):
            gram = lowered[i:i + size]
            # 内容語が1つだけの並び（"at the same", "in the capital"）は
            # 普通の英語であって口癖ではない。2つ以上を要求する。
            if sum(1 for w in gram if w and w not in _FUNCTION) < 2:
                continue
            counts[" ".join(gram)] += 1

    hits = {g: n for g, n in counts.items() if n >= min_hits}
    # 同じ口癖から "i first saw" "when i first" "when i first saw" が同数で立つ。
    # 同じ回数なら長いほうが直す手がかりになるので、短いほうを落とす。
    # 回数が減る長いものは別の情報なので残す。
    kept = [g for g in hits
            if not any(o != g and g in o and hits[o] >= hits[g] for o in hits)]

    out: list[Defect] = []
    for gram in sorted(kept, key=lambda g: (-hits[g], g)):
        where = [s for s in sentences(text) if gram in s.lower()]
        out.append(Defect(
            category="REPEATED PHRASE",
            quote=gram,
            detail=f"同じ言い回しが {hits[gram]} 回出現します。",
            fix="口癖であれば2回まで残し、残りは別の修辞機能に置き換えるか、"
                "定型句なしで内容に入ってください。事実の側（単位・固有名詞・"
                "繰り返し出る数量）であれば、言い換えずにそのままにしてください。",
            occurrences=where,
        ))
    return out


# ── SSML と表記 ───────────────────────────────────────────────────────────────

def broken_tags(ssml: str) -> list[Defect]:
    out = []
    for m in _TAG.finditer(ssml):
        if not _VALID_TAG.match(m.group()):
            out.append(Defect("BROKEN TAG", m.group(),
                              "SSML として許可されないか、壊れているタグです。",
                              "<speak> と <break time=\"Xs\"/> 以外は読み上げられます。削除してください。"))
    tail = _TAG.sub("", ssml)
    if "<" in tail:
        frag = tail[tail.index("<"):][:40]
        out.append(Defect("BROKEN TAG", frag, "閉じられていないタグの断片です。", "削除してください。"))
    return out


def double_breaks(ssml: str) -> list[Defect]:
    return [Defect("DOUBLE BREAK", m.group(), "間が連続しています。",
                   "長いほうだけを残してください。")
            for m in re.finditer(rf"{_BREAK.pattern}\s*{_BREAK.pattern}", ssml, re.I)]


# 型番のように公式表記に数字を含むものも、合成音声は誤読する（S-400 →「S マイナス400」）。
# 例外を設けず、本文に現れる数字はすべて報告する。
_DIGIT = re.compile(r"\S*\d\S*")


def digits_in_speech(text: str) -> list[Defect]:
    out = []
    for s in sentences(text):
        for m in _DIGIT.finditer(s):
            out.append(Defect("DIGITS", m.group(),
                              "読み上げられる本文に数字が残っています。",
                              "話す通りの綴りにしてください（176,000 → one hundred seventy-six thousand、"
                              "S-400 → S-four-hundred）。",
                              occurrences=[s]))
    return out


# ── 固有名詞の表記揺れ ────────────────────────────────────────────────────────

_PROPER = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|of|the|and))*\s+[A-Z][a-z]+\b")
_LEADING = {"the", "a", "an", "this", "that", "these", "those", "it", "its", "but",
            "and", "if", "when", "while", "in", "on", "at", "for", "by", "from",
            "with", "as", "so", "then", "now", "here", "there", "his", "her",
            "their", "our", "no", "not", "both", "each", "more", "most"}


def proper_nouns(text: str) -> Counter[str]:
    seen: Counter[str] = Counter()
    for m in _PROPER.finditer(text):
        words = m.group().split()
        # 文頭の語は固有名詞でなくても大文字になる（"Later the Balzi Rossi"）。
        # 冠詞が2語目にあるなら1語目は名前の一部ではない。"of" と "and" は
        # 名前の内側に来る（"Bank of Russia"）ので落とさない。
        while len(words) > 2 and (words[0].lower() in _LEADING
                                  or words[1].lower() == "the"):
            words.pop(0)
        if len(words) >= 2 and words[0].lower() not in _LEADING:
            seen[" ".join(words)] += 1
    return seen


def _edit_distance(a: str, b: str) -> int:
    """2語の編集距離。表記揺れは1〜2文字しか違わない。"""
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def name_variants(text: str) -> list[Defect]:
    """同じものを指していそうな綴り違いを探す（Balzi Rossi / Balti Rossi）。"""
    names = proper_nouns(text)
    out, done = [], set()
    for a in names:
        for b in names:
            if a >= b or (a, b) in done:
                continue
            done.add((a, b))
            if 0 < _edit_distance(a.lower(), b.lower()) <= 2:
                keep, drop = (a, b) if names[a] >= names[b] else (b, a)
                out.append(Defect("NAME VARIANT", drop,
                                  f"「{a}」({names[a]}回) と「{b}」({names[b]}回) が混在しています。",
                                  f"多いほうの「{keep}」に統一してください。"))
    return out


# ── まとめ ────────────────────────────────────────────────────────────────────

def scan(ssml: str) -> list[Defect]:
    """モデルを呼ばずに見つかる欠陥をすべて返す。"""
    body = spoken_text(ssml)
    return (broken_tags(ssml) + double_breaks(ssml) + digits_in_speech(body)
            + name_variants(body) + repeated_phrases(body))
