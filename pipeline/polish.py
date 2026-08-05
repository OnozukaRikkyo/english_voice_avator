"""Stage draft→narration: 完成した台本を **フルテキストで** 点検して直す。

# なぜ作り直したか

前の設計は2つ間違えていた。

**(1) 生成時に禁じようとした。** 「Xを使うな」と書くと、モデルは別の単一
テンプレートへ収束する（"caught my attention" を禁じたら "When I first saw
that figure" が5回になった）。書きながら自分の口癖を数えることはできない。
**完成文から数えるのは確実にできる。** だから禁止ではなく検出にする。

**(2) 塊ごとに点検した。** 定型句の総回数も、冒頭の伏線への引き戻しの有無も、
締めが冒頭に回帰しているかも、**全文を見なければ判定できない**。
指示を強めても2回続けて実装されなかったのは、指示が弱いからではなく、
点検する側に見えていなかったからである。

# どう直したか

台本を1本に連結してから、3つのパスを回す。

    A 検出   書き換えは一切しない。欠陥のリストだけを出す。
             機械的に数えられるもの（反復・タグ・数字・表記揺れ）は
             defects.py がコードで数える。判断の要るもの（修辞機能の反復、
             文意の破綻、必須要素の有無、帰属とヘッジ）だけモデルに訊く。

    B パッチ 全文を書き直させない。「元の文 → 直した文」の組だけを出させ、
             **文字列の置換はコードが行う**。元の文が原文に厳密一致しなければ
             そのパッチは棄却する。これで修正対象でない文が巻き添えで
             壊れることが原理的に起きない。

    C 検証   組ごとに、数値・固有名詞・ヘッジが保たれているかを見る。
             機械照合（数値と固有名詞の突き合わせ）を先に通し、
             残りをモデルに訊く。落ちた組は当てない。

A→B→C を最大 _MAX_ROUNDS 周。残った欠陥は「既知の残存欠陥」として
narration/{stem}_defects.md に記録する。ゼロを追うと収束しない。

  draft/{stem}_full.txt        ← 読む（連結済みの台本）
  narration/{stem}_full.txt    ← 書く（点検後）
  narration/{stem}_defects.md  ← 書く（何を直し、何が残ったか）
"""
import json
import re
from pathlib import Path

