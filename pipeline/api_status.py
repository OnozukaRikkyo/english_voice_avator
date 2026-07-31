"""API例外から HTTP ステータスコードを取り出す。

エラーの分類を `str(e)` の部分文字列で行うと、メッセージ中の ID やパスに
たまたま "401" や "429" が現れただけで誤検知する。SDK の例外は
ステータスコードを属性で持っているので、まずそちらを見る。
"""


def status_code(e: Exception) -> int | None:
    """例外から HTTP ステータスコードを返す。取れなければ None。

    OpenAI SDK は `status_code`、google-genai は `code` を持つ。
    どちらも無ければ `response.status_code` を見る。
    """
    for attr in ("status_code", "code", "http_status"):
        v = getattr(e, attr, None)
        if isinstance(v, bool):          # bool は int のサブクラスなので先に弾く
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)

    resp = getattr(e, "response", None)
    v = getattr(resp, "status_code", None)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    return None
