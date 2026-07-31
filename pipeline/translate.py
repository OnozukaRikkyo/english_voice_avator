"""Stage narration→translation: English narration → Japanese (Gemini).

Reads:  narration/{stem}_full.txt   (full English narration)
Writes: translation/{stem}_ja.txt   (Japanese translation)

The _ja suffix makes the language explicit, enabling future additions
like _zh.txt, _ko.txt without ambiguity.
"""
from pathlib import Path

from . import artifact, llm
from .config import TRANSLATE_MODEL, stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["translate"]

_PROMPT = """\
You are a professional Japanese translator specializing in geopolitical analysis \
and military OSINT content for YouTube audiences.

Translate the following English narration script into natural, fluent Japanese. \
Preserve the analytical, authoritative tone and all proper nouns \
(place names, weapon systems, unit names) in their standard Japanese usage \
as seen in NHK, Asahi, or Yomiuri reporting. \
Do not add explanations or translator notes.

Formatting — REQUIRED (the input is SSML; the output must NOT be):
- The input is wrapped in <speak>...</speak> and contains <break time="Xs"/> tags. \
These drive the English text-to-speech and have no place in the translation.
- Remove ALL SSML tags. Do not output <speak>, </speak>, or any <break> tag.
- Replace each <break> with a line break, so the Japanese keeps the same \
sentence and paragraph rhythm as the original.
- Use polite form (です・ます調) throughout.

Output the plain Japanese text only.

"""


def translate_file(src: Path, dst: Path, model: str = TRANSLATE_MODEL) -> Path:
    text = src.read_text(encoding="utf-8").strip()
    print(f"  Translating: {src.name} ({len(text)} chars)  [{model} / {llm.provider(model)}]")

    translated = llm.generate_text(model, _PROMPT + text)
    # 英→日は概ね入力の30〜50%の文字数に収まる。20%を下回るのは訳し漏れか途中切れ。
    artifact.write_checked(
        dst, translated, min_chars=100,
        src_chars=len(text), min_ratio=0.20, label=f"translate/{src.name}",
    )
    print(f"    → {dst.name} ({len(translated)} chars)")
    return dst


def run(project: str, *, force: bool = False, model: str | None = None) -> list[Path]:
    active_model = model or TRANSLATE_MODEL
    src_dir = stage_dir(project, _IN)    # narration/
    dst_dir = stage_dir(project, _OUT)   # translation/
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for full_txt in sorted(src_dir.glob("*_full.txt")):
        base = full_txt.stem.removesuffix("_full")
        out = dst_dir / f"{base}_ja.txt"
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        translate_file(full_txt, out, model=active_model)
        results.append(out)

    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] translate")
        run(project)


if __name__ == "__main__":
    run_all()
