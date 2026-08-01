"""Stage transcript→narration: English transcript → narration script (SSML).

REWRITE_MAX_CHARS in config.py controls segment size:
  -1  → unlimited: full narration in one file, no split instructions in prompt
  N   → each segment is at most N characters
"""
import json
from pathlib import Path

from . import llm
from .config import (
    REWRITE_MODEL, REWRITE_MAX_CHARS,
    stage_dir, parts_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["rewrite"]

# ── Shared role + content instructions ────────────────────────────────────────

_ROLE = """\
# Role & Objective
You are a subject-matter expert in whatever field the transcript covers, and a high-impact \
YouTube scriptwriter. You will receive a transcript of a two-person dialogue discussing news \
or analysis. Your task is to transform it into a compelling, sophisticated English commentary \
narration script for a YouTube audience.

# Core Instructions

0. Match the Subject Matter — READ THIS FIRST:
- First identify what the transcript is actually about (e.g. sport, science, culture, \
economics, technology, international affairs) and adopt the expertise, vocabulary, and frame \
of reference of that field.
- Do NOT impose the framing of an unrelated field. A transfer window is not a military \
campaign; a research result is not a geopolitical struggle. Words like "battlefield", \
"frontline", "offensive" or "geopolitical" belong in a script only when the subject really \
is conflict.

1. Precise Terminology:
- Identify every proper noun and technical term in the transcript: people, organisations, \
places, products, systems, designations, metrics, and field-specific jargon.
- Use the exact, globally recognized English spellings and designations used by the \
authoritative sources of that field — not informal or approximate terms.

2. Substantive & Novel Insights (Go Beyond the Transcript):
- Do not merely summarize what the speakers said. Read between the lines to uncover the \
underlying intent, mechanism, or broader implications.
- Add sharp, original analytical perspective appropriate to the field: e.g., why this \
particular development matters beyond the immediate news, or how a shift changes the \
incentives, economics, or constraints that the participants face.

3. Script Structure & Tone:
- Hook/Introduction: Open with a powerful, attention-grabbing line that immediately \
communicates the stakes and hooks the viewer.
- Body: Deliver the news seamlessly integrated with deep strategic analysis. \
Use rhetorical questions and smooth transitions to maintain viewer retention.
- Conclusion/Outro: Close with a forward-looking thought — what to watch next.
- Tone: Analytical, authoritative, engaging, and objective.
- Voice: Single narrator (no dialogue). Remove all conversational fillers \
("uh", "you know", "right", "exactly", "yeah", etc.).
- Energy: High-impact, like a top explanatory YouTube channel in that field, aimed at a global audience.

4. Coverage — CRITICAL:
- You MUST cover EVERY topic, event, location, and analytical point mentioned in the transcript.
- Do NOT summarize, condense, or omit any section of the transcript.
- The narration script must be long enough to fully address all content in the transcript. \
A 50,000-character transcript should produce a narration of comparable length and depth — \
not a short summary.
- If in doubt, expand with analysis rather than cut content.

5. SSML Formatting — REQUIRED:
- Wrap the entire text of each segment in <speak> ... </speak>.
- Insert <break time="Xs"/> tags at natural spoken pauses. Use these guidelines:
  - Between sentences: <break time="0.5s"/>
  - Between paragraphs or topic shifts: <break time="1.0s"/>
  - At major section transitions (e.g., hook → body, body → conclusion): <break time="1.5s"/>
- Do NOT add breaks in the middle of a sentence.
- Example: <speak>The announcement landed just after midnight. <break time="0.5s"/> Here is why that matters. <break time="1.0s"/> For the first time...</speak>\
"""

# ── Unlimited mode: no mention of splitting ────────────────────────────────────

# 注意: このモードは .format() を通さないため、波括弧はエスケープしない。
_PROMPT_UNLIMITED = _ROLE + """

# Output Format
Return a JSON array with a single element containing the full narration:
- { "index": 1, "text": <the complete narration script in SSML: wrapped in <speak>...</speak> with <break> tags> }
"""

# ── Continuation mode: one section of a longer script ─────────────────────────
#
# 長い transcript を塊に分けて渡すとき、各塊を独立に書かせると
# それぞれが冒頭のフックと締めを持ってしまい、1本の台本として繋がらない。
# 位置と直前の文脈を伝えて、続きとして書かせる。

_POSITION = {
    "first": (
        "This is the OPENING section. Write the hook that starts the whole script. "
        "Do NOT write a conclusion or sign-off — the script continues after this section."
    ),
    "middle": (
        "This is a MIDDLE section of a continuous script. "
        "Do NOT write an opening hook and do NOT write a conclusion or sign-off. "
        "Begin as a natural continuation of what came before, and end mid-argument "
        "so the next section can pick up from you."
    ),
    "last": (
        "This is the FINAL section. Do NOT write a new opening hook. "
        "Continue from what came before and close the whole script with a "
        "forward-looking conclusion."
    ),
}

_PROMPT_CONTINUATION = _ROLE + """

# Position in the Script — READ THIS
You are writing section {index} of {total} of ONE continuous narration script.
{position}

The source material below is only this section's portion of the transcript.
Cover it fully; do not reach forward or backward into other sections.

{context}

# Output Format
Return a JSON array with a single element containing this section's narration:
- {{ "index": 1, "text": <this section in SSML: wrapped in <speak>...</speak> with <break> tags> }}
"""

_CONTEXT_BLOCK = """\
# What Came Before
The previous section ended with the passage below. Continue naturally from it.
Do NOT repeat it, do NOT re-introduce the topic, do NOT summarise what was said.

--- previous section, final passage ---
{tail}
--- end ---
"""

# 直前の台本から渡す文字数。多すぎると本文と混同され、少ないと繋がりが切れる。
_CONTEXT_CHARS = 700

# ── Limited mode: splitting instructions included ──────────────────────────────

_PROMPT_LIMITED = _ROLE + """

# Segmentation Rules
After writing the COMPLETE narration (covering all content), divide it into segments:
- Each segment MUST be a coherent unit of meaning — do NOT cut a sentence in the middle.
- Each segment MUST be at most {max_chars} characters long (including spaces and punctuation).
- ALL segments combined MUST contain the complete narration — zero omissions.
- Use as many segments as needed. Do not limit the number of segments.

# Output Format
Return a JSON array of narration segments for AI voice synthesis:
- Each element: {{ "index": <integer starting from 1>, "text": <SSML string> }}
- Each "text" MUST be wrapped in <speak>...</speak> and contain <break> tags at natural pauses.
- Each "text" MUST be at most {max_chars} characters (never cut mid-sentence).
- Together, all segments must form the complete narration script without omissions.
"""


_MAX_ATTEMPTS = 3

# ナレーション合計が transcript のこの割合を下回ったら生成失敗とみなす。
#
# プロンプトは「要約するな・全網羅せよ・同等の長さに」と要求している。
# 分割ありの実測は 51%、短い入力では 116% に達する。
# 30% では明らかな要約（38,410字→11,774字＝31%）を通してしまったため引き上げた。
#
# 下限を上げすぎると、話者が繰り返しの多い喋り方をした回で誤検出しうる。
# その場合は再生成が走るだけで壊れた成果物は残らないが、料金は増える。
_MIN_RATIO = 0.45


def _validate(paragraphs: list[dict], src_chars: int) -> str | None:
    """生成結果を検証する。問題なければ None、あれば理由の文字列を返す。

    プロンプトは「要約するな・全網羅せよ」と要求しているので、
    合計が入力より極端に短ければ途中で切れたか手を抜いたかのどちらか。
    """
    if not paragraphs:
        return "空の結果が返りました"

    # index は出力ファイル名 _part{index:02d}.txt になる。重複すると同じファイルに
    # 2回書いて片方が消えるため、1..N の連番であることを先に確かめる。
    idxs = [p.get("index") for p in paragraphs]
    if not all(isinstance(i, int) for i in idxs):
        return f"index が整数でない要素があります: {idxs}"
    if sorted(idxs) != list(range(1, len(idxs) + 1)):
        return f"index が 1..{len(idxs)} の連番になっていません: {sorted(idxs)}"

    for p in paragraphs:
        idx, t = p.get("index"), (p.get("text") or "").strip()
        if len(t) < 50:
            return f"part {idx:02d} が短すぎます（{len(t)}字）"
        # 途中で切れた SSML の典型: 閉じタグが無い / タグの途中で終わっている
        if not t.endswith("</speak>"):
            return f"part {idx:02d} が </speak> で終わっていません（末尾: {t[-40:]!r}）"
        if t.count("<speak>") != 1:
            return f"part {idx:02d} の <speak> が {t.count('<speak>')} 個あります"

    total = sum(len((p.get("text") or "").strip()) for p in paragraphs)
    if total < src_chars * _MIN_RATIO:
        return (
            f"ナレーション合計 {total:,}字 が transcript {src_chars:,}字 の "
            f"{total / src_chars * 100:.0f}%しかありません（下限 {_MIN_RATIO * 100:.0f}%）"
        )
    return None


def _build_prompt(max_chars: int, transcript: str) -> str:
    if max_chars == -1:
        return _PROMPT_UNLIMITED + "\n\n" + transcript
    return _PROMPT_LIMITED.format(max_chars=max_chars) + "\n\n" + transcript


def _split_transcript(text: str, size: int) -> list[str]:
    """transcript を size 文字程度の塊に分ける。文の途中では切らない。

    モデルは渡された transcript 全体を見て「どれだけ書くか」を決めるため、
    長い transcript をまとめて渡すと圧縮する。実測（同じ38,410字の transcript）:

        全文をまとめて渡す        → 60%
        先頭7,000字だけを渡す     → 92%

    塊ごとに独立して書かせれば、それぞれが濃く書かれる。
    """
    if size <= 0 or len(text) <= size:
        return [text]

    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # 話題の変わり目を優先する。段落の切れ目が最も確実な手がかりで、
            # 無ければ文末で切る。塊が偏らないよう後半だけを探索範囲にする。
            lo = start + size // 2
            for marks in (("\n\n",), ("\n",), (". ", "! ", "? ")):
                found = max(text.rfind(m, lo, end) for m in marks)
                if found > start:
                    end = found + len(max(marks, key=lambda m: text.rfind(m, lo, end)))
                    break
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def rewrite_file(
    txt_path: Path,
    output_dir: Path,
    max_chars: int = REWRITE_MAX_CHARS,
    model: str = REWRITE_MODEL,
) -> list[Path]:
    text = txt_path.read_text(encoding="utf-8")
    print(f"  Total chars: {len(text)}  |  max_chars={'unlimited' if max_chars == -1 else max_chars}")

    # transcript が長いと、モデルは全体を見て「どれだけ書くか」を決めて圧縮する。
    # 塊に分けて独立に書かせ、結果を通し番号でつなぐ。
    chunks = _split_transcript(text, max_chars)
    if len(chunks) > 1:
        print(f"  transcript を {len(chunks)} 分割して個別に台本化します"
              f"（1塊あたり約 {len(text) // len(chunks):,}字）")
        results: list[Path] = []
        tail = ""            # 直前の塊の台本の末尾。続きとして書かせるために渡す
        for i, chunk in enumerate(chunks, 1):
            where = "first" if i == 1 else ("last" if i == len(chunks) else "middle")
            print(f"  chunk {i}/{len(chunks)} ({len(chunk):,}字, {where})")
            got = _rewrite_chunk(chunk, txt_path, output_dir, model,
                                 start_index=len(results) + 1,
                                 position=where, index=i, total=len(chunks), tail=tail)
            results.extend(got)
            if got:
                tail = got[-1].read_text(encoding="utf-8")[-_CONTEXT_CHARS:]
        total = sum(len(p.read_text(encoding="utf-8")) for p in results)
        print(f"  合計 {total:,}字 = transcript の {total / len(text) * 100:.0f}%")
        return results

    return _rewrite_chunk(text, txt_path, output_dir, model, start_index=1)


def _rewrite_chunk(
    text: str, txt_path: Path, output_dir: Path, model: str, *, start_index: int,
    position: str = "", index: int = 1, total: int = 1, tail: str = "",
) -> list[Path]:
    """transcript の1塊を台本にする。塊は分割せず1本で書かせる。

    position が指定されていれば、1本の台本の一部として書かせる
    （冒頭のフックと締めは最初と最後の塊だけに書かせ、間は続きとして書く）。
    """
    max_chars = -1  # 塊はすでに十分小さいので、この中では分割させない

    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "required": ["index", "text"],
            "properties": {
                "index": {"type": "INTEGER"},
                "text": {"type": "STRING"},
            },
        },
    }

    if position:
        prompt = _PROMPT_CONTINUATION.format(
            index=index, total=total, position=_POSITION[position],
            context=_CONTEXT_BLOCK.format(tail=tail) if tail else "",
        ) + "\n\n" + text
    else:
        prompt = _build_prompt(max_chars, text)
    paragraphs: list[dict] = []

    # 出力が途中で切れることが実際に起きる（`<break time=` で終わる SSML が
    # 生成された）。壊れた台本をそのまま翻訳まで流さないよう検証し、駄目なら作り直す。
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        # 用語の正確さ・行間の分析・意味単位での分割を同時に要求する最難関の工程。
        # OpenAI 経路では推論を深く使う（Gemini 経路では無視される）。
        raw = llm.generate_json(model, prompt, schema, schema_name="narration_parts", effort="high")
        paragraphs = sorted(json.loads(raw or "[]"), key=lambda x: x["index"])
        problem = _validate(paragraphs, len(text))
        if problem is None:
            break
        if attempt == _MAX_ATTEMPTS:
            raise RuntimeError(f"{txt_path.name}: {problem}（{_MAX_ATTEMPTS}回試行）")
        print(f"    [retry {attempt}/{_MAX_ATTEMPTS - 1}] {problem}")

    results: list[Path] = []
    for offset, p in enumerate(paragraphs):
        idx = start_index + offset          # 塊をまたいで連番になるようずらす
        part_text = p["text"].strip()
        out = output_dir / f"{txt_path.stem}_part{idx:02d}.txt"
        out.write_text(part_text, encoding="utf-8")
        print(f"    part {idx:02d}: {len(part_text)} chars → {out.name}")
        results.append(out)

    return results


