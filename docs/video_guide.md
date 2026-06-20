# 新規動画の作成手順

## 手順

### 1. 音声ファイルを inbox に置く

```
data/inbox/
  your_audio.m4a   ← ここに置く
```

対応フォーマット: `.m4a` / `.mp4` / `.mp3`

### 2. パイプラインを実行する

```bash
python run_pipeline.py
```

これだけです。以下がすべて自動で実行されます：

1. `data/inbox/` をスキャンし、ファイル名からプロジェクトを自動作成
2. パイプライン実行: `convert → transcribe → rewrite → concat_narration → translate → heygen → concat_video`
3. 動画・ナレーションの結合

## トラブルシューティング

### HeyGen API / アバターIDの確認

```bash
python heygen_check.py
```
