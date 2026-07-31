# ユーザーガイド

このプロジェクトでできることは2つです。目的から選んでください。

| やりたいこと | コマンド | 詳細 |
|---|---|---|
| 音声ファイルから英語ナレーション台本と日本語訳を作る | `./run.sh` | `video_guide.md` |
| 日本語資料から NotebookLM 用プロンプトを作る | `./gen_notebooklm_prompt.sh` | `notebooklm_guide.md` |

使うAIモデルの変更方法は `model_guide.md` にまとめています。

---

## はじめに（初回のみ）

### 1. APIキーを設定する

`.env` に書きます（git 管理外）。**実際に使う側だけ**あれば動きます。

```
GEMINI_API_KEY=...
OPENAI_API_KEY=...
HEYGEN_API_KEY=...        # 動画生成を再開するときのみ
```

### 2. 設定を確認する

```bash
./run_llm_check.sh
```

工程ごとにどのモデル・どの提供元を使う設定か、必要なキーが揃っているかが出ます。
`--live` を付けると実際に呼び出して疎通確認します。

---

## 使い方A: 音声 → 台本

```bash
cp your_audio.m4a data/inbox/    # 1. 置く
./run.sh                          # 2. 実行する
```

`convert → transcribe → rewrite → concat_narration → translate` が順に動きます。
音声の言語は問いません（英語以外は文字起こしの時点で英訳されます）。

`heygen` / `concat_video` は保留中で実行されません（詳細は `video_guide.md`）。

できあがるもの:

```
data/{プロジェクト名}/
  narration/*_full.txt     ← 英語ナレーション台本（SSML）
  translation/*_ja.txt     ← その日本語訳
```

プロジェクト名は音声ファイル名から自動で付きます。

---

## 使い方B: 資料 → NotebookLM プロンプト

```bash
cp your_doc.docx data/senario_jp/   # 1. 置く（.docx / .pdf）
./gen_notebooklm_prompt.sh          # 2. 実行する
```

`data/senario_jp/prompts/*_prompt.txt` ができるので、
中身をそのまま NotebookLM に貼り付けてください。

---

## よくある操作

```bash
./run.sh --steps transcribe            # 特定の工程だけ動かす
./run.sh --force                       # 既存の出力を無視して作り直す
./run.sh --provider openai             # 全工程を ChatGPT に切り替える
./run.sh --project スラッグ名          # 特定プロジェクトだけ処理する
python tools/clean_data.py             # 生成物を全部消してやり直す
```

工程ごとの個別実行用に `run_convert.sh` `run_transcribe.sh` `run_rewrite.sh`
`run_concat_narration.sh` `run_translate.sh` も用意しています。

---

## 困ったとき

| 症状 | 対処 |
|---|---|
| `GEMINI_API_KEY が未設定です` / `OPENAI_API_KEY が未設定です` | `.env` に該当キーを追加。`./run_llm_check.sh` で確認 |
| 途中まで生成済みで先に進まない | 各工程は出力があるとスキップします。作り直すなら `--force` |
| 出力が古い内容のまま | 同上。`--force` を付けるか `tools/clean_data.py` で消す |
| モデルを変えたい | `./run.sh --provider openai`、または `pipeline/config.py` を編集（`model_guide.md`） |
| 動画が作られない | `heygen` / `concat_video` は保留中です（`video_guide.md`） |
| 生成物が消えた | `data/` は git 管理外です。元音声から作り直せます |

---

## 中身を知りたい人向け

- `CLAUDE.md` — パイプラインの仕様（`pipeline/config.py` から自動生成）
- `pipeline/config.py` — ステージ定義・モデル定数。**設定の単一の情報源**
- `pipeline/llm.py` — Gemini / OpenAI の呼び分け
- `docs/` は `tools/gen_docs.py` から自動生成されます。直接編集しないでください
