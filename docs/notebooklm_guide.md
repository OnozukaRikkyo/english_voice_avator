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
  your_document_prompt.txt       ← これをそのまま貼り付ける
  your_document_vocabulary.txt   ← 文字起こし用の綴りヒント（自動生成）
```

## 文字起こしとの連携

プロンプトを生成すると、その用語集から**文字起こし用の綴りヒント**も
同時に作られます。以降 `./run.sh` で音声を処理すると自動で読み込まれ、
固有名詞の綴りが安定します（実測で `Kostyantynivka` → `Kostiantynivka`）。

`_vocabulary.txt` は1行1語のただのテキストです。**辞書が誤っていれば
その誤りを押し付けることになる**ので、気になる語は直してください。
行を消せばその語は渡されません。手で直した内容は再抽出で上書きされません。

資料と関係なく足したい語は `data/senario_jp/vocabulary.txt` に書きます。

既存のプロンプトから作り直すこともできます（APIを呼ばないので無料）。

```bash
./gen_notebooklm_prompt.sh --vocabulary-only
```

## 生成されるプロンプトの中身

`gpt-5.6-luna`（OpenAI）が資料を読んで
ドメイン（戦争・政治・経済・技術など）を判定し、そのドメインに合わせて次の3つを書き起こします。
Web検索ツールを有効にしているため、用語の英語表記は実際に検索して確認されます。
モデルの切り替え方は `model_guide.md` を参照してください。

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
