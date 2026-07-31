"""Gemini API 共通クライアント・エラーハンドリング。

utimes/gemini_client.py と同じ構成。pipeline/llm.py から使う。

使い方:
    from .gemini_client import get_genai_client, check_api_error
"""
import os
import sys

# ── カスタム例外 ──────────────────────────────────────────────────────────────

class GeminiApiError(Exception):
    """致命的な Gemini API エラー（400/401/403/429/500/503）。"""
    pass


# ── エラー分類・例外送出 ──────────────────────────────────────────────────────

_FATAL_CHECKS = [
    (("401", "UNAUTHENTICATED"),
     "APIキーが無効です（401）。GEMINI_API_KEY を再確認してください。"),
    (("403", "PERMISSION_DENIED"),
     "アクセス権限がありません（403）。Google Cloudの支払い・権限設定を確認してください。"),
    (("400", "INVALID_ARGUMENT"),
     "リクエストが不正です（400）。モデル名と入力内容を見直してください。"),
    (("429", "RESOURCE_EXHAUSTED"),
     "APIレート制限に達しました（429）。しばらく時間をおいてから再実行してください。"),
    (("500", "503", "INTERNAL", "UNAVAILABLE"),
     "Googleサーバーエラー（500/503）。10分ほど待機してから再実行してください。"),
]


def check_api_error(e: Exception) -> None:
    """致命的な API エラーを検出して GeminiApiError を送出する。

    該当しない場合は何もしない（呼び出し元で通常処理を続ける）。
    """
    err = str(e)
    if "quota" in err.lower():
        raise GeminiApiError(f"APIレート制限に達しました（quota）。しばらく時間をおいてから再実行してください。\n詳細: {e}")
    for patterns, msg in _FATAL_CHECKS:
        if any(c in err for c in patterns):
            raise GeminiApiError(f"{msg}\n詳細: {e}")


# ── クライアント遅延初期化 ────────────────────────────────────────────────────

_client = None


def get_genai_client():
    """google.genai.Client を遅延初期化して返す。

    OpenAI だけを使う構成でも import 時には何も起きないよう、遅延初期化にしている。
    """
    global _client
    if _client is None:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("[FATAL] GEMINI_API_KEY が未設定です。.env に追加してください。", file=sys.stderr)
            sys.exit(1)
        _client = genai.Client(api_key=api_key)
    return _client