from . import artifact, defects, llm, ssml
from .config import (
    REVIEW_MODEL, REWRITE_MAX_CHARS, POLISH_ROUNDS,
    stage_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["polish"]

# ── A: モデルにしか判断できない欠陥 ───────────────────────────────────────────
#
# コードで数えられるものはここに書かない（defects.py が確実に見つける）。
# ここに書くのは「読んで判断する」ことだけである。

_DETECT_PROMPT = """\
You are inspecting a finished narration script for a spoken news-commentary podcast.
The story may be about anything — politics, business, sport, science, culture, disaster —
and every check below applies unchanged whatever the subject. Judge the script against its
own subject matter, not against the examples used here to illustrate each check.
Report defects. Do NOT rewrite anything: this pass produces a list, nothing else.

# What You Are Given
Two blocks are appended below, each between named markers. The block between
"--- transcript ---" and "--- end ---" is the SOURCE and is never a defect; it exists only
to check the script against. The block between "--- script ---" and "--- end ---" is the
script under inspection, and every quote you return must come from it. The transcript block
may be absent.

# How To Quote
Copy the offending text EXACTLY as it appears in the script. A later pass locates it by
exact string match on the decoded JSON string, so ordinary punctuation and spacing are
fine, but a paraphrase or re-punctuation is useless. Quote enough that the text occurs
exactly once — usually one full sentence, and where a sentence itself recurs, extend the
quote into the neighbouring sentence until it is unique. If no unique quote is possible,
say so in "detail" and report the defect once rather than several times.

Report ONLY failures. A check that passes produces no element at all; do not report that
something is fine. Return one element per instance: if a habit occurs four times, return
four elements quoting the four instances, each naming the shared habit in "detail".

# 1. REPEATED RHETORICAL MOVE
Repetition of a device, not of words. If the narrator performs the same MOVE three or more
times — reacting with astonishment at a figure, introducing an analogy, asking the listener
a question, announcing a turn, calling something unprecedented — name the move, count it,
and quote every instance.
Wording that differs each time still counts: "I assumed I had misread it", "I had to check
it twice", "I assumed it might be a typo" are ONE move performed three times, and by the
third the listener hears a performance rather than a reaction.

# 2. BROKEN SENTENCE
A sentence that does not survive on its own. Four kinds, whatever the subject:
- MEANING LOST IN SHORTENING: the sentence still parses but no longer says anything —
  "producing enough for only its own internal requirements" after the point that production
  covers two-thirds of demand was cut; "the club posted strong revenue" after the figure
  that made it strong was cut.
- CONNECTIVE THAT DOES NOT FOLLOW: "Those reports remain unconfirmed. His survival is
  therefore a crucial detail." — "therefore" joins nothing. Also "but" between two agreeing
  clauses, "which means" before a claim that does not follow.
- NUMBER THAT DOES NOT AGREE with its verb or its unit.
- FRAGMENT left over from an earlier draft: a sentence that answers a point the script no
  longer makes.

# 3. MISSING STRUCTURE
A chapter is a distinct strand of the story — one subject developed over several
paragraphs, ending where the script stops developing it and takes up another. A
<break time="1.5s"/> usually marks one. Identify the chapters first, then check:
- Does the opening pose a question about the most surprising event in the script, within
  roughly the first 150 words?
- Does each chapter open with a spoken signpost saying where the argument has arrived?
- Does each chapter before the last END with a forward reference to that opening question
  — a line telling the listener the payoff is still coming?
- Does the ending return to the opening question and close it?
Report only what is MISSING, one element per missing item. Since missing text cannot be
quoted, set "quote" to the existing sentence the new line should follow (or, for a missing
opening question, the script's first sentence) and say in "fix" what to insert there.
If the opening question itself is absent, report THAT alone: the forward references and the
closing return depend on it, and reporting them too would produce edits that point at
nothing.

# 4. OVER-EXPLANATION
An inline gloss on a word a general adult listener already knows — "a stadium, a venue
where matches are played", "VIPs, or very important people", "a logistics hub, a site that
stores and moves supplies". The test is whether ordinary journalism uses the word without
explaining it. Genuine specialist terms — loan-loss provisions, expected goals, a
hit-to-kill interceptor, a p-value — keep their gloss.

# 5. ATTRIBUTION
Judge these from the script alone; they need no transcript.
- Wording implying the programme has its own reporters or private informants ("our
  sources", "we have learned").
- A future event stated as certain rather than as a possibility.
- An accusation against a named person or organisation with no attribution anywhere in the
  script.
Anything that requires comparing the script against the transcript belongs in section 6,
not here. Report each defect once, under one category only.

# 6. GROUNDING (only if a transcript section is supplied below)
A fact, figure, date, name or causal claim in the script that the transcript does not
support, or hedging present in the transcript that the script dropped.

Return a JSON array. Each element:
- "category": one of REPEATED MOVE, BROKEN SENTENCE, MISSING STRUCTURE, OVER-EXPLANATION,
  ATTRIBUTION, GROUNDING
- "quote": the exact text from the script. For a MISSING STRUCTURE absence, quote the
  sentence the new line should follow.
- "detail": one sentence in JAPANESE saying what is wrong.
- "fix": one sentence in JAPANESE saying what to do about it.
Report nothing else. An empty array means the script passes.
"""

_DETECT_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "required": ["category", "quote", "detail", "fix"],
        "properties": {
            "category": {"type": "STRING"},
            "quote": {"type": "STRING"},
            "detail": {"type": "STRING"},
            "fix": {"type": "STRING"},
        },
    },
}

# ── B: 差分だけを出させる ─────────────────────────────────────────────────────

