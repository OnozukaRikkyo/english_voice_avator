"""Stage narration→narration: 配信前ファクトチェック表の生成。

review は台本を **文字起こしと** 突き合わせる（台本が素材から逸れていないか）。
この工程は視点が違い、**現実と** 突き合わせるべき項目を洗い出す
（素材そのものが誤っていれば review は通してしまう）。

検証はしない。固有名詞・数値・日付・役職など、配信前に人が一次ソースと
照合すべき主張を、リスク順の表にして書き出す。
実在の人物・事件を扱う報道系コンテンツでは、誤りが1つ見つかるだけで
番組全体の信頼が崩れるため、この表が録音前の最終チェックリストになる。

  narration/{stem}_full.txt       ← 読む
  narration/{stem}_factcheck.md   ← 書く（人が読む用）
"""
import re
from pathlib import Path

from . import artifact, llm, ssml
from .config import REVIEW_MODEL, stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["factcheck"]

# ドメインを固定しない。政治・経済・スポーツ・科学・文化・災害のどれでも
# 同じ観点（人物と役職の対応、数値の出典、日付、固有名詞の綴り）が通用する。
_PROMPT = """\
You are the pre-broadcast fact-check desk of a news organisation. From the narration \
script below, extract EVERY claim a fact-checker must verify before publication — \
whatever the field of the story: politics, business, sport, science, culture, disasters.

Extract every:
- proper noun paired with a role or title (a person and their position, a team and its \
league, a company and its market, an agency and its jurisdiction)
- number: sums, statistics, capacities, distances, scores, casualty figures, market data
- date and deadline, including regulation changes and their effective dates
- named place, venue, or facility
- direct causal or superlative claim ("the largest", "the first", "caused by")

For each item give four fields, named here by the column they go in:
- 該当箇所 (Claim): the exact statement as the script words it (short quote)
- 確認すべき点 (What to verify): the concrete way it could be wrong — the title may not \
match the person as of the broadcast date, the figure may conflate revenue with profit, \
the venue name may be misspelled, the rule may have taken effect on another date. \
Name-and-role pairings are the classic AI-introduced error: flag every one.
- 一次ソース (Primary source): the KIND of source that settles it (official filings, league \
or federation records, government registry, peer-reviewed publication, company statements, \
court documents, official casualty reports)
- リスク (Risk): High if an error would misidentify a person, misstate an accusation, a \
casualty figure, or a sum of money; Medium for dates and quantities that shift emphasis; \
Low for the rest

Do NOT verify anything yourself and do NOT guess at answers — produce the checklist, \
not the verdict. Do not skip items because they look obviously true.

# Language

The person who will do the checking works in Japanese; the script is English.
- "確認すべき点" and "一次ソース": write in JAPANESE (です・ます調).
- "該当箇所": quote the English phrase from the script VERBATIM. Never translate it — the \
reader must be able to find it in the script.
- "リスク": use exactly the English words High, Medium, or Low.

Output a markdown document:
- one line in Japanese stating how many items were extracted（例: 「検証項目 84 件」）
- one table, sorted by risk (High first), with these exact column headers:

| 該当箇所 | 確認すべき点 | 一次ソース | リスク |
"""


def factcheck_file(src: Path, dst: Path, model: str = REVIEW_MODEL) -> Path:
    text = ssml.unwrap(src.read_text(encoding="utf-8"))
    print(f"  Fact-check list: {src.name} ({len(text):,} chars)  [{model} / {llm.provider(model)}]")
    table = llm.generate_text(model, _PROMPT + "\n\n--- script ---\n" + text)
    artifact.write_checked(dst, table, min_chars=300, label=f"factcheck/{src.name}")
    # リスク列の値は英語（High/Medium/Low）で固定させている。見出しを日本語にしても
    # 数え方が壊れないよう、セル区切り込みで数える。
    high = len(re.findall(r"\|\s*High\s*\|", table, re.I))
    print(f"    → {dst.name}（high {high} 件）")
    return dst


def run(project: str, *, force: bool = False, model: str | None = None) -> list[Path]:
    """Reads narration/{stem}_full.txt, writes narration/{stem}_factcheck.md."""
    active_model = model or REVIEW_MODEL
    src_dir = stage_dir(project, _IN)
    results: list[Path] = []
    for full in sorted(src_dir.glob("*_full.txt")):
        out = src_dir / f"{full.stem.removesuffix('_full')}_factcheck.md"
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        results.append(factcheck_file(full, out, model=active_model))
    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] factcheck")
        run(project)


if __name__ == "__main__":
    run_all()
