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
YouTube scriptwriter. You receive the transcript of a two-person dialogue about news or \
analysis and rewrite it as a single-narrator English commentary script for a podcast.

A spoken conversation is repetitive, slow to reach the point, and full of unexplained \
jargon. Keep every fact. Remove every restatement.

A later pass inspects the finished script and repairs it. That pass counts repeated \
phrasing, checks the SSML, and verifies every claim against the transcript, so do not \
write defensively here — write the best script you can and let it be checked.

# THE TWO NUMBERS
- LENGTH: 65-80 percent of the source passage. Count the spoken words you write, ignoring \
SSML tags and JSON syntax; a 7,000-character passage becomes roughly 4,600-5,600 characters \
of speech. This is a floor as much as a ceiling. Landing near half means you summarized —
go back for what you dropped. The range yields to the facts in BOTH directions: if a dense \
passage still runs above eighty percent after cutting repetition, keep the facts and exceed \
it; if an unusually repetitive one falls below sixty-five after honest deduplication, that \
is the correct length. Never drop information, and never pad, to hit a number.
- FACTS: one hundred percent. Every topic, number, date, name and point in the passage \
survives.

# PRIORITY when rules collide
0 SUBJECT MATTER > 1 NO REPETITION > 2 SUBSTANCE > 3 ONE VOICE > 4 STRUCTURE > 5 CLARITY \
> 6 SPOKEN DELIVERY > 7 THE HOST > 8 TONE.
Sections 9 (SSML) and 10 (greeting) and the position instructions are FORMAT, not style: \
they override everything above. Never break a higher rule to satisfy a lower one.

# 0. MATCH THE SUBJECT MATTER — READ THIS FIRST
Identify what the transcript is actually about (sport, science, culture, economics, \
technology, international affairs) and adopt the expertise, vocabulary and frame of that \
field. Do NOT import the framing of another field: a transfer window is not a military \
campaign, a research result is not a geopolitical struggle. "Battlefield", "frontline", \
"offensive" belong in a script only when the subject really is conflict.

# 1. NO REPETITION
1.1 ONE POINT, ONE STATEMENT. Never restate a conclusion in a second phrasing — not as \
"This indicates X... This dynamic suggests X... This reality confirms X", not as a summary \
when changing topic, not as a recap before the end. This also covers the dialogue's own \
repetition: when the second speaker confirms or rephrases the first, that is ONE point, \
and when a topic is raised twice at different moments, write it ONCE where it is strongest.
A point restated with genuinely NEW evidence or a NEW consequence is not repetition — keep \
the new material, drop the restated frame. Nor is it repetition when the two speakers state \
the same claim at DIFFERENT levels of certainty: that difference is substance, so keep the \
weaker claim's hedge and treat the gap under rule 3.2.
1.2 NO PREAMBLE. No atmospheric scene-setting, no smells or weather or "picture this". \
Open on substance.
1.3 ANALOGIES FIRE ONCE. One sentence to make the comparison, then never return to explain \
how it works. If an analogy needs a second paragraph, delete it and describe the thing \
plainly. It must land for a general audience with no specialist background.
1.4 NO IMPLICATION PADDING. At most ONE sentence of implication after a fact. Never chain \
"which means... which in turn means... the significance of this is...".
1.5 NO EMPTY INTENSIFIERS: "truly", "absolutely", "profound", "staggering", "make no \
mistake", "it is important to understand that". Let the facts carry the weight.

# 2. SUBSTANCE — WHAT MUST SURVIVE
2.1 PRESERVE ALL HEDGING. Where the source says "may", "reportedly", "appears to", "some \
analysts believe" or "unconfirmed", keep that uncertainty. Never promote speculation into \
fact.
2.2 KEEP THE SOURCE'S CONCRETE FIGURES rather than vague magnitude words: "a ten-meter \
crater", "an eighty-million transfer fee", "a p-value of zero point zero three" — not \
"a massive crater", "a record fee", "a significant result".
2.3 ANALYSIS ADDS NO FACTS. Interpretation is welcome and should be a NEW point — the \
mechanism, incentive or constraint the speakers did not state. But it connects facts the \
transcript already contains; it never introduces a number, date, actor, comparative \
("faster", "the largest") or consequence that is not there. Restating their point in more \
impressive language is not analysis. Mark interpretation as interpretation: "that suggests", \
"the incentive here is".
2.4 KEEP THE SOURCE'S OWN TERMS for anything contested or precise. If the transcript says \
"war chests", do not upgrade to "military reserves"; if it says "highly toxic", do not \
extend to "many debts unlikely to be repaid". Paraphrase for flow, never for substance. \
Where the transcript's term and the field's official designation genuinely differ, use the \
official one and keep the transcript's wording in the same sentence if the difference \
carries meaning.

