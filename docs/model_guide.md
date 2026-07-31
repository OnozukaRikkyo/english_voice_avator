# モデル・プロバイダの切り替え

## 規約

**モデル名がプロバイダを決めます。**
`gpt-` で始まれば OpenAI、それ以外は Gemini。
呼び分けは `pipeline/llm.py` が行い、各工程のコードは
プロバイダのSDKを直接触りません。utimes プロジェクトと同じ規約です。

## 現在の設定

| 定数 | モデル | プロバイダ |
|------|--------|-----------|
| `TRANSCRIBE_MODEL` | `gpt-transcribe` | OpenAI |
| `TRANSCRIBE_ENGLISH_MODEL` | `gemini-2.5-flash` | Gemini |
| `REWRITE_MODEL` | `gemini-3.5-flash` | Gemini |
| `TRANSLATE_MODEL` | `gemini-2.5-flash` | Gemini |

## 恒久的に変える

`pipeline/config.py` の該当行を書き換えるだけです。

```python
TRANSCRIBE_MODEL = "gpt-transcribe"     # OpenAI
TRANSCRIBE_MODEL = "gemini-2.5-flash"   # Gemini
```

## 一時的に変える（この実行だけ）

```bash
./run.sh --model-rewrite gpt-5.6-luna
./run.sh --model-transcribe gemini-2.5-flash
```

## 確認する

```bash
./run_llm_check.sh            # 工程ごとのモデルとプロバイダ、キーの有無
./run_llm_check.sh --live     # 実際に呼び出して疎通確認
./run_llm_check.sh --models   # 利用可能なモデル一覧
```

## 文字起こしの注意

`transcript/` は**常に英語**という約束ですが、実現方法が経路で違います。

- **Gemini 経路** — マルチモーダルなので「英語で出せ」と直接指示でき、1回で終わります。
- **OpenAI 経路** — `gpt-transcribe` は専用の音声認識モデルで、
  **必ず話された言語のまま逐語で書き起こします**。
  `prompt` でも `language=en` でも英語化できないことを実 API で確認済みです。
  そのため書き起こしの後に `gemini-2.5-flash` で英語化を1回挟みます
  （`TRANSCRIBE_ENGLISH_MODEL`）。英語音声なら実質そのまま返ります。

OpenAI のアップロード上限は25MBです。超える音声は `pipeline/llm.py` が
ffmpeg で時間分割して個別に送り、結果を連結します。

## APIキー

`.env`（git 管理外）に置きます。クライアントは遅延初期化なので、
**実際に使う側のキーだけ**あれば動きます。

```
GEMINI_API_KEY=...
OPENAI_API_KEY=...
```

なお `tools/gen_notebooklm_prompt.py` だけは Google 検索グラウンディングを使うため
`NOTEBOOKLM_PROMPT_MODEL`（`gemini-2.5-flash`）で Gemini 固定です。
