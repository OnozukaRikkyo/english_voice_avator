"""SSML 台本の分割。

HeyGen の入力上限は 5,000 字。rewrite が作る台本パートはこれを超えることがある
（実測で 6,416〜9,483 字）ので、送る前に上限以下へ割り直す。

切る場所は `<break time="Xs"/>` に合わせる。rewrite のプロンプトが
間の長さを意味づけているため、そのまま話題の切れ目として使える。

    1.5s  章の転換（フック→本文、本文→結び）  ← 最も切りたい場所
    1.0s  段落・話題の変わり目
    0.5s  文と文の間

長い間を優先して切ることで、章の途中で動画が変わるのを避ける。
"""
import re

# <break time="1.5s"/> の time を取り出す。属性の書き方の揺れを許容する。
_BREAK = re.compile(r'<break\s+time\s*=\s*"([\d.]+)s"\s*/>', re.I)
_SPEAK_OPEN = re.compile(r"^\s*<speak>\s*", re.I)
_SPEAK_CLOSE = re.compile(r"\s*</speak>\s*$", re.I)

_WRAPPER = "<speak>\n\n</speak>"   # 包み直す分の文字数


# 台本に許すタグは <speak> と <break time="Xs"/> だけ。HeyGen が他のタグを
# 解釈する保証がなく、解釈されないタグはそのまま読み上げられる。
# 実害の例: `<break time="0.5s/>`（閉じ引用符欠落）が検証を通過して
# 最終台本まで残った。形の崩れたタグは _BREAK にも一致しないため、
# 「正しい break を数える」検証では見つけられない。タグ様のもの全体を見る。
_TAG = re.compile(r"<[^>]*>")
_VALID_TAG = re.compile(r'^(</?speak>|<break\s+time\s*=\s*"[\d.]+s"\s*/>)$', re.I)


def check_tags(text: str) -> str | None:
    """SSML として不正なタグがあれば説明を、無ければ None を返す。"""
    for m in _TAG.finditer(text):
        if not _VALID_TAG.match(m.group(0)):
            return f"許可されないタグまたは壊れたタグ: {m.group(0)!r}"
    # 「<」で始まって「>」に至らないタグの断片（出力の途中切れで起きる）
    tail = _TAG.sub("", text)
    if "<" in tail:
        frag = tail[tail.index("<"):][:40]
        return f"閉じられていないタグの断片: {frag!r}"
    return None


def merge_breaks(text: str) -> str:
    """隣り合う <break> を1つにまとめる（長いほうを残す）。

    間の指定はプロンプトで禁じているが、モデルは塊の継ぎ目で重ねてしまう
    （文末の 0.5s と話題の変わり目の 1.0s が並ぶ）。合成音声はそこで不自然に
    長く止まる。決定論的に潰せるものをモデルに任せる理由がない。
    """
    def longest(m: "re.Match[str]") -> str:
        secs = [float(x) for x in re.findall(r'time\s*=\s*"([\d.]+)s"', m.group(), re.I)]
        return f'<break time="{max(secs):g}s"/>'

    _TAGS = r'<break\s+time\s*=\s*"[\d.]+s"\s*/>'
    return re.sub(rf'{_TAGS}(?:\s*{_TAGS})+', longest, text, flags=re.I)


def unwrap(text: str) -> str:
    """<speak> の中身を返す。"""
    return _SPEAK_CLOSE.sub("", _SPEAK_OPEN.sub("", text.strip())).strip()


def wrap(body: str) -> str:
    return f"<speak>\n{body.strip()}\n</speak>"


def _segments(body: str) -> list[tuple[str, float]]:
    """本文を「テキスト + 直後の break」の組に分ける。

    返すのは (その区間の文字列, 直後の break の秒数) の並び。
    最後の区間には break が続かないので 0.0 を入れる。
    """
    out: list[tuple[str, float]] = []
    pos = 0
    for m in _BREAK.finditer(body):
        out.append((body[pos:m.end()], float(m.group(1))))
        pos = m.end()
    tail = body[pos:]
    if tail.strip():
        out.append((tail, 0.0))
    return out


def split(text: str, max_chars: int) -> list[str]:
    """SSML 台本を max_chars 以下の妥当な SSML の並びに割る。

    上限に収まっていれば、そのまま1件返す（無駄に割らない）。
    break が1つも無く上限を超える場合は、文末で割る。
    """
    if len(text) <= max_chars:
        return [text]

    body = unwrap(text)
    budget = max_chars - len(_WRAPPER)
    segments = _segments(body)

    # break が無い、または区間が1つしかないなら文末で割るしかない
    if len(segments) <= 1:
        return [wrap(p) for p in _split_by_sentence(body, budget)]

    # 大きい間から順に試し、全て上限に収まる切り方が見つかった時点で採用する。
    # 1.5s だけで割れれば章の境界が保たれ、足りなければ段落・文へ降りる。
    for threshold in (1.5, 1.0, 0.5, 0.0):
        pieces = _greedy(segments, budget, threshold)
        if pieces and all(len(p) <= budget for p in pieces):
            return [wrap(p) for p in pieces]

    # どの間で割っても収まらない区間がある（極端に長い一文など）
    pieces = _greedy(segments, budget, 0.0)
    out: list[str] = []
    for p in pieces:
        out.extend(_split_by_sentence(p, budget) if len(p) > budget else [p])
    return [wrap(p) for p in out]


def _greedy(segments: list[tuple[str, float]], budget: int, threshold: float) -> list[str]:
    """threshold 以上の break だけを切れ目の候補として、詰められるだけ詰める。"""
    pieces: list[str] = []
    current = ""
    for chunk, gap in segments:
        current += chunk
        # ここで切れる（十分長い間がある）かつ、次を足すと溢れるなら切る
        if gap >= threshold > 0 and len(current) >= budget * 0.5:
            pieces.append(current)
            current = ""
        elif len(current) > budget:
            # 溢れた。直前の候補位置が無かったので、ここで切る
            pieces.append(current)
            current = ""
    if current.strip():
        pieces.append(current)
    return [p.strip() for p in pieces if p.strip()]


def _split_by_sentence(body: str, budget: int) -> list[str]:
    """break が使えないときの最後の手段。文末で割り、それでも余るなら語で割る。"""
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        if current and len(current) + len(sentence) + 1 > budget:
            parts.append(current.strip())
            current = ""
        current += (" " if current else "") + sentence
    if current.strip():
        parts.append(current.strip())

    # 文末記号が無い、または一文が長すぎる場合は語の切れ目で割る。
    # ここを省くと上限を超えたまま返してしまう。
    out: list[str] = []
    for p in parts:
        while len(p) > budget:
            cut = p.rfind(" ", 0, budget)
            cut = cut if cut > 0 else budget      # 空白すら無ければ字数で割る
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or [body[:budget]]
