# 音声から台本を作る手順

## 手順

### 1. 音声ファイルを inbox に置く

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

### 2. パイプラインを実行する

```bash
./run.sh
```

これだけです。以下がすべて自動で実行されます：

1. `data/inbox/` をスキャンし、ファイル名からプロジェクトを自動作成
2. パイプライン実行: `convert → transcribe → rewrite → concat_narration → translate → heygen → concat_video`

最終成果物は以下の2つです：

- `data/{project}/narration/*_full.txt` — 英語ナレーション台本（SSML）
- `data/{project}/translation/*_ja.txt` — その日本語訳

## トラブルシューティング

### HeyGen API / アバターIDの確認

```bash
python heygen_check.py    # 動画生成を再開するときのみ
```

### 生成物をすべて消してやり直す

```bash
python tools/clean_data.py
```

`data/` 配下は丸ごと git 管理外です。すべて元音声から再生成できます。
