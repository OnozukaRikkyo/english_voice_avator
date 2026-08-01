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
./tool_llm_check.sh
```

工程ごとにどのモデル・どの提供元を使う設定か、必要なキーが揃っているかが出ます。
`--live` を付けると実際に呼び出して疎通確認します。

---

## 使い方A: 音声 → 台本

```bash
./run_audio.sh path/to/audio.m4a     # 音声を指定して1本処理する
```

何本も続けて処理する場合はこれが一番手軽です。処理後は inbox から
自動で片付けられるので、次のファイルを指定してまた実行するだけです。
同名プロジェクトが既にある場合は上書きせずエラーで止まります。

inbox に置いてから実行する従来の方法も使えます。

```bash
cp your_audio.m4a data/inbox/    # 1. 置く
./run.sh                          # 2. 実行する
```

`convert → transcribe → rewrite → concat_narration → translate` が順に動きます。
入力音声は英語である前提です。

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
./tool_test.sh                         # 自動テストを流す（課金なし）
```

テストはファイル編集のたびに自動実行され（`.claude/settings.json` のフック）、
push すると GitHub Actions でも走ります。どちらも API を呼ばないため課金されません。

---

## スクリプト一覧

接頭辞で役割が分かるようにしています。

| 接頭辞 | 意味 |
|---|---|
| `run` | パイプライン全工程を実行する |
| `step_` | 単一工程だけを実行する（全プロジェクト対象） |
| `tool_` | パイプライン外の確認・調査 |
| `gen_` | 生成物を作る（NotebookLM プロンプト） |

```
run.sh                        inbox の全件を処理する（標準入口）
run_audio.sh <file>           音声1本を指定して処理する
gen_notebooklm_prompt.sh      資料 → NotebookLM プロンプト

step_convert.sh               音声形式の変換
step_transcribe.sh            文字起こし
step_rewrite.sh               ナレーション台本の生成
step_concat_narration.sh      台本パートの結合
step_translate.sh             日本語訳
step_heygen.sh                アバター動画の生成（保留中）
step_concat_video.sh          動画パートの結合（保留中）

tool_llm_check.sh             モデルとAPIキーの確認
tool_heygen_consent.sh        HeyGen アバターの同意リンク取得
tool_heygen_test.sh           HeyGen のテスト動画を1本生成
tool_test_caption.sh          HeyGen 字幕の挙動テスト
tool_investigate_caption.sh   HeyGen 字幕の実証調査
tool_test.sh                  自動テスト（APIを呼ばない）
```

各スクリプトの2行目に役割が書いてあります。

---

## 困ったとき

| 症状 | 対処 |
|---|---|
| `GEMINI_API_KEY が未設定です` / `OPENAI_API_KEY が未設定です` | `.env` に該当キーを追加。`./tool_llm_check.sh` で確認 |
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
