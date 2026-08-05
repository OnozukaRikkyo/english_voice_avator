"""Stage draft→narration: 台本を「放送できるニュース解説か」の観点で点検して直す。

rewrite が書いた台本は読み物としては整っていても、報道としては危うい箇所を含む。
文字起こしに無い数字を足す、"reportedly" が落ちて推測が断定になる、片方の当事者の
主張が地の文になる、見出し的な煽り語が混ざる — いずれも読み返しの効かない音声では
そのまま事実として受け取られる。

この工程は台本を **元の文字起こしと突き合わせて** 点検し、問題を挙げたうえで
最小限の修正を入れた版を書く。

  draft/parts/{stem}_part01.txt         rewrite の出力（点検前）
  draft/parts/{stem}_part01_review.md   何を直したかの記録（人が読む用）
  narration/parts/{stem}_part01.txt     点検後（以降の工程はこちらを使う）

問題が1件も無ければ台本には触らず、そのまま複製する。
モデルに「直すところが無くても書き直せ」と言うと、直す必要のない箇所まで
書き換えてしまうためである。
"""
import json
import re
from pathlib import Path

from . import artifact, llm, ssml
from .config import (
    REVIEW_MODEL, REWRITE_MAX_CHARS,
    stage_dir, parts_dir, all_projects, STEP_IO,
)
from .rewrite import split_transcript

_IN, _OUT = STEP_IO["review"]

# ── 点検の指示 ────────────────────────────────────────────────────────────────

_PROMPT = """\
You are a standards editor at a broadcast news organisation. A narration script for a \
spoken news-commentary podcast has been drafted from the transcript of a two-person \
discussion. Before it is recorded, you check it against that transcript and against \
ordinary broadcast standards, then you fix what is wrong.

You are NOT rewriting the script. You are correcting it.

# What Counts As A Problem

Rank each finding as "high", "medium", or "low".

HIGH — must not be broadcast as written:
- UNSUPPORTED: a fact, figure, date, name, location, or causal claim that is not in the \
source transcript. Inference the writer added is not evidence.
- HEDGE STRIPPED: the source says "may", "reportedly", "appears to", "some analysts \
believe", or "unconfirmed", and the script states it flatly as fact.
- PREDICTION AS FACT: a future event presented as certain rather than as a possibility.
- ONE-SIDED SOURCING: a claim by one party to the story (a government, a company, a \
combatant) presented in the narrator's own voice instead of being attributed to them.
- ACCUSATION WITHOUT ATTRIBUTION: alleging that a named person or organisation committed \
a crime, a fraud, or an atrocity without saying who alleges it.
- NUMBER DRIFT: a figure, unit, date, or proper noun that contradicts the transcript, or \
that is stated more precisely than the transcript supports.

MEDIUM — fix unless the fix would break the sentence:
- SENSATIONALISM: alarmist or headline-style language that outruns the evidence \
("catastrophic", "on the brink", "the beginning of the end", "shocking").
- EDITORIALISING: a moral verdict on the people in the story, or the narrator's opinion \
presented as though it were established fact ("the spending exposed their hypocrisy").
  NOT editorialising, and NOT to be removed: the host's own first-person reaction to the \
EVIDENCE, plainly marked as personal — "Here's the part that surprised me", "when I follow \
that chain one step further", "if we take the figure at face value". This narration has a \
named human presenter and that voice is deliberate. Leave it alone unless it states a fact, \
drops a hedge, or judges a person.
- LOADED FRAMING: emotive or partisan wording where neutral wording carries the same fact.
- MISSING COUNTERPOINT: the transcript contains a caveat, denial, or competing reading \
that the script dropped.
- UNEXPLAINED JARGON: a technical term, acronym, or designation used with no plain-English \
gloss on first use.
- REDUNDANCY: the same conclusion stated more than once in different words, or an \
implication chain ("which means ... which in turn means ..."). Cut the repeats.
- INCONSISTENT NAME: the same person, place, or organisation spelled two ways in the \
script. Pick the form the transcript supports and use it throughout.
- DIGITS: a quantity, year, score, or sum written in digits ("176,000", "2025"). The \
synthesizer misreads digits — rewrite it as spoken words ("one hundred seventy-six \
thousand", "twenty twenty-five"). Alphanumeric designations whose official form contains \
digits (PAC-3, Boeing 747, Formula 1) keep that form.

LOW — note it, fix only if the fix is a clean deletion:
- Filler, empty intensifiers ("truly", "absolutely", "make no mistake"), padding.
- Written-only constructions that will not survive being heard once.

# How To Fix

- MINIMAL EDITS. Change only the words that carry the problem. Everything else must survive \
character for character.
- Fix by ATTRIBUTING or HEDGING, not by deleting, whenever the claim itself is in the \
transcript: "state media said the fire was contained", "the club reportedly put the fee \
at ...", "officials put the figure at ...".
- DELETE a claim only when it is absent from the transcript entirely. Do not invent a \
source, a date, or a number to prop it up.
- Do NOT add new facts, new analysis, new examples, or new transitions.
- Do NOT lengthen the script. Your revision must be about as long as the draft, and \
shorter if you cut redundancy.
- Do NOT restructure, reorder, or re-hook the script.

# Hard Constraints

- The output must be valid SSML: exactly one <speak> ... </speak> wrapper, with the \
existing <break time="Xs"/> tags kept where they are. Never add a break inside a sentence.
- If the draft opens with a fixed greeting and presenter introduction, reproduce it \
VERBATIM. It is the channel's standard opening and is not yours to edit.
- Everything you output is read aloud by a synthetic voice. No headings, labels, brackets, \
editor's notes, or markup other than the SSML tags.
- If you find NO problems, return an empty issues list and return the draft unchanged, \
character for character.

# Output

Return one JSON array with a single element:
- "issues": the findings, each with "severity", "type" (one of the labels above), "quote" \
(the exact phrase from the draft, under 30 words), "problem" (one sentence), and "fix" \
(one sentence on what you changed).
- "revised": the corrected script in SSML.
"""

