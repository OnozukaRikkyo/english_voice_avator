"""プロバイダの呼び分け。

**モデル名がプロバイダを決める。** `gpt-` で始まれば OpenAI、それ以外は Gemini。
utimes/code/llm.py と同じ規約なので、両プロジェクトで判断が揃う。

つまり config.py のモデル名を1行書き換えるだけでプロバイダが切り替わる:

    TRANSCRIBE_MODEL = "gpt-transcribe"      # OpenAI
    TRANSCRIBE_MODEL = "gemini-2.5-flash"    # Gemini

提供する関数は3つで、どちらのプロバイダでも同じ戻り値の型になる:

    transcribe(model, mp3_path)          → str   音声 → 英語テキスト
    generate_json(model, prompt, schema) → str   スキーマ制約付きJSON文字列
    generate_text(model, prompt)         → str   プレーンテキスト

スキーマは Gemini 形式の dict を単一の情報源にしている。Gemini はそのまま
制約付きデコーディングに使い、OpenAI 経路だけ strict な JSON スキーマに変換する。
"""
import math
import subprocess
import tempfile
from pathlib import Path

from . import gemini_client, openai_client
from .config import OPENAI_AUDIO_MAX_BYTES, TRANSCRIBE_ENGLISH_MODEL

# ── 文字起こし用プロンプト ────────────────────────────────────────────────────

# Gemini 経路: マルチモーダルなので直接「英語で出せ」と指示できる。
_PROMPT_TRANSCRIBE_EN = (
    "Transcribe this audio. The output MUST be in English, and in English only.\n"
    "- If the audio is spoken in English, transcribe it verbatim.\n"
    "- If the audio is spoken in any other language, translate it into English "
    "as you transcribe. Do NOT output the original language.\n"
    "Cover the entire audio from start to finish — do not summarize or omit anything.\n"
    "Output the English text only: no preamble, no language labels, no commentary."
)

# OpenAI 経路: gpt-transcribe が原語で返した本文を英語化する後段プロンプト。
_PROMPT_TO_ENGLISH = (
    "Below is a raw speech-to-text transcript. Return it in English.\n"
    "- If it is already English, return it unchanged apart from obvious "
    "speech-recognition typos.\n"
    "- If it is in any other language, translate the whole thing into English.\n"
    "Keep every sentence — do not summarize, condense, or omit anything. "
    "Preserve proper nouns using their standard English spellings.\n"
    "Output the English text only: no preamble, no notes.\n\n"
)


def is_openai(model: str) -> bool:
    """モデル名から OpenAI 経路かどうかを判定する。"""
    return model.startswith("gpt-")


def provider(model: str) -> str:
    """表示用のプロバイダ名。"""
    return "OpenAI" if is_openai(model) else "Gemini"


def check_api_error(e: Exception) -> None:
    """致命的なAPIエラーを、どちらの経路で起きたかに関わらず分類する。

    各 check_api_error は自分の提供元のパターンにだけ反応するため、
    両方を通しても誤検知しない。
    """
    gemini_client.check_api_error(e)
    openai_client.check_api_error(e)


# ── テキスト生成 ──────────────────────────────────────────────────────────────

def generate_text(model: str, prompt: str, *, search: bool = False, temperature: float | None = None) -> str:
    """プレーンテキストを生成して返す。

    Args:
        search: Web検索ツールを有効にする。OpenAI は Responses API の `web_search`、
                Gemini は Google 検索グラウンディングを使う。用語の正式な英語表記を
                実際に調べさせたい場合に使う。
        temperature: Gemini 経路のみ有効。OpenAI の推論モデルは非対応なので無視する。
    """
    try:
        if is_openai(model):
            kwargs = {"tools": [{"type": "web_search"}]} if search else {}
            resp = openai_client.get_openai_client().responses.create(
                model=model, input=prompt, **kwargs
            )
            return (resp.output_text or "").strip()

        from google.genai import types
        cfg: dict = {}
        if search:
            cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        if temperature is not None:
            cfg["temperature"] = temperature
        resp = gemini_client.get_genai_client().models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(**cfg) if cfg else None,
        )
        return (resp.text or "").strip()
    except Exception as e:
        check_api_error(e)
        raise


# ── 構造化JSON生成 ────────────────────────────────────────────────────────────

