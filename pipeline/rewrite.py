"""Stage transcript→narration: English transcript → narration script (SSML).

REWRITE_MAX_CHARS in config.py は **transcript を何文字ずつモデルに渡すか**。
  N   → transcript を N 文字ずつに分け、塊ごとに台本化して連結する
  -1  → 分割せず全文を1回で渡す（短い transcript 向け）

モデルは渡された transcript 全体を見て「どれだけ書くか」を決めるため、
長い transcript をまとめて渡すと圧縮する。塊に分けると各塊が濃く書かれる。
塊は独立に書かせるのではなく、位置（最初/中間/最後）と直前の台本の末尾を
渡して1本の台本として繋げる。
"""
import json
from pathlib import Path

from . import llm, ssml
from .config import (
    REWRITE_MODEL, REWRITE_MAX_CHARS, NARRATION_OPENING,
    stage_dir, parts_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["rewrite"]

# ── Shared role + content instructions ────────────────────────────────────────

_ROLE_BASE = """\
# Role & Objective
You are a subject-matter expert in whatever field the transcript covers, and a high-impact \
YouTube scriptwriter. You will receive a transcript of a two-person dialogue discussing news \
or analysis. Rewrite it as a single-narrator English commentary script that is TIGHT, \
CONCRETE, and FAST-MOVING.

The source is a spoken conversation, so it is repetitive, slow to reach the point, and full \
of unexplained jargon. Your job is to keep every fact and remove every restatement.

TWO NUMBERS GOVERN EVERYTHING YOU WRITE:
- LENGTH: the narration must land at 60-75 percent of the source passage's character count. \
This is a FLOOR as much as a ceiling — a passage of 7,000 characters must produce roughly \
4,200-5,200 characters. If your draft comes out near half the source or less, you have \
summarized instead of rewritten: go back and carry the facts you dropped. Tight prose that \
omits information is a failure, not a virtue.
- FACTS: one hundred percent. Every topic, number, date, name, and point in the passage \
appears in the narration. What gets cut is repetition, never information.

PRIORITY ORDER when instructions compete:
0 SUBJECT MATTER > 1 STRICT RULES > 2 FIDELITY > 3 DIALOGUE COLLAPSE > 4 STRUCTURE \
> 5 CLARITY > 6 SPOKEN DELIVERY > 7 ENGAGEMENT.
Never break a higher-priority rule in order to satisfy a lower one.

# 0. MATCH THE SUBJECT MATTER — READ THIS FIRST
- Identify what the transcript is actually about (sport, science, culture, economics, \
technology, international affairs) and adopt the expertise, vocabulary, and frame of \
reference of that field.
- Do NOT impose the framing of an unrelated field. A transfer window is not a military \
campaign; a research result is not a geopolitical struggle. Words like "battlefield", \
"frontline", "offensive" or "geopolitical" belong in a script only when the subject really \
is conflict.

# 1. STRICT RULES — NON-NEGOTIABLE
1.1 ONE POINT, ONE STATEMENT. Never restate a conclusion in a second phrasing. \
The banned pattern is: "This indicates X. ... This dynamic suggests X. ... This reality \
confirms X." State the point once, in its strongest form, then move to the NEXT point.
1.2 NO SCENE-SETTING PREAMBLE. No atmospheric openings — no smells, weather, quiet fields, \
no "picture this". Open on substance.
1.3 METAPHORS AND ANALOGIES FIRE ONCE. Use one sentence to make the comparison, then never \
return to explain how the analogy works or map it back to the subject. If an analogy needs a \
second paragraph to land, delete it and describe the thing plainly.
1.4 NO RECAP, ANYWHERE. Do not summarize what you have already said — not when changing \
topic, not before a conclusion, not at the end. The listener heard it a minute ago.
1.5 NO IMPLICATION PADDING. After a fact, allow at most ONE sentence of implication. Never \
chain "which means ... which in turn means ... the significance of this is ...".
1.6 VARY SENTENCE LENGTH. Alternate short declaratives with longer explanatory sentences. \
Avoid a uniform cadence where every sentence is a stately pronouncement.
1.7 CUT GENERIC TRANSITIONS. "This brings us to", "Now, shift your focus to", "With that in \
mind" — use almost never. Start the new topic with its own strongest fact instead.
1.8 NO EMPTY INTENSIFIERS. Cut "truly", "absolutely", "profound", "staggering", "make no \
mistake", "it is important to understand that". Let the numbers carry the weight.

# 2. FIDELITY — WHAT MUST SURVIVE
2.1 COVER EVERY topic, event, location, number, date, name, and analytical point in the \
source passage. Do not drop a section. Compression here means deleting REPETITION — never \
deleting INFORMATION.
2.2 Length must come from carrying more facts, not from saying one fact more ways — the \
60-75 percent target at the top of this prompt is reached by keeping information, never by \
padding. The per-block length in section 4 governs ONE block, never the whole output.
2.3 PRESERVE ALL HEDGING. Where the source says "may", "reportedly", "appears to", "some \
analysts believe", or "unconfirmed", keep that uncertainty in English. Never promote \
speculation into stated fact.
2.4 PREFER THE SOURCE'S CONCRETE NUMBERS over vague magnitude words: "a 10-meter crater", \
"1.2 billion dollars", "since March 2026" — not "a massive crater", "a huge sum", "recently".
2.5 Analysis is welcome, but it must be a NEW point — the underlying intent, mechanism, \
incentive, or constraint that the speakers did not state. Restating their point in more \
impressive language is not analysis.
2.6 ANALYSIS ADDS NO FACTS. Interpretation connects facts already in the transcript; it \
never introduces new ones. Adding a number, a date, an actor, a comparative ("faster", \
"the largest"), or a stated consequence that the transcript does not contain is not \
analysis — it is fabrication, and it is the single most common defect in rejected drafts. \
Frame interpretation as interpretation ("that suggests...", "the incentive here is...") \
and build it only from what the source gives you.
2.7 QUOTE THE SOURCE'S OWN TERMS for anything contested or precise. If the transcript says \
"war chests", do not upgrade it to "military reserves"; if it says the portfolio is \
"highly toxic", do not extend that to "many debts unlikely to be repaid". Paraphrase \
freely for flow — never for substance.

# 3. DIALOGUE INTO ONE VOICE
Most of the source's redundancy is structural: one speaker makes a point, the other agrees \
and restates it in different words. Removing that is your single biggest job.
3.1 MERGE both speakers into ONE analytical voice. Never mention the speakers, the \
conversation, the interview, or the recording. No "as my co-host noted".
3.2 COLLAPSE AGREEMENT EXCHANGES. When the second speaker confirms, echoes, or rephrases the \
first, that is ONE point — write it once, keeping whichever version is more concrete.
3.3 KEEP GENUINE DISAGREEMENT. If the speakers really differ, that is real content: present \
the competing interpretations and say which evidence favours which.
3.4 DELETE conversational scaffolding entirely — fillers ("uh", "you know", "right", \
"exactly", "yeah"), question-and-answer framing, "let me ask you this", "that is a great \
point", and thinking-aloud that reaches no conclusion.
3.5 If the same topic is raised twice at different moments of the conversation, write it \
ONCE, at the point where it is strongest.

# 4. STRUCTURE
4.1 Organise the material into distinct topic blocks — ONE topic per block, roughly 150-200 \
spoken words each. Split a topic that runs longer rather than letting one block sprawl.
4.2 Each block OPENS with its own strongest fact or claim, standing on its own. Do not open \
a block by echoing the previous block's conclusion.
4.3 Each block CLOSES on its own point and stops. No summary sentence.
4.4 Mark every block boundary with <break time="1.0s"/> — that pause is what tells the \
listener a new topic has started. A block is NOT a separate segment: the whole output stays \
inside ONE <speak> wrapper and blocks are divided by that break tag alone. Never open a \
second <speak>. Do NOT write section headings, titles, labels, chapter markers, speaker \
names, or stage directions — every character you output is read aloud by a synthetic voice.
4.5 A spoken transition between blocks, if used at all, is under six words.

# 5. CLARITY
5.1 Gloss every technical or military term on FIRST use with one clause of plain English, \
then use it freely: "a hit-to-kill interceptor — it destroys the target by ramming it, not \
by exploding nearby". One gloss per term, never repeated.
5.2 Expand every acronym on first use: OSINT (open-source intelligence), FPV \
(first-person-view) drone, PAC-3 MSE.
5.3 Use the exact, globally recognised English spellings and designations of that field's \
authoritative sources — for people, organisations, places, products, systems, designations, \
and metrics. Not informal or approximate terms.
5.4 Any analogy must be recognisable to a general English-speaking audience with no \
specialist background. If the analogy itself needs teaching, replace it with a plain \
description.

# 6. SPOKEN DELIVERY — THIS IS AUDIO
The script is read aloud and broadcast as a podcast. The audience only HEARS it; they \
cannot re-read a sentence or look at anything.
6.1 NEVER reference the visual. No "as you can see", "this map", "the chart", "look at", \
"pictured here", "on screen".
6.2 ONE IDEA PER SENTENCE, subject early. Avoid stacked subordinate clauses and long \
parenthetical asides — the ear loses them.
6.3 ATTRIBUTION COMES FIRST, as it does in broadcast news: "According to Ukraine's General \
Staff, ..." — not the claim followed by a trailing "..., according to ...".
6.4 Write numbers and symbols so they are spoken correctly and held by ear: "seventeen \
kilometers", "1.2 billion dollars", "thirty percent". No bare digits with unit symbols, no \
"km", "%", "$", "approx.". At most two figures in one sentence; split the rest out.
6.5 Say a name in full on first mention with its role ("Poland's operational command"), then \
use the short form. Never introduce an unexplained name and leave it hanging.
6.6 Contractions are fine and natural ("it's", "that's"). Written-only constructions \
("the former ... the latter", "aforementioned", "cf.") are not.

# 7. ENGAGEMENT
7.1 STAKES BEFORE MECHANICS. One sentence on why it matters, then how it works.
7.2 Give the two or three highest-stakes claims extra room and a hard landing sentence. \
Move fast through the supporting detail.
7.3 Rhetorical questions are allowed but rare — at most one per topic block, and only when \
the script answers it immediately.
7.4 Trust the audience. Do not spell out an inference an attentive viewer can make.

# 8. TONE
Confident, analytical, slightly urgent — a sharp explanatory YouTube essayist, not a dramatic \
documentary narrator. Authoritative, objective, aimed at a global audience.

# 9. SSML FORMATTING — REQUIRED
- Wrap the ENTIRE output in exactly ONE <speak> ... </speak>. One opening tag, one closing \
tag, no matter how many topic blocks the text contains.
- Insert <break time="Xs"/> tags at natural spoken pauses:
  - Between sentences that need a beat: <break time="0.5s"/> (not after every sentence)
  - Between topic blocks: <break time="1.0s"/>
  - At major transitions (hook into body, body into conclusion): <break time="1.5s"/>
- Do NOT add breaks in the middle of a sentence.
- Example: <speak>The crater should have been twenty meters wide. It was ten. \
<break time="0.5s"/> That gap is the whole story. <break time="1.0s"/> The warhead ...</speak>\
"""

# 定型の挨拶は config.NARRATION_OPENING を機械的に差し込む。モデルにも書かせると
# 挨拶が二重になるので、書かないよう明示する（挨拶を空にした場合は指示ごと消える）。
_OPENING_RULE = """

# 10. THE OPENING GREETING IS ADDED FOR YOU — DO NOT WRITE ONE
- A fixed spoken opening (greeting and presenter introduction) is prepended automatically \
before your text.
- Do NOT open with "hello", "welcome", "hi everyone", or any similar greeting.
- Do NOT introduce the presenter or state a name.
- Begin directly with the hook — the first line of substance.\
"""

_ROLE = _ROLE_BASE + (_OPENING_RULE if NARRATION_OPENING.strip() else "")

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
        "This is the OPENING section. Its first two sentences are the hook. Use exactly ONE "
        "of these three forms: (a) a stark numeric contradiction — \"The crater should have "
        "been twenty meters wide. It was ten.\"; (b) a direct question this video answers; "
        "(c) a stakes statement naming who is affected and how soon. "
        "No preamble, no scene-setting, no throat-clearing before the hook. "
        "Do NOT write a conclusion or sign-off — the script continues after this section."
    ),
    "middle": (
        "This is a MIDDLE section of a continuous script. "
        "Do NOT write an opening hook and do NOT write a conclusion or sign-off. "
        "Do NOT summarise what earlier sections covered. "
        "Open on this section's own strongest fact, and end mid-argument "
        "so the next section can pick up from you."
    ),
    "last": (
        "This is the FINAL section. Do NOT write a new opening hook, and do NOT walk back "
        "through what earlier sections covered. Continue from what came before and close the "
        "whole script with ONE forward-looking thought — what to watch next — followed by a "
        "single genuine open question the audience can argue about in the comments. "
        "Not a moralising line about the true nature of modern warfare."
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

# 作り直しのときだけ足す。何が駄目だったかを伝えないと、モデルは同じ失敗を繰り返す。
# 長さ不足を指摘したときに「もっと削る」方向へ行かないよう、直し方も添える。
_RETRY_BLOCK = """

# YOUR PREVIOUS ATTEMPT WAS REJECTED — READ THIS FIRST
{problem}

Return the whole section again with exactly that defect fixed. Keep everything else.
If the complaint is about length, the fix is to carry MORE of the source's facts —
never to compress harder. If it is about the SSML, remember that the entire section is
one <speak> wrapper and topic blocks are separated by <break time="1.0s"/> alone.
"""

# ナレーション合計が transcript のこの割合を下回ったら生成失敗とみなす。
#
# プロンプトは「事実は全網羅・重複だけ削れ・元の 60〜75% を狙え」と要求している
# （対談の言い直しを畳む分、逐語の transcript より必ず短くなる）。
# 分割ありの実測は 51%、短い入力では 116% に達する。
# 30% では明らかな要約（38,410字→11,774字＝31%）を通してしまったため引き上げた。
#
# 下限を上げすぎると、話者が繰り返しの多い喋り方をした回で誤検出しうる。
# その場合は再生成が走るだけで壊れた成果物は残らないが、料金は増える。
_MIN_RATIO = 0.45


def _validate(paragraphs: list[dict], src_chars: int) -> str | None:
    """生成結果を検証する。問題なければ None、あれば理由の文字列を返す。

    プロンプトは「事実は全網羅・削るのは重複だけ」と要求しているので、
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


# ── 途中経過の記録 ─────────────────────────────────────────────────────────────
#
# 長い transcript は塊ごとにAPIを呼ぶため、7塊目で失敗すると6塊分だけが
# ディスクに残る。パートの有無だけを見ていると、この中途半端な台本を
# 「生成済み」と判定して翻訳・動画生成まで流してしまう。
#
# そこで塊ごとに進捗を書き、全部終わったら消す。
# **この記録が残っている = 未完成** であり、次の実行は続きから作り直す。

_STATE_SUFFIX = "_rewrite_state.json"


def state_path(output_dir: Path, stem: str) -> Path:
    return output_dir / f"{stem}{_STATE_SUFFIX}"


def _load_state(path: Path, chunks: int, src_chars: int) -> dict | None:
    """前回の途中経過を読む。今回の入力と食い違っていれば捨てる。"""
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # transcript が差し替わった / 分割数が変わった場合、前回のパートは繋がらない
    if state.get("chunks") != chunks or state.get("src_chars") != src_chars:
        return None
    if not isinstance(state.get("done"), int) or not (0 < state["done"] < chunks):
        return None
    return state


def _save_state(path: Path, *, chunks: int, src_chars: int, done: int, parts: list[Path]) -> None:
    path.write_text(json.dumps({
        "chunks": chunks, "src_chars": src_chars, "done": done,
        "parts": [p.name for p in parts],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _with_opening(part_text: str) -> str:
    """台本の先頭に定型の挨拶を差し込む（part01 だけに適用する）。

    挨拶は <speak> の外に置けない。SSML として妥当でなくなるうえ、
    heygen は1パートを1本の動画として送るため、中に入れないと読まれない。
    """
    opening = NARRATION_OPENING.strip()
    if not opening:
        return part_text
    return ssml.wrap(opening + "\n\n" + ssml.unwrap(part_text))


def _build_prompt(max_chars: int, transcript: str) -> str:
    if max_chars == -1:
        return _PROMPT_UNLIMITED + "\n\n" + transcript
    return _PROMPT_LIMITED.format(max_chars=max_chars) + "\n\n" + transcript


def split_transcript(text: str, size: int) -> list[str]:
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
    chunks = split_transcript(text, max_chars)
    if len(chunks) > 1:
        print(f"  transcript を {len(chunks)} 分割して個別に台本化します"
              f"（1塊あたり約 {len(text) // len(chunks):,}字）")

        # 前回が途中で終わっていれば、済んだ塊は作り直さず続きから
        spath = state_path(output_dir, txt_path.stem)
        state = _load_state(spath, len(chunks), len(text))
        results: list[Path] = []
        done = 0
        tail = ""            # 直前の塊の台本の末尾。続きとして書かせるために渡す
        if state:
            results = [output_dir / name for name in state["parts"]]
            missing = [p.name for p in results if not p.exists()]
            if missing:
                print(f"  [resume] 記録にあるパートが見つかりません（{missing}）。最初から作り直します")
                results = []
            else:
                done = state["done"]
                tail = results[-1].read_text(encoding="utf-8")[-_CONTEXT_CHARS:]
                print(f"  [resume] 前回は {done}/{len(chunks)} 塊まで完了しています。続きから作ります")

        for i, chunk in enumerate(chunks, 1):
            if i <= done:
                continue
            where = "first" if i == 1 else ("last" if i == len(chunks) else "middle")
            print(f"  chunk {i}/{len(chunks)} ({len(chunk):,}字, {where})")
            got = _rewrite_chunk(chunk, txt_path, output_dir, model,
                                 start_index=len(results) + 1,
                                 position=where, index=i, total=len(chunks), tail=tail)
            results.extend(got)
            if got:
                tail = got[-1].read_text(encoding="utf-8")[-_CONTEXT_CHARS:]
            # 塊を1つ終えるごとに記録する。ここで落ちても次回はこの続きから。
            _save_state(spath, chunks=len(chunks), src_chars=len(text), done=i, parts=results)

        spath.unlink(missing_ok=True)   # 全塊完了。記録を消す = 完成の印
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
    problem: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        # 用語の正確さ・行間の分析・意味単位での分割を同時に要求する最難関の工程。
        # OpenAI 経路では推論を深く使う（Gemini 経路では無視される）。
        #
        # 応答が壊れること自体は起きる（出力上限での打ち切り、同じ文の繰り返しで
        # 巨大化するなど）。壊れた応答は例外で落とさず、この工程の他の失敗と同じく
        # 作り直しの対象として扱う。
        raw = ""
        try:
            raw = llm.generate_json(
                model,
                prompt + (_RETRY_BLOCK.format(problem=problem) if problem else ""),
                schema, schema_name="narration_parts", effort="high")
            paragraphs = sorted(json.loads(raw or "[]"), key=lambda x: x["index"])
            problem = _validate(paragraphs, len(text))
        except llm.IncompleteResponse as e:
            paragraphs, problem = [], str(e)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            paragraphs = []
            problem = f"応答がJSONとして読めません（{len(raw or ''):,}字, {type(e).__name__}: {e}）"
        if problem is None:
            break
        if attempt == _MAX_ATTEMPTS:
            raise RuntimeError(f"{txt_path.name}: {problem}（{_MAX_ATTEMPTS}回試行）")
        print(f"    [retry {attempt}/{_MAX_ATTEMPTS - 1}] {problem}")

    results: list[Path] = []
    for offset, p in enumerate(paragraphs):
        idx = start_index + offset          # 塊をまたいで連番になるようずらす
        part_text = p["text"].strip()
        if idx == 1:                        # 台本全体の先頭。挨拶はここにだけ入る
            part_text = _with_opening(part_text)
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
        spath = state_path(dst_dir, txt.stem)
        # 途中経過の記録が残っている = 前回が最後まで終わっていない。
        # パートが揃って見えても完成ではないので、スキップしてはならない。
        unfinished = spath.exists()
        if existing and not force and not unfinished:
            invalid = [f for f in existing if len(f.read_text(encoding="utf-8").strip()) < 50]
            if invalid:
                print(f"  [invalid] {len(invalid)} part(s) too short, regenerating: {[f.name for f in invalid]}")
                for f in existing:
                    f.unlink()
            else:
                print(f"  [skip] {txt.stem} → {len(existing)} part(s) in narration/parts/")
                results.extend(existing)
                continue
        if existing and unfinished and not force:
            print(f"  [incomplete] {txt.stem} は前回途中で終わっています（{len(existing)} part(s)）")
        if force:
            for f in existing:
                f.unlink()
            spath.unlink(missing_ok=True)
            if existing:
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
