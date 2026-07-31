"""プロバイダの呼び分け。

**モデル名がプロバイダを決める。** `gpt-` で始まれば OpenAI、それ以外は Gemini。
utimes/code/llm.py と同じ規約なので、両プロジェクトで判断が揃う。

つまり config.py のモデル名を1行書き換えるだけでプロバイダが切り替わる:

    TRANSCRIBE_MODEL = "gpt-transcribe"      # OpenAI
    TRANSCRIBE_MODEL = "gemini-3.6-flash"    # Gemini

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
from .config import OPENAI_AUDIO_MAX_BYTES

# ── 文字起こし用プロンプト ────────────────────────────────────────────────────

# 入力音声は英語である前提。書き起こしはそのまま逐語で行い、変換は挟まない。
# 初版 3cc7377 から b217aec まで使われていたプロンプトをそのまま復元したもの。
# （OpenAI の gpt-transcribe は元から逐語なので、Gemini 経路だけ指示が要る）
_PROMPT_TRANSCRIBE = "This audio is in English. Please transcribe it in English. Output the text only."


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

def transcribe(model: str, mp3: Path) -> str:
    """英語音声を逐語で書き起こして返す。

    入力は英語である前提なので、変換は一切挟まない（1音声につきAPI呼び出しは1回）。
    OpenAI の gpt-transcribe は元から話された言語のまま逐語で返すため、
    そのまま使える。
    """
    if is_openai(model):
        return _transcribe_openai(model, mp3)
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
        resp = client.models.generate_content(model=model, contents=[uploaded, _PROMPT_TRANSCRIBE])
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
    # ffmpeg が何も吐かなかった場合、以降は静かに空文字列を返してしまう
    if not chunks:
        raise RuntimeError(f"{mp3.name}: 音声の分割に失敗しました（チャンクが0件）")
    # segment_time はキーフレーム境界に依存するため、指定どおりのサイズにならない。
    # 上限を超えたまま送ると API 側で落ちるので、送る前に検出する。
    over = [c for c in chunks if c.stat().st_size > OPENAI_AUDIO_MAX_BYTES]
    if over:
        _cleanup_chunks(mp3, chunks)
        raise RuntimeError(
            f"{mp3.name}: 分割後も上限（{OPENAI_AUDIO_MAX_BYTES // 1024 // 1024}MB）を超える"
            f"チャンクがあります: {[f'{c.name} {c.stat().st_size / 1024 / 1024:.1f}MB' for c in over]}"
        )
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
