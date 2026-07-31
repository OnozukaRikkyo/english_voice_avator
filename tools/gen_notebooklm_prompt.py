#!/usr/bin/env python3
"""Generate NotebookLM prompts from Japanese scenario documents (docx / pdf).

Scans data/senario_jp/ for .docx and .pdf files. For each file the configured
model (NOTEBOOKLM_PROMPT_MODEL — gpt-* → OpenAI, else Gemini) reads it with web
search enabled and writes one NotebookLM system prompt containing:
  1. A Role & Objective matched to the document's domain
  2. A Document-Specific Vocabulary Guide of the genuinely unfamiliar terms
  3. Core Instructions naming the authoritative sites to verify against

Usage:
  ./gen_notebooklm_prompt.sh
  ./gen_notebooklm_prompt.sh --model-notebooklm gemini-3.6-flash
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import llm
from pipeline.config import NOTEBOOKLM_PROMPT_MODEL, PRESETS, resolve_models

SENARIO_DIR = ROOT / "data" / "senario_jp"
OUTPUT_DIR  = SENARIO_DIR / "prompts"
INPUT_EXTS  = {".docx", ".pdf"}

# ── メタプロンプト（プロンプトを書かせるプロンプト）────────────────────────────────────────────────────────

_META_PROMPT = """\
You are an expert analyst and YouTube scriptwriting consultant. \
You have access to Google Search — use it actively to look up terms, verify English \
designations, and find authoritative sources for the content in the document below.

A Japanese document is provided below. Read it carefully, identify its domain, \
then write ONE complete NotebookLM system prompt in English.

The prompt you write must:

1. Open with a Role & Objective paragraph that names the appropriate expert role \
for this domain and states the task: transform the uploaded Japanese sources into a \
compelling English YouTube commentary script.

2. Include a Document-Specific Vocabulary Guide (labeled as such, with sub-heading \
"Auto-generated from source document — verify before use"). \
Target audience: a general American adult with no specialist knowledge of this domain. \
Include ONLY terms that would genuinely confuse or be unfamiliar to this audience — \
obscure place names, specific technical designations, domain jargon, acronyms, or proper \
nouns that require context. Do NOT include widely known terms. Be selective. \
For each term: use Google Search to find the correct English designation and how it is \
described on authoritative English-language sources (news sites, official organizations, \
academic sources). Use those exact terms and phrasings in your explanation.

3. Include Core Instructions with domain-specific guidance on:
   - Which types of terms require verification and which specific authoritative \
English-language websites to use (provide actual site names and URLs where appropriate, \
e.g., isw.org for conflict, imf.org for economics, official vendor sites for technology). \
Instruct NotebookLM to search these sites to confirm the correct English usage of each term.
   - How to find novel analytical insights not explicit in the sources, \
with 2 concrete examples appropriate to this specific domain
   - Tone and script structure suited to this domain and audience

Write it as one cohesive prompt — do not label it as sections or add structural commentary. \
The reader will paste this directly into NotebookLM.

Here is the Japanese document:

"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_pdf(path: Path) -> str:
    import pdfplumber
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return read_docx(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf(path)
    raise ValueError(f"Unsupported format: {path.suffix}")


def generate_dynamic_sections(japanese_text: str, model: str = NOTEBOOKLM_PROMPT_MODEL) -> str:
    """Web検索を有効にしてドメイン適応プロンプトを生成する。

    プロバイダはモデル名で決まる（gpt-* → OpenAI の web_search、
    それ以外 → Gemini の Google 検索グラウンディング）。
    """
    return llm.generate_text(model, _META_PROMPT + japanese_text,
                             search=True, temperature=0.3, effort="high")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="日本語資料から NotebookLM 用プロンプトを生成する")
    parser.add_argument(
        "--provider", default=None, choices=sorted(PRESETS),
        help="プリセットのプロバイダに切り替える（pipeline/config.py の PRESETS）",
    )
    parser.add_argument(
        "--model-notebooklm", default=None, dest="model_notebooklm", metavar="MODEL",
        help=f"使用モデル（gpt-* なら OpenAI、それ以外は Gemini。既定: {NOTEBOOKLM_PROMPT_MODEL}）",
    )
    args = parser.parse_args()

    try:
        model = resolve_models(args.provider, notebooklm=args.model_notebooklm)["notebooklm"]
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    inputs = sorted(f for f in SENARIO_DIR.iterdir() if f.suffix.lower() in INPUT_EXTS)
    if not inputs:
        print(f"No .docx or .pdf files found in {SENARIO_DIR.relative_to(ROOT)}")
        return

    failed = 0
    for src in inputs:
        out = OUTPUT_DIR / f"{src.stem}_prompt.txt"
        print(f"Processing: {src.name}")
        japanese_text = read_document(src)
        print(f"  {len(japanese_text)} chars extracted")

        print(f"  Generating domain-adapted prompt [{model} / {llm.provider(model)}]...")
        prompt = generate_dynamic_sections(japanese_text, model=model)

        # 空の応答をそのまま書き出すと 0 バイトのプロンプトができてしまう。
        # 既存ファイルも壊さないよう、書かずにスキップする。
        if not prompt:
            print(f"  ERROR: {model} が空の応答を返しました。書き出しをスキップします。", file=sys.stderr)
            failed += 1
            continue

        out.write_text(prompt, encoding="utf-8")
        print(f"  → {out.relative_to(ROOT)} ({len(prompt)} chars)")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