_PATCH_PROMPT = """\
You are given a narration script and a list of defects found in it. Produce the minimal
edits that fix those defects.

# The Only Output Allowed

Edits, and nothing else. NEVER return the whole script or a rewritten section. Each edit
has three fields — "old", "new" and "why" — and no other content is permitted.
- "old" must be copied from the script CHARACTER FOR CHARACTER. It is located by exact
  string match; if it differs by a comma the edit is discarded. Quote enough context that
  the text appears exactly once in the script — usually one full sentence.
- "new" is the replacement, written as it will read in the script. To insert after a
  sentence, set "new" to that sentence plus the new one; to insert before it, set "new" to
  the new sentence plus that one. Separate sentences with a single space. To delete, set
  "new" to the empty string.
- Every "old" must match the script AS GIVEN TO YOU. Edits are applied to the original
  text, so two edits must never overlap: if one sentence carries two defects, fix both in
  a single edit.

# Rules

1. Touch NOTHING that is not in the defect list.
2. "new" keeps every figure, date, proper noun, attribution and hedge that "old" carried.
   If a defect requires dropping one, say so in "why".
3. A repetition report is not always a defect. If the repeated words are the SUBJECT
   MATTER — a unit ("thousand square meters"), a name, a figure that genuinely recurs —
   leave every instance alone and skip it. Only a narrator's verbal habit needs fixing.
   For a repeated phrase or a repeated rhetorical move that IS a habit: leave at most TWO
   instances — keep the FIRST two occurrences and change every later one. Change the FUNCTION, not just the wording — if the move was astonishment
   at a number, the replacement should do something else entirely, such as stating the
   consequence flatly or contrasting it with a second figure. Replacements must differ from
   each other, or you have simply created the next catchphrase.
4. For missing structure, insert one or two sentences at the position given, and leave the
   surrounding sentences untouched.
5. For a broken sentence, restore the meaning the transcript supports. Do not invent
   facts. If the transcript shows the script's figure, date or name is simply WRONG, correct
   it to the transcript's version and say so in "why" — rule 2 protects the source's facts,
   not the script's mistakes.
6. These apply to the text you write in "new", not to the rest of the script.
   - SPOKEN WORDS carry no digits. Every quantity, year, score, sum or designation you
     write is spelled out: "twenty twenty-five", "S-four-hundred". This is about FORM, not
     value — "2025" becomes "twenty twenty-five", never a different year.
   - SSML TAGS keep their digits, because they are not spoken: a pause is written
     <break time="1.0s"/> or <break time="1.5s"/>, exactly like the ones already in the
     script. Copy the form; do not spell the seconds out.
   - Tags allowed: <speak> and <break time="Xs"/>. Never two breaks in a row, never one
     inside a sentence.
   - Digits elsewhere in the script are not your concern; leave them unless the defect list
     names them.

Return a JSON array. Each element: "old", "new", "why" (one sentence in JAPANESE).
"""

_PATCH_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "required": ["old", "new", "why"],
        "properties": {
            "old": {"type": "STRING"},
            "new": {"type": "STRING"},
            "why": {"type": "STRING"},
        },
    },
}

# ── C: 意味が保たれているか ───────────────────────────────────────────────────

_VERIFY_PROMPT = """\
Check each edit for meaning that went missing. You are not judging style.

For every pair, ask:
1. Is every figure, date, proper noun and job title in "old" still present in "new"?
2. Did the strength of the claim change — a hedged statement made certain, or a stated
   fact softened into speculation?
3. Was an attribution or a hedge ("reportedly", "according to", "unconfirmed") dropped?
4. Does "new" read correctly on its own, as a complete sentence?

Return a JSON array with one element per pair, in the same order:
- "ok": true if the edit preserves meaning, false if it must go back for rework
- "why": one sentence in JAPANESE. When ok is false, say exactly what was lost.
Judge only what is in front of you. An edit that deliberately removes a phrase the defect
list called false ("our sources") is correct, as long as the claim's certainty is unchanged.
"""

_VERIFY_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "required": ["ok", "why"],
        "properties": {"ok": {"type": "BOOLEAN"}, "why": {"type": "STRING"}},
    },
}


# ── C の機械照合 ──────────────────────────────────────────────────────────────

_NUMBER_WORD = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion)\b", re.I)


def _facts_in(text: str) -> set[str]:
    """その文が運んでいる「落としてはいけないもの」。数と固有名詞。"""
    body = defects.spoken_text(text)
    return ({m.group().lower() for m in _NUMBER_WORD.finditer(body)}
            | set(defects.proper_nouns(body)))


def check_kept(old: str, new: str) -> str | None:
    """old にあって new から消えた数・固有名詞を返す。無ければ None。

    モデルの自己申告より先にこれを通す。数と名前は目視で消えたかどうか
    判定できるので、判断をモデルに任せる理由がない。
    """
    lost = _facts_in(old) - _facts_in(new)
    # 重複表現を削る修正では、同じ語が別の場所に残っていることがある。
    # ここでは「この組の中で消えた」ことだけを見る。
    return f"消えた要素: {', '.join(sorted(lost))}" if lost else None