# 表記揺れは part をまたいで起きる（実例: 同一のレストランが part05 で "Balzi Rossi"、
# part07 で "Balti Rossi"）。review は1 part ずつ見るため、単独では原理的に見つからない。
# 済んだ part で確定した綴りを次の part に渡して、照合できるようにする。
_NAMES_BLOCK = """\

# Spellings Already Used Earlier In This Script

These proper nouns appear in the parts already reviewed. This part must spell them exactly
the same way. A different spelling of the same thing is an INCONSISTENT NAME finding — fix
it to match this list, unless the transcript clearly shows this list is the wrong one.

{names}
"""

_SOURCE_BLOCK = """\

# Source Transcript — the ONLY thing the script may claim

Anything asserted in the script that cannot be traced to this passage is UNSUPPORTED.
Hedging that appears here must survive into the script.

--- transcript ---
{source}
--- end transcript ---
"""

_DRAFT_BLOCK = """\

# The Draft To Check

--- draft ---
{draft}
--- end draft ---
"""

_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "required": ["issues", "revised"],
        "properties": {
            "issues": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "required": ["severity", "type", "quote", "problem", "fix"],
                    "properties": {
                        "severity": {"type": "STRING", "enum": ["high", "medium", "low"]},
                        "type": {"type": "STRING"},
                        "quote": {"type": "STRING"},
                        "problem": {"type": "STRING"},
                        "fix": {"type": "STRING"},
                    },
                },
            },
            "revised": {"type": "STRING"},
        },
    },
}

_MAX_ATTEMPTS = 3

# 作り直しのときだけ足す。何が駄目だったかを伝えないと同じ失敗を繰り返す。
_RETRY_BLOCK = """

# YOUR PREVIOUS ATTEMPT WAS REJECTED — READ THIS FIRST
{problem}

Return the corrected script again with exactly that defect fixed. The revision must stay
about as long as the draft: this is a correction pass, not a rewrite and not a summary.
The whole script is one <speak> wrapper.
"""