def generate_json(model: str, prompt: str, schema: dict, schema_name: str = "result") -> str:
    """スキーマで文法を強制したJSON文字列を返す。

    schema は Gemini 形式の dict（"type": "ARRAY" のような大文字表記）。
    OpenAI 経路では strict な JSON スキーマに変換して Structured Outputs に渡す。
    OpenAI の strict モードはトップレベルに object を要求するため、配列スキーマは
    {"items": [...]} で包んでから中身を取り出す。
    """
    try:
        if is_openai(model):
            json_schema = openai_client.gemini_schema_to_json_schema(schema)
            wrapped = json_schema.get("type") == "array"
            if wrapped:
                json_schema = {
                    "type": "object",
                    "properties": {"items": json_schema},
                    "required": ["items"],
                    "additionalProperties": False,
                }
            resp = openai_client.get_openai_client().responses.create(
                model=model,
                input=prompt,
                text={"format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                }},
            )
            out = (resp.output_text or "").strip()
            if wrapped:
                import json
                return json.dumps(json.loads(out)["items"], ensure_ascii=False)
            return out

        from google.genai import types
        resp = gemini_client.get_genai_client().models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return (resp.text or "").strip()
    except Exception as e:
        check_api_error(e)
        raise


# ── 文字起こし ────────────────────────────────────────────────────────────────

def transcribe(model: str, mp3: Path, *, english_model: str | None = None) -> str:
    """音声を英語テキストにして返す。出力は必ず英語。

    Gemini はマルチモーダルのプロンプトで直接「英語で出せ」を指示できるが、
    OpenAI の gpt-transcribe は専用の音声認識モデルで、必ず話された言語のまま
    逐語で書き起こす（prompt でも language でも英語化できないことを実測で確認済み）。
    そのため OpenAI 経路では書き起こしのあとに英語化のテキスト変換を1回挟む。

    Args:
        english_model: 英語化に使うモデル。OpenAI 経路でのみ使う。
                       None なら config.TRANSCRIBE_ENGLISH_MODEL。
    """
    if is_openai(model):
        raw = _transcribe_openai(model, mp3)
        return _ensure_english(raw, english_model or TRANSCRIBE_ENGLISH_MODEL)
    return _transcribe_gemini(model, mp3)


def _transcribe_gemini(model: str, mp3: Path) -> str:
    """Gemini Files API にアップロードして英語で書き起こす。"""
    import io
    import time

    client = gemini_client.get_genai_client()
    try:
        buf = io.BytesIO(mp3.read_bytes())
        buf.name = "upload.mp3"
        uploaded = client.files.upload(file=buf, config={"mime_type": "audio/mp3"})
        while uploaded.state.name == "PROCESSING":
            time.sleep(5)
            uploaded = client.files.get(name=uploaded.name)
        resp = client.models.generate_content(model=model, contents=[uploaded, _PROMPT_TRANSCRIBE_EN])
        client.files.delete(name=uploaded.name)
    except Exception as e:
        check_api_error(e)
        raise
    return (resp.text or "").strip()


def _transcribe_openai(model: str, mp3: Path) -> str:
    """OpenAI /v1/audio/transcriptions で書き起こす（話された言語のまま）。

    アップロード上限は25MB。超える場合は時間で等分割して個別に投げ、連結する。
    """
    chunks = _split_for_upload(mp3)
    if len(chunks) > 1:
        print(f"    {mp3.stat().st_size / 1024 / 1024:.1f} MB > 上限 → {len(chunks)} 分割して送信")

    client = openai_client.get_openai_client()
    texts: list[str] = []
    try:
        for i, chunk in enumerate(chunks, 1):
            if len(chunks) > 1:
                print(f"    chunk {i}/{len(chunks)} ({chunk.stat().st_size / 1024 / 1024:.1f} MB)")
            with open(chunk, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=model, file=f, response_format="text",
                )
            texts.append(str(resp).strip())
    except Exception as e:
        check_api_error(e)
        raise
    finally:
        _cleanup_chunks(mp3, chunks)

    return "\n".join(texts)


def _split_for_upload(mp3: Path) -> list[Path]:
    """25MB を超える音声を、上限に収まる個数へ時間で等分割する。

    分割が不要なら元ファイルをそのまま1件返す。
    """
    size = mp3.stat().st_size
    if size <= OPENAI_AUDIO_MAX_BYTES:
        return [mp3]

    duration = _duration_seconds(mp3)
    n = math.ceil(size / (OPENAI_AUDIO_MAX_BYTES * 0.9))  # 1割の余裕を見る
    seg = math.ceil(duration / n)

    tmpdir = Path(tempfile.mkdtemp(prefix="transcribe_", dir=mp3.parent))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-f", "segment", "-segment_time", str(seg),
         "-c", "copy", str(tmpdir / "chunk%03d.mp3")],
        check=True, capture_output=True,
    )
    return sorted(tmpdir.glob("chunk*.mp3"))


def _cleanup_chunks(mp3: Path, chunks: list[Path]) -> None:
    """_split_for_upload が作った一時ディレクトリを消す（未分割なら何もしない）。"""
    if chunks and chunks[0] != mp3:
        import shutil
        shutil.rmtree(chunks[0].parent, ignore_errors=True)


def _duration_seconds(mp3: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)],
        capture_output=True, check=True,
    )
    return float(out.stdout.decode().strip())


def _ensure_english(text: str, model: str) -> str:
    """英語でなければ英訳する。すでに英語ならほぼそのまま返る。"""
    print(f"    英語化: {model} ({provider(model)})")
    return generate_text(model, _PROMPT_TO_ENGLISH + text)