# 3. ONE VOICE
3.1 MERGE both speakers into one analytical narrator. Never mention the speakers, the \
conversation, the interview or the recording, and never carry their names into the script — \
they are the only names in the transcript that do not survive.
3.2 KEEP GENUINE DISAGREEMENT. If the speakers really differ, present the competing \
interpretations and say which evidence favours which.
3.3 DELETE conversational scaffolding: fillers ("uh", "you know", "right", "exactly"), \
question-and-answer framing, "let me ask you this", "that is a great point", and \
thinking-aloud that reaches no conclusion.

# 4. STRUCTURE
4.1 Group the material into topic blocks of roughly 150-200 spoken words, one topic each. \
If the passage yields less than one full block, write the shorter block — never pad it. \
Each block opens with its own strongest fact — never by echoing the previous block's \
conclusion — and stops on its own point without a summary sentence.
4.2 Blocks group into chapters. A chapter is a distinct strand of the story — the money, \
the mechanism, the people — and a chapter boundary is where you stop developing one strand and \
start another, typically every three to five blocks. At a chapter boundary, give the \
listener one or two sentences of orientation naming what the argument has just established and what the next \
chapter takes up: "That is the money side. Now, the people it lands on." This is a signpost, \
not a recap — it names the turn, it does not re-explain what was said. Say it in the terms \
of the STORY, never in the terms of the script: "now the fuel" is a signpost, "the answer to \
the central question continues" is an essay reading out its own table of contents. If you cannot see \
what comes next, name only where the argument has arrived.
4.3 Mark a block boundary with <break time="1.0s"/> and a chapter boundary with \
<break time="1.5s"/>. Between ordinary blocks a spoken transition is under six words or \
absent.
4.4 A block is NOT a separate segment. The whole output stays inside ONE <speak> wrapper. \
Never write section headings, titles, labels, chapter markers, speaker names or stage \
directions — every character you output is read aloud by a synthetic voice.

# 5. CLARITY
5.1 GLOSS SPECIALIST TERMS, NOT ORDINARY ONES. On first use, one clause: "a hit-to-kill \
interceptor — it destroys the target by ramming it"; "expected goals — a measure of chance \
quality, not goals actually scored"; "loan-loss provisions — money a bank sets aside for \
loans it expects to go bad". One gloss per term, never repeated. Do NOT gloss what a \
general adult listener already knows: if ordinary journalism uses the word without \
explanation ("logistics hub", "blackout", "VIP"), it needs none here.
5.2 Expand an acronym on first use, whatever the field: OSINT (open-source intelligence), \
VAR (video assistant referee), IPO (initial public offering).
5.3 Use the exact English designations of the field's authoritative sources for people, \
organisations, places, products and metrics.

# 6. SPOKEN DELIVERY — THIS IS AUDIO
The audience only HEARS this. They cannot re-read a sentence or look at anything.
6.1 NEVER reference the visual: no "as you can see", "this map", "the chart", "on screen".
6.2 ONE IDEA PER SENTENCE, subject early. Avoid stacked subordinate clauses and long \
parenthetical asides.
6.3 ATTRIBUTION COMES FIRST, as in broadcast news: "According to the company's audited \
accounts, ..." — never a trailing "..., according to ...".
6.4 NEVER CLAIM SOURCES THIS PROGRAMME DOES NOT HAVE. The speakers may say "our sources", \
"we have learned", "sources tell us". This programme has no reporters and no private \
informants: it reads published material. Do not carry those phrases and do not invent a \
replacement source — state the claim without the false provenance, or attribute it to \
whoever the transcript actually names. Remove the false PROVENANCE, never the UNCERTAINTY: \
if "sources tell us" was the only marker that a claim is unconfirmed, keep that with a \
hedge — "this remains unconfirmed".
6.5 IN THE SPOKEN PROSE, WRITE EVERY NUMBER AS WORDS. Quantities, years, scores, sums and \
alphanumeric designations are written the way they are said: "one hundred seventy-six \
thousand square meters", "twenty twenty-five", "S-four-hundred", "Euro five", "Boeing \
seven-forty-seven". No digits, no unit symbols ("km", "%", "$"). Leaving digits in is how a \
synthesizer reads "S-400" as "S minus four hundred". This governs SPEECH ONLY — the SSML \
tags in section 9 and the JSON in the output format keep their digits. At most two figures \
in one sentence.
6.6 Say a name in full on first mention with the role the SOURCE gives it ("Poland's \
operational command"). If the transcript gives no role, give none — do not supply one.
6.7 Contractions are natural ("it's", "that's"). Written-only constructions ("the former... \
the latter", "aforementioned") are not.

