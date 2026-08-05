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
| `REWRITE_MODEL` | `gpt-5.6-luna` | OpenAI |
| `REVIEW_MODEL` | `gpt-5.6-luna` | OpenAI |
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
./run.sh --model-transcribe gemini-3.6-flash
./gen_notebooklm_prompt.sh --model-notebooklm gemini-3.6-flash
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

`./tool_llm_check.sh` で反映を確認できます。

### 4. 既定値そのものを変える

`pipeline/config.py` の該当行を書き換えます。

```python
TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gpt-transcribe")     # OpenAI
TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gemini-3.6-flash")   # Gemini
```

## 確認する

```bash
./tool_llm_check.sh                    # 工程ごとのモデルとプロバイダ、キーの有無
./tool_llm_check.sh --provider openai  # プリセット適用後の姿を予習（変更はしない）
./tool_llm_check.sh --live             # 実際に呼び出して疎通確認
./tool_llm_check.sh --models           # 利用可能なモデル一覧
```

## 文字起こしについて

入力音声は英語である前提です。書き起こしは逐語で行い、言語変換は挟みません
（1音声につきAPI呼び出しは1回）。

OpenAI のアップロード上限は25MBです。超える音声は `pipeline/llm.py` が
ffmpeg で時間分割して個別に送り、結果を連結します。

## モデル選定の考え方

**作業の難易度で選びます。** 安いモデルで足りる工程だけ安くします。

| 工程 | 難易度 | 理由 |
|---|---|---|
| rewrite | 最難 | 用語の正確さ・行間の分析・冗長の削り込み・SSML・意味単位での分割を同時に要求 |
| review | 最難 | 裏付けのない断定・煽り・片側だけの視点を見つける。安いモデルは問題を見つけられない |
| transcribe | 高 | 固有名詞の聞き取り。誤ると後段すべてが誤った前提で動き、取り返しがつかない |
| notebooklm | 中〜高 | 検索の使い分けと、一般読者が分からない語だけを選ぶ取捨選択 |
| translate | 中 | 翻訳自体は機械的だが、NHK準拠の固有名詞表記と論調の維持が要る |

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
./gen_notebooklm_prompt.sh --model-notebooklm gemini-3.6-flash  # この実行だけ変更
```
