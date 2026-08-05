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
HEYGEN_API_KEY=...        # 動画生成に必要
HEYGEN_AVATAR_ID=...      # 使うアバター
HEYGEN_VOICE_ID=...       # 使う音声
```

### 2. 設定を確認する

```bash
./tool_llm_check.sh
```

工程ごとにどのモデル・どの提供元を使う設定か、必要なキーが揃っているかが出ます。
`--live` を付けると実際に呼び出して疎通確認します。

---

## 使い方A: 音声 → 台本・動画

```bash
cp your_audio.m4a data/inbox/    # 1. 置く
./run.sh                          # 2. 実行する
```

**`./run.sh` は引数なしで最初から最後まで通します。**
`convert → transcribe → rewrite → review → concat_narration → factcheck → translate → heygen → concat_video` が順に動きます。
プロジェクト名は音声ファイル名から自動で付きます。
入力音声は英語である前提です。


音声を1本だけ指定して処理することもできます。

```bash
./run.sh path/to/audio.m4a
```

処理後は inbox から自動で片付けられるので、次のファイルを指定してまた
実行するだけです。同名プロジェクトが既にある場合は上書きせず止まります。

できあがるもの:

```
data/{プロジェクト名}/
  narration/*_full.txt     ← 英語ナレーション台本（SSML）
  translation/*_ja.txt     ← その日本語訳
  video/*.mp4              ← 結合済みのアバター動画
  draft/parts/*_review.md  ← 台本のどこを報道基準で直したかの記録
  narration/*_factcheck.md ← 配信前に一次ソースと照合すべき項目の表
```

### 台本の点検（review 工程）

`rewrite` が書いた台本は、そのままでは報道として危うい箇所を含みます。
文字起こしに無い数字が足される、"reportedly" が落ちて推測が断定になる、
片方の当事者の主張が地の文になる — 読み返しの効かない音声では、いずれも
そのまま事実として受け取られます。

`review` は台本を **元の文字起こしと突き合わせて** 点検し、最小限の修正を
入れた版を `narration/parts/` に書きます。以降の工程はこちらを使います。

何を直したかは `draft/parts/{stem}_part01_review.md` に残るので、
録音前にここだけ読めば済みます。指摘が high（裏付け無し・断定化・
一方的な引用）で出ていたら、元の音声まで戻って確認してください。
指摘が1件も無ければ台本には触らず、そのまま複製します。

### 配信前の照合リスト（factcheck 工程）

review は台本を**文字起こしと**突き合わせますが、素材そのものが
誤っていれば通してしまいます。factcheck は完成した台本から、
**現実と**照合すべき項目（人物と役職の対応・数値・日付・固有名詞）を
リスク順の表 `narration/*_factcheck.md` に書き出します。
検証自体は行いません — 配信前に high の行だけでも一次ソースと
照合してください。実在の人物・事件を扱う以上、誤り1つで番組全体の
信頼が崩れます。

各工程は出力があるとスキップします。途中で止まっても `./run.sh` を
もう一度実行すれば続きから進みます。作り直すときは `--force` が要ります。

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
./run.sh --provider openai             # 全工程を OpenAI に切り替える
./run.sh --project スラッグ名          # 特定プロジェクトだけ処理する
./run.sh --again                       # 既存を上書きして作り直す（引数不要）
./run.sh --no-video                    # 動画を作らず台本と日本語訳まで
./run_no_video.sh                      # 同上（近道）
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
| `run` | パイプラインを実行する |
| `step_` | 単一工程だけを実行する（全プロジェクト対象） |
| `tool_` | パイプライン外の確認・調査 |
| `gen_` | 生成物を作る（NotebookLM プロンプト） |

```
run.sh                        パイプラインの唯一の入口
  ./run.sh                      inbox の全件を処理する
  ./run.sh <file>               音声1本を指定して処理する
  ./run.sh --again              既存プロジェクトを上書きして作り直す
  ./run.sh --no-video           動画を作らず台本と日本語訳まで
run_no_video.sh               ./run.sh --no-video の近道
gen_notebooklm_prompt.sh      資料 → NotebookLM プロンプト

step_convert.sh               音声形式の変換
step_transcribe.sh            文字起こし
step_rewrite.sh               ナレーション台本の生成
step_review.sh                台本を報道基準で点検して修正
step_factcheck.sh             配信前に照合すべき項目の表を生成
step_concat_narration.sh      台本パートの結合
step_translate.sh             日本語訳
step_heygen.sh                アバター動画の生成
step_concat_video.sh          動画パートの結合

tool_llm_check.sh             モデルとAPIキーの確認
tool_heygen_consent.sh        HeyGen アバターの同意リンク取得
tool_heygen_test.sh           設定中のアバターと音声を短い文で1本確認
tool_test_caption.sh          HeyGen 字幕の挙動テスト（調査済み・記録用）
tool_investigate_caption.sh   HeyGen 字幕の実証調査（調査済み・記録用）
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
| 動画が作られない | `./run.sh --steps heygen,concat_video` で動画だけ作り直せます |
| 生成物が消えた | `data/` は git 管理外です。元音声から作り直せます |

---

## 中身を知りたい人向け

- `CLAUDE.md` — パイプラインの仕様（`pipeline/config.py` から自動生成）
- `pipeline/config.py` — ステージ定義・モデル定数。**設定の単一の情報源**
- `pipeline/llm.py` — Gemini / OpenAI の呼び分け
- `docs/` は `tools/gen_docs.py` から自動生成されます。直接編集しないでください
