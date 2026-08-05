# 音声から台本・動画を作る手順

毎回この3手順を繰り返します。

| | やること | コマンド |
|---|---|---|
| 1 | 日本語資料から NotebookLM 用プロンプトを作る | `./gen_notebooklm_prompt.sh` |
| 2 | NotebookLM で英語音声を作り、`data/inbox/` に置く | （手作業） |
| 3 | 台本・翻訳・動画をまとめて作る | `./run.sh` |

手順1のプロンプトからは、文字起こしに渡す用語ヒントも同時に作られます。
詳しくは `notebooklm_guide.md` を参照してください。

---

## 1. 音声ファイルを inbox に置く

```
data/inbox/
  your_audio.m4a   ← ここに置く
```

対応フォーマット: `.m4a` / `.mp4` / `.mp3`

入力音声は英語である前提です（逐語で書き起こします）。

変換は音声認識向けの設定（64kbps モノラル）で行います。約52分まで
分割せずに1回で送れます。超える場合は無音の位置で分割します。

`data/senario_jp/prompts/` に NotebookLM プロンプトがあると、その用語集を
固有名詞のヒントとして文字起こしに渡します（綴りが安定します）。
自前の用語を足したい場合は `data/senario_jp/vocabulary.txt` に1行1語で置きます。

---

## 2. パイプラインを実行する

```bash
./run.sh
```

**引数は不要です。** `data/inbox/` を読み、ファイル名からプロジェクトを
自動で作り、下の全工程を最初から最後まで通します。

`convert → transcribe → rewrite → review → concat_narration → factcheck → translate → heygen → concat_video`

所要時間の目安（49分の音声・8分割での実測）:

| 工程 | 目安 |
|---|---|
| `convert` | 20秒 |
| `transcribe` | 1分 |
| `rewrite` | 15分前後（分割した塊ごとにAPIを呼ぶ・作り直し込み） |
| `review` | 20分前後（台本パートごとにAPIを呼ぶ） |
| `concat_narration` | 即時 |
| `factcheck` | 数分（台本全体を1回で読む） |
| `translate` | 1〜2分 |
| `heygen` | **最も長い**。動画1本あたり数分 × パート数 |
| `concat_video` | 数十秒 |

動画を除くと約30分、いずれも音声の長さにおおむね比例します。

できあがるもの:

```
data/{プロジェクト名}/
  narration/*_full.txt     ← 英語ナレーション台本（SSML）
  translation/*_ja.txt     ← その日本語訳
  video/*.mp4              ← 結合済みのアバター動画
  draft/parts/*_review.md  ← 台本のどこを報道基準で直したかの記録
  narration/*_factcheck.md ← 配信前に一次ソースと照合すべき項目の表
```

録音・公開の前に `*_review.md` の high 指摘と `*_factcheck.md` の
high 行に目を通してください（説明は `user_guide.md`）。

---

## 途中から再開する / 作り直す

各工程は**出力が既にあればスキップ**します。途中で止まっても、
`./run.sh` をもう一度実行すれば済んだ工程を飛ばして続きから進みます。

逆に、同じ音声で作り直したいときはスキップされてしまうので `--force` が要ります。

```bash
./run.sh --force                      # 全工程を作り直す
./run.sh --again                      # 同上（引数不要・直近のプロジェクトが対象）
./run.sh --steps rewrite,translate    # 特定の工程だけやり直す
```

**`--force` は動画も作り直します。** HeyGen の生成分は課金対象なので、
台本だけ直したいときは `--steps` で工程を絞ってください。

---

## 台本の分割

HeyGen の入力上限は5,000字です。台本パートはこれを超えることがあるため
（実測 6,416〜9,483字）、送る前に `<break>` の位置で自動的に割ります。
1.5秒（章の転換）を優先し、足りなければ1.0秒・0.5秒へ降ります。
文の途中では切りません。

分けたときの動画は `_part01_01.mp4` のように枝番が付きます。
1本に収まったパートは枝番なしのままです。

---

## 冒頭の挨拶

台本の先頭には、毎回まったく同じ挨拶が自動で入ります。

```
Hello everyone, and welcome. <break time="0.5s"/> I'm Bogdan Parkhomenko, and this is the beginning of a new journey. <break time="1.5s"/>
```

AIには書かせていません。文言が回ごとにぶれないよう、`part01` の
`<speak>` の中へ機械的に差し込んでいます。AIには「挨拶と名乗りは書くな、
本題から始めろ」と指示しているので、二重になりません。

文言を変えるときは `.env` に1行書きます（コードの編集は不要）。

```
NARRATION_OPENING=Hello everyone, and welcome back. <break time="0.5s"/> I'm Bogdan Parkhomenko. <break time="1.5s"/>
```

空にすれば挨拶を入れません。既定の「new journey（新しい旅の始まり）」は
開設回向けの文言なので、回を重ねたら `welcome back` などへ差し替えてください。

---

## アバターと音声を変える

`.env` の `HEYGEN_AVATAR_ID` / `HEYGEN_VOICE_ID` を書き換えます。
変更後は短い文で1本だけ生成して確認できます（消費は最小）。

```bash
./tool_heygen_test.sh                 # 既定の短文で確認
./tool_heygen_test.sh "好きな文章"     # 文章を指定して確認
```

出力は `/tmp/heygen_test.mp4` です。見た目・声・背景の緑・画面字幕が
出ていないことを確認してください。

**既に生成済みの動画は変わりません。** 新しいアバターは次に生成する分から
適用されます。作り直すなら `--force` が必要です。

---

## 生成物をすべて消してやり直す

```bash
python tools/clean_data.py
```

`data/` 配下は丸ごと git 管理外です。すべて元音声から再生成できます。