# 校閲は書き直しではないので、長さは大きく動かないはずである。
# 下限を割る = 台本を削って要約した。上限を超える = 直すついでに書き足した
# （rewrite で削った冗長さが戻ってくるのは、この工程で最も避けたい失敗）。
_MIN_RATIO, _MAX_RATIO = 0.75, 1.15

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _validate(result: dict, draft: str) -> str | None:
    """校閲結果を検証する。問題なければ None、あれば理由の文字列を返す。"""
    revised = (result.get("revised") or "").strip()
    if not revised:
        return "revised が空です"
    if revised.count("<speak>") != 1 or not revised.endswith("</speak>"):
        return f"revised が SSML として壊れています（末尾: {revised[-40:]!r}）"
    bad = ssml.check_tags(revised)
    if bad:
        return f"revised: {bad}"
    if len(revised) < len(draft) * _MIN_RATIO:
        return (f"revised {len(revised):,}字 が draft {len(draft):,}字 の "
                f"{len(revised) / len(draft) * 100:.0f}%しかありません"
                f"（下限 {_MIN_RATIO * 100:.0f}%）")
    if len(revised) > len(draft) * _MAX_RATIO:
        return (f"revised {len(revised):,}字 が draft {len(draft):,}字 の "
                f"{len(revised) / len(draft) * 100:.0f}%に膨らんでいます"
                f"（上限 {_MAX_RATIO * 100:.0f}%）")
    if not isinstance(result.get("issues"), list):
        return "issues が配列ではありません"
    return None


def _report(part_name: str, issues: list[dict], changed: bool) -> str:
    """人が読む用の記録。何を見つけ、何を直したかだけを書く。"""
    lines = [f"# Review — {part_name}", ""]
    if not issues:
        lines += ["問題なし。台本はそのまま narration/parts/ へ複製しました。", ""]
        return "\n".join(lines)

    counts = {s: sum(1 for i in issues if i.get("severity") == s)
              for s in ("high", "medium", "low")}
    lines += [
        f"{len(issues)} 件（high {counts['high']} / medium {counts['medium']} "
        f"/ low {counts['low']}）",
        "" if changed else "※ 修正後の台本は draft と同一でした。",
        "",
    ]
    for i in sorted(issues, key=lambda x: _SEVERITY_ORDER.get(x.get("severity"), 3)):
        lines += [
            f"## [{i.get('severity', '?').upper()}] {i.get('type', '?')}",
            f"- 該当: 「{i.get('quote', '')}」",
            f"- 問題: {i.get('problem', '')}",
            f"- 修正: {i.get('fix', '')}",
            "",
        ]
    return "\n".join(lines)


def _source_for(part: Path, transcript_dir: Path, part_count: int, index: int) -> str:
    """この part の根拠になる文字起こしを返す。

    rewrite は文字起こしを REWRITE_MAX_CHARS ごとの塊に分け、1塊から1 part を書く。
    同じ分け方をやり直せば part と塊が対応する。数が合わなければ対応を仮定できないので、
    文字起こし全文を渡す（高くつくが、根拠を欠いた点検よりはよい）。
    """
    stem = part.stem.rsplit("_part", 1)[0]
    src = transcript_dir / f"{stem}.txt"
    if not src.exists():
        return ""
    text = src.read_text(encoding="utf-8")
    chunks = split_transcript(text, REWRITE_MAX_CHARS)
    if len(chunks) == part_count:
        return chunks[index]
    print(f"    [warn] part 数 {part_count} と文字起こしの塊 {len(chunks)} が一致しません。"
          f"全文を根拠として渡します（{len(text):,}字）")
    return text


# 固有名詞らしきもの: 大文字で始まる語が2語以上続くもの。
_PROPER = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|of|the|and))*\s+[A-Z][a-z]+\b")

# 文頭の語は固有名詞でなくても大文字になる。そのまま採ると "The Balzi Rossi" と
# "Balzi Rossi" が別物として並び、照合表が汚れる。先頭のこれらは落とす。
_LEADING = {"the", "a", "an", "this", "that", "these", "those", "it", "its",
            "but", "and", "if", "when", "while", "in", "on", "at", "for", "by",
            "from", "with", "as", "so", "then", "now", "here", "there", "his",
            "her", "their", "our", "no", "not", "both", "each", "more", "most"}


def known_names(parts: list[Path]) -> list[str]:
    """済んだ part から固有名詞らしき表記を集める（頻度順）。"""
    seen: dict[str, int] = {}
    for f in parts:
        for m in _PROPER.finditer(ssml.unwrap(f.read_text(encoding="utf-8"))):
            words = m.group().split()
            while len(words) > 2 and words[0].lower() in _LEADING:
                words.pop(0)
            name = " ".join(words)
            if len(words) >= 2 and len(name) > 4 and words[0].lower() not in _LEADING:
                seen[name] = seen.get(name, 0) + 1
    return sorted(seen, key=lambda n: (-seen[n], n))[:60]