# ── パッチの適用 ──────────────────────────────────────────────────────────────

def apply_patches(text: str, patches: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """当たったパッチだけを当てる。返り値は (結果, 当てた組, 棄却した組)。

    棄却の理由は2つだけ:
      - old が原文に無い（モデルが引用を作文した）
      - old が2箇所以上ある（どちらを直すのか決められない）
    どちらも「黙って当てない」ほうが安全である。取りこぼしは次の周で拾える。
    """
    original = text
    applied, rejected = [], []
    spans: list[tuple[int, int]] = []      # 原文のどこを既に書き換えたか

    for p in patches:
        old, new = p.get("old", ""), p.get("new", "")
        if not old:
            rejected.append({**p, "reason": "old が空です"})
            continue
        n = original.count(old)
        if n == 0:
            rejected.append({**p, "reason": "old が原文に見つかりません（引用が不正確）"})
            continue
        if n > 1:
            rejected.append({**p, "reason": f"old が {n} 箇所にあり、対象を特定できません"})
            continue
        # 位置は必ず原文で測る。適用済みの本文で数えると、先の置換で
        # 文字数が変わったぶんだけ範囲がずれ、重なりを見落とす。
        i = original.index(old)
        span = (i, i + len(old))
        overlap = next(((a, b) for a, b in spans if a < span[1] and span[0] < b), None)
        if overlap:
            rejected.append({**p, "reason": "先の修正と範囲が重なっています"})
            continue
        if text.count(old) != 1:
            rejected.append({**p, "reason": "先の修正で原文が変わり、対象を特定できません"})
            continue
        text = text.replace(old, new, 1)
        spans.append(span)
        applied.append(p)
    return text, applied, rejected


# ── A: 検出 ───────────────────────────────────────────────────────────────────

def detect(script: str, transcript: str, model: str) -> list[defects.Defect]:
    """コードの検出結果とモデルの検出結果を1つのリストにまとめる。"""
    found = defects.scan(script)

    prompt = _DETECT_PROMPT
    if transcript:
        prompt += ("\n# Source Transcript — the only thing the script may claim\n\n"
                   "--- transcript ---\n" + transcript + "\n--- end ---\n")
    prompt += "\n# The Script\n\n--- script ---\n" + script + "\n--- end ---\n"

    raw = llm.generate_json(model, prompt, _DETECT_SCHEMA,
                            schema_name="script_defects", effort="high")
    for d in json.loads(raw or "[]"):
        found.append(defects.Defect(d["category"], d["quote"], d["detail"], d["fix"]))
    return found


def _defect_list(found: list[defects.Defect]) -> str:
    out = []
    for i, d in enumerate(found, 1):
        out.append(f'{i}. [{d.category}] quote: "{d.quote}"\n'
                   f"   problem: {d.detail}\n   fix: {d.fix}")
        if d.occurrences:
            out.append("   occurrences:\n" + "\n".join(f"     - {o}" for o in d.occurrences[:8]))
    return "\n".join(out)


# ── B + C: 直して確かめる ─────────────────────────────────────────────────────

def repair(script: str, found: list[defects.Defect], model: str) -> tuple[str, list[dict]]:
    """欠陥リストから差分を作り、検証を通ったものだけを当てる。"""
    prompt = (_PATCH_PROMPT + "\n# Defects\n\n" + _defect_list(found)
              + "\n\n# The Script\n\n--- script ---\n" + script + "\n--- end ---\n")
    raw = llm.generate_json(model, prompt, _PATCH_SCHEMA, schema_name="patches", effort="high")
    patches = json.loads(raw or "[]")
    if not patches:
        return script, []

    # C-1 機械照合。数と固有名詞が消えた組はモデルに訊くまでもなく差し戻す。
    survived, dropped = [], []
    for p in patches:
        lost = check_kept(p.get("old", ""), p.get("new", ""))
        (dropped if lost else survived).append({**p, "reason": lost} if lost else p)

    # C-2 意味の検証。
    if survived:
        pairs = "\n\n".join(f'{i}. old: "{p["old"]}"\n   new: "{p["new"]}"\n   why: {p.get("why","")}'
                            for i, p in enumerate(survived, 1))
        raw = llm.generate_json(model, _VERIFY_PROMPT + "\n\n# Edits\n\n" + pairs,
                                _VERIFY_SCHEMA, schema_name="verdicts", effort="high")
        verdicts = json.loads(raw or "[]")
        keep = []
        for p, v in zip(survived, verdicts + [{"ok": True, "why": ""}] * len(survived)):
            (keep if v.get("ok") else dropped).append(
                p if v.get("ok") else {**p, "reason": v.get("why", "検証で差し戻し")})
        survived = keep

    script, applied, rejected = apply_patches(script, survived)
    for p in applied:
        p["result"] = "適用"
    for p in rejected + dropped:
        p["result"] = "棄却"
    return script, applied + rejected + dropped


# ── 記録 ──────────────────────────────────────────────────────────────────────

def _report(rounds: list[dict], remaining: list[defects.Defect]) -> str:
    out = ["# 点検の記録", ""]
    for r in rounds:
        out.append(f"## 第{r['round']}周 — 検出 {r['found']} 件 / 適用 {r['applied']} 件 "
                   f"/ 棄却 {r['rejected']} 件")
        out.append("")
        for p in r["patches"]:
            mark = "✓" if p.get("result") == "適用" else "✗"
            out.append(f"- {mark} 「{p.get('old','')[:80]}」")
            out.append(f"    → 「{p.get('new','')[:80]}」")
            out.append(f"    理由: {p.get('why','')}")
            if p.get("reason"):
                out.append(f"    棄却: {p['reason']}")
        out.append("")

    out += ["## 既知の残存欠陥", ""]
    if not remaining:
        out.append("なし。")
    else:
        out.append(f"{POLISH_ROUNDS} 周で直しきれなかったものです。"
                   "**構造・文意の破綻・事実に関わるものは配信前に手で直してください。**")
        out.append("")
        out += [d.as_markdown() for d in remaining]
    return "\n".join(out)


# ── 工程本体 ──────────────────────────────────────────────────────────────────

def polish_file(src: Path, dst: Path, transcript: str, model: str = REVIEW_MODEL) -> Path:
    script = src.read_text(encoding="utf-8").strip()
    rounds: list[dict] = []
    found: list[defects.Defect] = []

    for i in range(1, POLISH_ROUNDS + 1):
        found = detect(script, transcript, model)
        print(f"    第{i}周: 欠陥 {len(found)} 件"
              + (f"（{', '.join(sorted({d.category for d in found}))}）" if found else ""))
        if not found:
            break
        script, patches = repair(script, found, model)
        applied = sum(1 for p in patches if p.get("result") == "適用")
        print(f"      → 適用 {applied} / 棄却 {len(patches) - applied}")
        rounds.append({"round": i, "found": len(found), "applied": applied,
                       "rejected": len(patches) - applied, "patches": patches})
        if applied == 0:
            break                      # 何も当たらないなら次の周も当たらない

    # 直した結果に決定論的な仕上げをかける（間の重複はここで潰す）
    script = ssml.merge_breaks(script)
    artifact.write_checked(dst, script, min_chars=500,
                           src_chars=len(src.read_text(encoding="utf-8")),
                           min_ratio=0.85, label=f"polish/{src.name}")
    report = dst.parent / f"{dst.stem.removesuffix('_full')}_defects.md"
    report.write_text(_report(rounds, found), encoding="utf-8")
    print(f"    → {dst.name}（残存 {len(found)} 件 / 記録 {report.name}）")
    return dst


def _transcript_for(src: Path, project: str) -> str:
    """台本の根拠になった文字起こし。無ければ空（根拠照合だけ落ちる）。"""
    stem = src.stem.removesuffix("_full")
    p = stage_dir(project, "transcript") / f"{stem}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def run(project: str, *, force: bool = False, model: str | None = None) -> list[Path]:
    """Reads draft/{stem}_full.txt, writes narration/{stem}_full.txt + _defects.md."""
    active_model = model or REVIEW_MODEL
    src_dir, dst_dir = stage_dir(project, _IN), stage_dir(project, _OUT)
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for src in sorted(src_dir.glob("*_full.txt")):
        out = dst_dir / src.name
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        print(f"  Polishing: {src.name} ({len(src.read_text(encoding='utf-8')):,}字) "
              f"[{active_model} / {llm.provider(active_model)}]")
        results.append(polish_file(src, out, _transcript_for(src, project), model=active_model))
    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] polish")
        run(project)


if __name__ == "__main__":
    run_all()