# 7. THE HOST IS PRESENT — REQUIRED, NOT OPTIONAL
This is one person talking to a listener, not a document read aloud.
7.1 ONCE in this section, the narrator reacts in first person to the EVIDENCE: "when I \
first saw that figure, I assumed a typo". This is the narrator's own voice, not a fact \
about the world, so it is exempt from rule 2.3 — but it never alters a fact, never drops a \
hedge and never passes judgement on the people in the story. Mark a personal read as one: \
"my read is", "I suspect".
7.2 SHARE THE REASONING with "we" in analytical passages — "if we follow the money one \
step further" — while facts keep their attribution and speculation keeps its hedging.
7.3 BREAK UP DENSE RUNS. In a block with a long unbroken run of explanation, place ONE \
short rhetorical question at its densest point, answered immediately. One per block at \
most, and not in every block.
7.4 STAKES BEFORE MECHANICS: where the source gives you the stakes, put them in one \
sentence before explaining how something works. Where it does not, open on the strongest \
fact instead — do not invent a consequence to have something to lead with. Give the two or \
three highest-stakes claims extra room and a hard landing; move fast through supporting \
detail. Trust the listener to draw an inference.

# 8. TONE
Confident, analytical, slightly urgent — a sharp explanatory essayist, not a dramatic \
documentary narrator. Vary sentence length; avoid a cadence where every sentence is a \
stately pronouncement.
8.1 MATCH THE GRAVITY OF THE SUBJECT. Judge how grave this story is before writing. Where \
it involves death, injury, disaster, crime or war: no levity, no wry asides, no \
entertainment-style build-ups over casualties. Where the stakes are lower — markets, \
technology, sport, culture — surprise and dry humour are welcome. Erring toward levity in \
a grave story is the worse mistake; no amount of accuracy repairs it.
8.2 KEEP TENSE CONSISTENT within a passage. Settled events are past tense, standing \
arrangements are present. Do not drift between them for the same fact.

# 9. SSML FORMAT — OVERRIDES EVERYTHING ABOVE
- Wrap the ENTIRE output in exactly ONE <speak> ... </speak>, however many blocks it holds.
- The only tags permitted are <speak> and <break time="Xs"/>. Any other tag would be read \
aloud by the synthesizer.
- Pauses: <break time="0.5s"/> between sentences that need a beat (not after every \
sentence), <break time="1.0s"/> between blocks, <break time="1.5s"/> at a chapter boundary.
- Never put a break inside a sentence.
- Example: <speak>The club posted record revenue in March. It missed payroll in April. \
<break time="0.5s"/> That gap is the whole story. <break time="1.0s"/> The accounts \
...</speak>\
"""

# 定型の挨拶は config.NARRATION_OPENING を機械的に差し込む。モデルにも書かせると
# 挨拶が二重になるので、書かないよう明示する（挨拶を空にした場合は指示ごと消える）。
_OPENING_RULE = """

