#!/usr/bin/env python3
"""Generate NotebookLM prompts from Japanese scenario documents (docx / pdf).

Scans data/senario_jp/ for .docx and .pdf files.
For each file, uses Gemini to:
  1. Detect the document's domain (war, politics, economics, technology, etc.)
  2. Generate a domain-appropriate Role & Objective
  3. Extract difficult terminology into a Document-Specific Vocabulary Guide
  4. Generate domain-appropriate Core Instructions

Only the Expected Output Format is fixed across all documents.

Usage:
  python tools/gen_notebooklm_prompt.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from google import genai
from google.genai import types

from pipeline.config import GEMINI_API_KEY, GEMINI_TRANSLATE_MODEL

SENARIO_DIR = ROOT / "data" / "senario_jp"
OUTPUT_DIR  = SENARIO_DIR / "prompts"
INPUT_EXTS  = {".docx", ".pdf"}

# ── Gemini meta-prompt ────────────────────────────────────────────────────────

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


def generate_dynamic_sections(client: genai.Client, japanese_text: str) -> str:
    response = client.models.generate_content(
        model=GEMINI_TRANSLATE_MODEL,
        contents=[_META_PROMPT + japanese_text],
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
        ),
    )
    return (response.text or "").strip()


def build_prompt(dynamic_sections: str) -> str:
    return dynamic_sections


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=GEMINI_API_KEY)

    inputs = sorted(f for f in SENARIO_DIR.iterdir() if f.suffix.lower() in INPUT_EXTS)
    if not inputs:
        print(f"No .docx or .pdf files found in {SENARIO_DIR.relative_to(ROOT)}")
        return

    for src in inputs:
        out = OUTPUT_DIR / f"{src.stem}_prompt.txt"
        print(f"Processing: {src.name}")
        japanese_text = read_document(src)
        print(f"  {len(japanese_text)} chars extracted")

        print("  Generating domain-adapted prompt (Gemini)...")
        dynamic_sections = generate_dynamic_sections(client, japanese_text)

        prompt = build_prompt(dynamic_sections)
        out.write_text(prompt, encoding="utf-8")
        print(f"  → {out.relative_to(ROOT)} ({len(prompt)} chars)")


if __name__ == "__main__":
    main()