def review_part(part: Path, out: Path, source: str, model: str = REVIEW_MODEL,
                names: list[str] | None = None) -> Path:
    draft = part.read_text(encoding="utf-8").strip()
    prompt = (
        _PROMPT
        + (_NAMES_BLOCK.format(names="\n".join(f"- {n}" for n in names)) if names else "")
        + (_SOURCE_BLOCK.format(source=source) if source else "")
        + _DRAFT_BLOCK.format(draft=draft)
    )

    result: dict = {}
    problem: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw = ""
        try:
            raw = llm.generate_json(
                model,
                prompt + (_RETRY_BLOCK.format(problem=problem) if problem else ""),
                _SCHEMA, schema_name="narration_review", effort="high")
            parsed = json.loads(raw or "[]")
            result = parsed[0] if parsed else {}
            problem = _validate(result, draft)
        except llm.IncompleteResponse as e:
            problem = str(e)
        except (json.JSONDecodeError, TypeError, KeyError, IndexError) as e:
            problem = f"応答がJSONとして読めません（{len(raw or ''):,}字, {type(e).__name__}: {e}）"
        if problem is None:
            break
        if attempt == _MAX_ATTEMPTS:
            raise RuntimeError(f"{part.name}: {problem}（{_MAX_ATTEMPTS}回試行）")
        print(f"    [retry {attempt}/{_MAX_ATTEMPTS - 1}] {problem}")

    issues = result["issues"]
    revised = result["revised"].strip()
    # 指摘が無いのに文面が変わっているのは、直す理由の説明がつかない書き換えである。
    # 台本は rewrite の出力のままにして、変えなかったことを記録に残す。
    if not issues and revised != draft:
        revised = draft

    artifact.write_checked(out, revised, min_chars=50,
                           src_chars=len(draft), min_ratio=_MIN_RATIO,
                           label=f"review/{part.name}")
    (part.parent / f"{part.stem}_review.md").write_text(
        _report(part.name, issues, revised != draft), encoding="utf-8")

    counts = {s: sum(1 for i in issues if i.get("severity") == s)
              for s in ("high", "medium", "low")}
    print(f"    {part.name}: high {counts['high']} / medium {counts['medium']} "
          f"/ low {counts['low']}  →  {out.name} ({len(revised):,}字)")
    return out


def _drop_orphans(parts: list[Path], src_dir: Path, dst_dir: Path) -> None:
    """draft/parts/ に対応するもののない出力と記録を消す。

    台本を作り直すと part の数が変わる（7分割が5分割になる）。narration/parts/ は
    draft/parts/ から作られる派生物なので、残った古い part06・part07 は次の
    concat_narration で本文に混ざる。出来上がった台本を読むまで気づけない。
    """
    live = {p.name for p in parts}
    for stale in sorted(dst_dir.glob("*_part*.txt")):
        if stale.name not in live:
            print(f"  [stale] {stale.name} は draft に対応がありません。削除します")
            stale.unlink()
    live_reports = {f"{p.stem}_review.md" for p in parts}
    for stale in sorted(src_dir.glob("*_part*_review.md")):
        if stale.name not in live_reports:
            stale.unlink()


def run(project: str, *, force: bool = False, model: str | None = None) -> list[Path]:
    """Run the news review for a project.

    Reads:  draft/parts/{stem}_part*.txt
    Writes: narration/parts/{stem}_part*.txt  +  draft/parts/{stem}_part*_review.md
    """
    active_model = model or REVIEW_MODEL
    src_dir = parts_dir(project, _IN)     # draft/parts/
    dst_dir = parts_dir(project, _OUT)    # narration/parts/
    transcript_dir = stage_dir(project, "transcript")
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    parts = sorted(p for p in src_dir.glob("*_part*.txt") if not p.stem.endswith("_review"))
    if not parts:
        return results
    _drop_orphans(parts, src_dir, dst_dir)
    print(f"  Reviewing {len(parts)} part(s)  [{active_model} / {llm.provider(active_model)}]")

    for i, part in enumerate(parts):
        out = dst_dir / part.name
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        source = _source_for(part, transcript_dir, len(parts), i)
        # 済んだ part の綴りを渡す。skip された part も確定済みなので含める。
        names = known_names([p for p in results if p.exists()])
        results.append(review_part(part, out, source, model=active_model, names=names))

    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] review")
        run(project)


if __name__ == "__main__":
    run_all()
