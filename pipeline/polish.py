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
Report defects. Do NOT rewrite anything: this pass produces a list, nothing else.

Quote the offending text EXACTLY as it appears — a later pass finds your quote by exact
string match, so a paraphrased or re-punctuated quote is useless.

# 1. REPEATED RHETORICAL MOVE
Repetition of a device, not of words. If the narrator performs the same MOVE three or more
times — reacting with astonishment at a number, introducing an analogy, asking the listener
a question, announcing a turn — name the move, count it, and quote every instance.
Wording that differs each time still counts: "I assumed I had misread it", "I had to check
it twice", "I assumed it might be a typo" are ONE move performed three times, and by the
third the listener hears a performance rather than a reaction.

# 2. BROKEN SENTENCE
A sentence that does not survive on its own: a claim whose meaning was lost when it was
shortened ("refining enough fuel for only its own internal requirements" where the point
was that refining covers only two-thirds of demand), a connective that does not follow from
what precedes it ("Those claims remain unconfirmed rumors. The general's survival is
therefore a crucial detail."), a number that does not agree with its verb, a fragment left
over from an earlier draft.

# 3. MISSING STRUCTURE
Answer each of these with yes or no and quote the evidence, or report the absence:
- Does the opening pose a question about the most surprising event in the script, within
  roughly the first 150 words?
- Does each chapter open with a spoken signpost saying where the argument has arrived?
- Does each middle chapter END with a forward reference to that opening question — a line
  telling the listener the payoff is still coming? Report the absence separately for EACH
  chapter that lacks one, and say which sentence the missing line should follow.
- Does the ending return to the opening question and close it?

# 4. OVER-EXPLANATION
An inline gloss on a word a general adult listener already knows — "air-defense batteries,
grouped defensive systems", "VIPs, or very important people". Specialist terms keep their
gloss; ordinary vocabulary does not need one.

# 5. ATTRIBUTION AND HEDGING
- Wording implying the programme has its own reporters or private informants ("our
  sources", "we have learned").
- An unverified report, a prediction, or one party's claim stated as settled fact.
- An accusation against a named person or organisation with no attribution.

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

Pairs of old text and new text. NEVER return the whole script or a rewritten section.
- "old" must be copied from the script CHARACTER FOR CHARACTER. It is located by exact
  string match; if it differs by a comma the edit is discarded. Quote enough context that
  the text appears exactly once in the script — usually one full sentence.
- "new" is the replacement. To insert a line, set "new" to the old sentence followed by the
  new one. To delete, set "new" to the empty string.

# Rules

1. Touch NOTHING that is not in the defect list.
2. "new" keeps every figure, date, proper noun, attribution and hedge that "old" carried.
   If a defect requires dropping one, say so in "why".
3. A repetition report is not always a defect. If the repeated words are the SUBJECT
   MATTER — a unit ("thousand square meters"), a name, a figure that genuinely recurs —
   leave every instance alone and skip it. Only a narrator's verbal habit needs fixing.
   For a repeated phrase or a repeated rhetorical move that IS a habit: leave at most TWO
   instances and
   change the rest. Change the FUNCTION, not just the wording — if the move was astonishment
   at a number, the replacement should do something else entirely, such as stating the
   consequence flatly or contrasting it with a second figure. Replacements must differ from
   each other, or you have simply created the next catchphrase.
4. For missing structure, insert one or two sentences at the position given, and leave the
   surrounding sentences untouched.
5. For a broken sentence, restore the meaning the transcript supports. Do not invent facts.
6. Preserve SSML: the only tags are <speak> and <break time="Xs"/>, never two in a row,
   never inside a sentence. Every number in speech is spelled as words.

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
    applied, rejected = [], []
    for p in patches:
        old, new = p.get("old", ""), p.get("new", "")
        if not old:
            rejected.append({**p, "reason": "old が空です"})
            continue
        n = text.count(old)
        if n == 0:
            rejected.append({**p, "reason": "old が原文に見つかりません（引用が不正確）"})
            continue
        if n > 1:
            rejected.append({**p, "reason": f"old が {n} 箇所にあり、対象を特定できません"})
            continue
        text = text.replace(old, new, 1)
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
