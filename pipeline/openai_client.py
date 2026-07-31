"""OpenAI API 共通クライアント・エラーハンドリング。

utimes/openai_client.py と同じ構成。pipeline/llm.py から使う。

使い方:
    from .openai_client import get_openai_client, check_api_error
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # config.py を経由せず単体で import されても .env が効くようにする

# ── カスタム例外 ──────────────────────────────────────────────────────────────

class OpenAiApiError(Exception):
    """致命的な OpenAI API エラー（401/403/429/500/503）。"""
    pass


# ── エラー分類・例外送出 ──────────────────────────────────────────────────────

_FATAL_CHECKS = [
    (("401", "invalid_api_key", "AuthenticationError"),
     "APIキーが無効です（401）。OPENAI_API_KEY を再確認してください。"),
    (("403", "PermissionDeniedError"),
     "アクセス権限がありません（403）。OpenAIアカウントの権限設定を確認してください。"),
    (("429", "RateLimitError", "insufficient_quota"),
     "APIレート制限または利用上限に達しました（429）。しばらく時間をおいてから再実行してください。"),
    (("500", "503", "InternalServerError", "APIConnectionError"),
     "OpenAIサーバーエラー（500/503）。10分ほど待機してから再実行してください。"),
]


def check_api_error(e: Exception) -> None:
    """致命的な API エラーを検出して OpenAiApiError を送出する。

    該当しない場合は何もしない（呼び出し元で通常処理を続ける）。
    """
    err = str(e)
    for patterns, msg in _FATAL_CHECKS:
        if any(c in err for c in patterns):
            raise OpenAiApiError(f"{msg}\n詳細: {e}")


# ── クライアント遅延初期化 ────────────────────────────────────────────────────

_client = None


def get_openai_client():
    """openai.OpenAI クライアントを遅延初期化して返す。

    Gemini だけを使う構成でも import 時には何も起きないよう、遅延初期化にしている。
    """
    global _client
    if _client is None:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[FATAL] OPENAI_API_KEY が未設定です。.env に追加してください。", file=sys.stderr)
            sys.exit(1)
        _client = OpenAI(api_key=api_key)
    return _client


# ── スキーマ変換 ──────────────────────────────────────────────────────────────

def gemini_schema_to_json_schema(schema: dict) -> dict:
    """Gemini 形式のスキーマ dict を OpenAI Structured Outputs（strict）用に変換する。

    パイプラインのスキーマは Gemini 形式（"type": "ARRAY" のような大文字表記）を
    単一の情報源にしている。strict モードの制約に合わせて object には
    additionalProperties=false を付け、全プロパティを required に含める。
    """
    t = str(schema.get("type", "")).upper()
    if t == "OBJECT":
        props = {k: gemini_schema_to_json_schema(v) for k, v in (schema.get("properties") or {}).items()}
        return {
            "type": "object",
            "properties": props,
            "required": list(props.keys()),
            "additionalProperties": False,
        }
    if t == "ARRAY":
        return {"type": "array", "items": gemini_schema_to_json_schema(schema["items"])}
    if t == "STRING":
        out: dict = {"type": "string"}
        if schema.get("enum"):
            out["enum"] = list(schema["enum"])
        return out
    if t == "INTEGER":
        return {"type": "integer"}
    if t == "NUMBER":
        return {"type": "number"}
    if t == "BOOLEAN":
        return {"type": "boolean"}
    raise ValueError(f"未対応のスキーマ型: {t}")
