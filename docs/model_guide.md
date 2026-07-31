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
| `TRANSCRIBE_ENGLISH_MODEL` | `gemini-3.5-flash-lite` | Gemini |
| `REWRITE_MODEL` | `gemini-3.5-flash` | Gemini |
| `TRANSLATE_MODEL` | `gemini-3.6-flash` | Gemini |

## 変え方は4通り

優先順位は **個別指定 > プリセット > .env > config.py の既定値** です。

### 1. 全工程をまとめて（この実行だけ）

```bash
./run.sh --provider gemini
./run.sh --provider openai
```

中身は `pipeline/config.py` の `PRESETS` です。

### 2. 1工程だけ（この実行だけ）

```bash
./run.sh --model-rewrite gpt-5.6-luna
./run.sh --model-transcribe gemini-2.5-flash
./gen_notebooklm_prompt.sh --model-notebooklm gemini-2.5-flash
```

プリセットと併用でき、個別指定が勝ちます。

```bash
./run.sh --provider openai --model-rewrite gemini-3.5-flash
  → rewrite だけ Gemini、他は OpenAI
```

### 3. 恒久的に変える（コード編集なし・おすすめ）

`.env` に定数名と同じ名前で書くだけです。雛形がコメントで入っています。

```
REWRITE_MODEL=gemini-3.6-flash
TRANSLATE_MODEL=gpt-5.6-luna
```

`./run_llm_check.sh` で反映を確認できます。

### 4. 既定値そのものを変える

`pipeline/config.py` の該当行を書き換えます。

```python
TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gpt-transcribe")     # OpenAI
TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gemini-3.6-flash")   # Gemini
```

## 確認する

```bash
./run_llm_check.sh                    # 工程ごとのモデルとプロバイダ、キーの有無
./run_llm_check.sh --provider openai  # プリセット適用後の姿を予習（変更はしない）
./run_llm_check.sh --live             # 実際に呼び出して疎通確認
./run_llm_check.sh --models           # 利用可能なモデル一覧
```

## 文字起こしの注意

`transcript/` は**常に英語**という約束ですが、実現方法が経路で違います。

- **Gemini 経路** — マルチモーダルなので「英語で出せ」と直接指示でき、1回で終わります。
- **OpenAI 経路** — `gpt-transcribe` は専用の音声認識モデルで、
  **必ず話された言語のまま逐語で書き起こします**。
  `prompt` でも `language=en` でも英語化できないことを実 API で確認済みです。
  そのため書き起こしの後に `gemini-3.5-flash-lite` で英語化を1回挟みます
  （`TRANSCRIBE_ENGLISH_MODEL`）。英語音声なら実質そのまま返ります。

OpenAI のアップロード上限は25MBです。超える音声は `pipeline/llm.py` が
ffmpeg で時間分割して個別に送り、結果を連結します。

## モデル選定の考え方

**作業の難易度で選びます。** 安いモデルで足りる工程だけ安くします。

| 工程 | 難易度 | 理由 |
|---|---|---|
| rewrite | 最難 | 軍事用語の正確さ・行間の戦略的洞察・独自視点・SSML・意味単位での分割を同時に要求 |
| transcribe | 高 | 固有名詞の聞き取り。誤ると後段すべてが誤った前提で動き、取り返しがつかない |
| notebooklm | 中〜高 | 検索の使い分けと、一般読者が分からない語だけを選ぶ取捨選択 |
| translate | 中 | 翻訳自体は機械的だが、NHK準拠の固有名詞表記と論調の維持が要る |
| transcribe_english | 低 | 原語→英語の逐語変換のみ。判断も創作もない |

`transcribe_english` だけ意図的に lite モデルを使っています。
21,578字の実データで保持率100.0%（欠落なし）を確認済みです。

translate を lite に落とすのは推奨しません。実測で `gemini-2.5-flash-lite` は
改行構造が123行→8行に崩れ、固有名詞も落ちました。

## APIキー

`.env`（git 管理外）に置きます。クライアントは遅延初期化なので、
**実際に使う側のキーだけ**あれば動きます。

```
GEMINI_API_KEY=...
OPENAI_API_KEY=...
```

## Web検索を使う工程

`tools/gen_notebooklm_prompt.py` は用語の正式な英語表記を実際に調べさせるため、
Web検索ツールを有効にして呼びます（`NOTEBOOKLM_PROMPT_MODEL` = `gpt-5.6-luna` / OpenAI）。
これも同じ規約で切り替わります。

- **OpenAI** — Responses API の `web_search` ツール
- **Gemini** — Google 検索グラウンディング

```bash
./gen_notebooklm_prompt.sh                              # 既定モデル
./gen_notebooklm_prompt.sh --model gemini-2.5-flash     # この実行だけ変更
```