def run(
    project: str, *, force: bool = False, max_chars: int | None = None, model: str | None = None
) -> list[Path]:
    """Run rewrite for a project.

    Parts are written to narration/parts/ (intermediate).
    The merged full file lives in narration/ (final output, via concat_narration.py).

    Args:
        force: Delete existing parts and re-run.
        max_chars: Override REWRITE_MAX_CHARS (-1=unlimited, N=split at N chars).
        model: Override REWRITE_MODEL (gpt-* なら OpenAI 経路).
    """
    effective_max = max_chars if max_chars is not None else REWRITE_MAX_CHARS
    active_model = model or REWRITE_MODEL
    src_dir = stage_dir(project, _IN)
    dst_dir = parts_dir(project, _OUT)   # ← narration/parts/
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for txt in sorted(src_dir.glob("*.txt")):
        existing = sorted(dst_dir.glob(f"{txt.stem}_part*.txt"))
        if existing and not force:
            invalid = [f for f in existing if len(f.read_text(encoding="utf-8").strip()) < 50]
            if invalid:
                print(f"  [invalid] {len(invalid)} part(s) too short, regenerating: {[f.name for f in invalid]}")
                for f in existing:
                    f.unlink()
            else:
                print(f"  [skip] {txt.stem} → {len(existing)} part(s) in narration/parts/")
                results.extend(existing)
                continue
        if existing and force:
            for f in existing:
                f.unlink()
            print(f"  [force] removed {len(existing)} existing part(s)")
        print(
            f"  Rewriting: {txt.name}  (max_chars={'unlimited' if effective_max == -1 else effective_max})"
            f"  [{active_model} / {llm.provider(active_model)}]"
        )
        parts = rewrite_file(txt, dst_dir, max_chars=effective_max, model=active_model)
        results.extend(parts)

    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] rewrite")
        run(project)


if __name__ == "__main__":
    run_all()
