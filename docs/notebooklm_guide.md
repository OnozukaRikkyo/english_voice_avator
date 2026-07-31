# NotebookLM プロンプトの生成手順

NotebookLM で音声を作る際に貼り付ける**システムプロンプト**を、
手元の日本語資料から自動生成します。

生成するのはプロンプトだけです。音声そのものは NotebookLM 側で作ります。

## 手順

### 1. 日本語資料を置く

```
data/senario_jp/
  your_document.docx   ← ここに置く
```

対応フォーマット: `.docx` / `.pdf`

### 2. 生成する

```bash
./gen_notebooklm_prompt.sh
```

### 3. 出力を NotebookLM に貼り付ける

```
data/senario_jp/prompts/
  your_document_prompt.txt   ← これをそのまま貼り付ける
```

## 生成されるプロンプトの中身

`gemini-2.5-flash` が資料を読んでドメイン（戦争・政治・経済・技術など）を
判定し、そのドメインに合わせて次の3つを書き起こします。
Google 検索ツールを有効にしているため、用語の英語表記は実際に検索して確認されます。

1. **Role & Objective** — ドメインに合った専門家の役割設定
2. **Document-Specific Vocabulary Guide** — 資料に出てくる難解語の用語集。
   対象読者は「その分野の知識がない一般的なアメリカ人成人」で、
   本当に分からない語（マイナーな地名・型式名・略語・専門用語）だけを選びます
3. **Core Instructions** — 参照すべき権威ある英語サイトの実名
   （紛争なら isw.org、経済なら imf.org など）、資料に明示されていない
   独自の分析視点の見つけ方（具体例2つ）、トーンと構成

## 注意

- `data/` は丸ごと git 管理外です。生成したプロンプトはローカルにのみ残ります
- 用語集は自動生成なので、そのまま使う前に内容を確認してください
  （生成物自身にもその旨の注記が入ります）
- 生成元: `tools/gen_notebooklm_prompt.py`（プロンプト定義は `_META_PROMPT`）