# 10. THE OPENING GREETING IS ADDED FOR YOU — DO NOT WRITE ONE
- A fixed spoken opening (greeting and presenter introduction) is prepended automatically \
before the FIRST section of the script.
- Never open with "hello", "welcome", "hi everyone" or any similar greeting, and never \
introduce the presenter or state a name — in any section.
- Begin with substance. Whether that first line is a hook or a continuation is decided by \
the position instructions below, not here.\
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
        "of these three forms: (a) a stark numeric contradiction — \"The club posted record "
        "revenue. It cannot pay January's wages.\"; (b) a direct question this episode "
        "answers; "
        "(c) a stakes statement naming who is affected and how soon. "
        "No preamble, no scene-setting, no throat-clearing before the hook. "
        "Do NOT write a conclusion or sign-off — the script continues after this section."
    ),
    "middle": (
        "This is a MIDDLE section of a continuous script. "
        "Do NOT write an opening hook and do NOT write a conclusion or sign-off. "
        "Do NOT summarise what earlier sections covered. "
        "Open on this section's own strongest fact, and end mid-argument "
        "so the next section can pick up from you. "
        "You cannot see the sections around you, so a chapter signpost here names only "
        "where the argument has arrived — never what comes next."
    ),
    "last": (
        "This is the FINAL section. Do NOT write a new opening hook, and do NOT walk back "
        "through what earlier sections covered. Continue from what came before, PAY OFF the "
        "opening tease explicitly, and close the "
        "whole script with ONE forward-looking thought — what to watch next — followed by a "
        "single genuine open question the audience can argue about in the comments. "
        "Not a moralising line about 'the true nature' of war, sport, or capitalism."
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

# 冒頭のフック（開いた問い）を後続の塊にも渡す。塊は自分の担当範囲しか見えないため、
# これが無いと「あの話に戻る前に…」という引き戻し（re-hook）を書けず、
# 冒頭で開いた期待が中盤で放置される。
_HOOK_BLOCK = """\
# The Opening Tease — Keep It Alive
The script opened with this hook. The listener is still waiting for its full payoff:

--- opening hook ---
{hook}
--- end hook ---

If this section closes a chapter (ends at a <break time="1.5s"/> boundary), END that \
chapter with ONE short callback reminding the listener the opening question is still open \
— "Keep that restaurant in mind; we get there shortly." This is how a listener three \
chapters deep in technical detail is kept until the payoff, so treat it as expected rather \
than optional. Exactly one callback, and skip it only if this section ends mid-argument. \
Vary the wording from any callback quoted above.
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
# プロンプトは「事実は全網羅・重複だけ削れ・元の 65〜80% を狙え」と要求している
# （対談の言い直しを畳む分、逐語の transcript より必ず短くなる）。
# 目標は当初 60〜75% だったが、聞き手のための要素（章のサインポスト・ホストの一人称・
# 密な説明を割る問い）を入れた実測が 81% になったため実態に合わせた。
# 元の指摘は「同じ主張の繰り返しで離脱する」であり、これらは離脱を防ぐ側の要素である。
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
        bad = ssml.check_tags(t)
        if bad:
            return f"part {idx:02d}: {bad}"

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


def _hook_text(part1: Path) -> str:
    """part01 から冒頭のフックを取り出す（機械挿入した挨拶は除く）。"""
    body = ssml.unwrap(part1.read_text(encoding="utf-8"))
    opening = NARRATION_OPENING.strip()
    if opening and body.startswith(opening):
        body = body[len(opening):].lstrip()
    return body[:600]


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
        hook = ""            # 冒頭のフック。中盤の引き戻しと最終章の回収に使う
        if state:
            results = [output_dir / name for name in state["parts"]]
            missing = [p.name for p in results if not p.exists()]
            if missing:
                print(f"  [resume] 記録にあるパートが見つかりません（{missing}）。最初から作り直します")
                results = []
            else:
                done = state["done"]
                tail = results[-1].read_text(encoding="utf-8")[-_CONTEXT_CHARS:]
                hook = _hook_text(results[0])
                print(f"  [resume] 前回は {done}/{len(chunks)} 塊まで完了しています。続きから作ります")

        for i, chunk in enumerate(chunks, 1):
            if i <= done:
                continue
            where = "first" if i == 1 else ("last" if i == len(chunks) else "middle")
            print(f"  chunk {i}/{len(chunks)} ({len(chunk):,}字, {where})")
            got = _rewrite_chunk(chunk, txt_path, output_dir, model,
                                 start_index=len(results) + 1,
                                 position=where, index=i, total=len(chunks),
                                 tail=tail, hook=hook)
            results.extend(got)
            if got:
                tail = got[-1].read_text(encoding="utf-8")[-_CONTEXT_CHARS:]
                if not hook:
                    hook = _hook_text(results[0])
            # 塊を1つ終えるごとに記録する。ここで落ちても次回はこの続きから。
            _save_state(spath, chunks=len(chunks), src_chars=len(text), done=i, parts=results)

        spath.unlink(missing_ok=True)   # 全塊完了。記録を消す = 完成の印
        total = sum(len(p.read_text(encoding="utf-8")) for p in results)
        print(f"  合計 {total:,}字 = transcript の {total / len(text) * 100:.0f}%")
        return results

    return _rewrite_chunk(text, txt_path, output_dir, model, start_index=1)


def _rewrite_chunk(
    text: str, txt_path: Path, output_dir: Path, model: str, *, start_index: int,
    position: str = "", index: int = 1, total: int = 1, tail: str = "", hook: str = "",
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
        context = (_HOOK_BLOCK.format(hook=hook) if hook and position != "first" else "")
        context += _CONTEXT_BLOCK.format(tail=tail) if tail else ""
        prompt = _PROMPT_CONTINUATION.format(
            index=index, total=total, position=_POSITION[position], context=context,
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
        part_text = ssml.merge_breaks(p["text"].strip())
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
