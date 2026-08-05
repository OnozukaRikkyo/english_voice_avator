"""review — 台本を放送前に点検して直す工程。

この工程の失敗は静かに通る種類のものである:
  - 校閲のつもりで台本を要約してしまう（内容が消える）
  - 直すついでに書き足す（rewrite で削った冗長さが戻る）
  - 指摘は0件なのに文面だけ変わっている（理由の説明がつかない書き換え）
いずれも出来上がったファイルを見ただけでは気づけないので、検証側を固めておく。
"""
import json

import pytest

from pipeline import review

DRAFT = "<speak>" + "x" * 3000 + "</speak>"


def result(revised: str, issues: list | None = None) -> dict:
    return {"issues": issues if issues is not None else [], "revised": revised}


def issue(severity: str = "high") -> dict:
    return {"severity": severity, "type": "UNSUPPORTED", "quote": "q",
            "problem": "p", "fix": "f"}


# ── _validate ─────────────────────────────────────────────────────────────────

def test_unchanged_draft_passes():
    assert review._validate(result(DRAFT), DRAFT) is None


def test_empty_revision_is_rejected():
    assert "空" in review._validate(result(""), DRAFT)


def test_truncated_ssml_is_rejected():
    broken = result('<speak>A shift unfolds. <break time=')
    assert "SSML" in review._validate(broken, DRAFT)


def test_double_speak_wrapper_is_rejected():
    doubled = result(f"<speak>{DRAFT}</speak>")
    assert "SSML" in review._validate(doubled, DRAFT)


def test_summarised_revision_is_rejected():
    """校閲は書き直しではない。大幅に短ければ内容を落としている。"""
    shrunk = result("<speak>" + "x" * 1000 + "</speak>")
    problem = review._validate(shrunk, DRAFT)
    assert problem is not None and "下限" in problem


def test_padded_revision_is_rejected():
    """直すついでの書き足しは、rewrite で削った冗長さを戻す。"""
    padded = result("<speak>" + "x" * 5000 + "</speak>")
    problem = review._validate(padded, DRAFT)
    assert problem is not None and "上限" in problem


def test_issues_must_be_a_list():
    assert "issues" in review._validate({"issues": "none", "revised": DRAFT}, DRAFT)


# ── review_part ───────────────────────────────────────────────────────────────

def _run(tmp_path, monkeypatch, payload: dict, draft: str = DRAFT):
    src = tmp_path / "draft" / "parts"
    src.mkdir(parents=True)
    part = src / "ep_part01.txt"
    part.write_text(draft, encoding="utf-8")
    out = tmp_path / "narration" / "parts" / "ep_part01.txt"
    out.parent.mkdir(parents=True)

    monkeypatch.setattr(review.llm, "generate_json",
                        lambda *a, **k: json.dumps([payload]))
    review.review_part(part, out, source="transcript text")
    return out, src / "ep_part01_review.md"


def test_revision_is_written_and_reported(tmp_path, monkeypatch):
    fixed = "<speak>" + "y" * 2900 + "</speak>"
    out, report = _run(tmp_path, monkeypatch, result(fixed, [issue()]))
    assert out.read_text(encoding="utf-8") == fixed
    assert "UNSUPPORTED" in report.read_text(encoding="utf-8")


def test_no_issues_keeps_the_draft_verbatim(tmp_path, monkeypatch):
    """指摘0件なのに文面が変わるのは、理由の説明がつかない書き換えである。"""
    drifted = "<speak>" + "z" * 2950 + "</speak>"
    out, report = _run(tmp_path, monkeypatch, result(drifted, []))
    assert out.read_text(encoding="utf-8") == DRAFT
    assert "問題なし" in report.read_text(encoding="utf-8")


def test_broken_response_raises_instead_of_writing(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError):
        _run(tmp_path, monkeypatch, result("<speak>too short</speak>", [issue()]))
    assert not (tmp_path / "narration" / "parts" / "ep_part01.txt").exists()


# ── run() ─────────────────────────────────────────────────────────────────────

def test_review_reports_are_not_reviewed_again(tmp_path, monkeypatch):
    """レポートは draft/parts/ に置くため、入力の glob が拾わないことを確かめる。"""
    src = tmp_path / "draft" / "parts"
    src.mkdir(parents=True)
    (src / "ep_part01.txt").write_text(DRAFT, encoding="utf-8")
    (src / "ep_part01_review.md").write_text("# report", encoding="utf-8")
    (src / "ep_part02_review.txt").write_text("stray", encoding="utf-8")

    picked = sorted(p.name for p in src.glob("*_part*.txt")
                    if not p.stem.endswith("_review"))
    assert picked == ["ep_part01.txt"]


def test_orphaned_outputs_are_dropped(tmp_path):
    """part 数が減ったとき、古い出力が残ると concat で本文に混ざる。"""
    src = tmp_path / "draft" / "parts"
    dst = tmp_path / "narration" / "parts"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    for name in ("ep_part01.txt", "ep_part02.txt"):
        (src / name).write_text(DRAFT, encoding="utf-8")
    for name in ("ep_part01.txt", "ep_part02.txt", "ep_part03.txt"):
        (dst / name).write_text(DRAFT, encoding="utf-8")
    (src / "ep_part03_review.md").write_text("# stale", encoding="utf-8")

    parts = sorted(src.glob("*_part0?.txt"))
    review._drop_orphans(parts, src, dst)

    assert sorted(p.name for p in dst.glob("*.txt")) == ["ep_part01.txt", "ep_part02.txt"]
    assert not (src / "ep_part03_review.md").exists()


def test_malformed_tag_in_revision_is_rejected():
    body = "x" * 2900 + '<break time="0.5s/>'
    assert "タグ" in review._validate(result(f"<speak>{body}</speak>"), DRAFT)


def test_known_names_collects_proper_nouns(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("<speak>The Balzi Rossi restaurant on Kudrinskaya Square burned. "
                 "The Balzi Rossi is closed.</speak>", encoding="utf-8")
    names = review.known_names([p])
    assert "Balzi Rossi" in names
    assert names.index("Balzi Rossi") == 0        # 頻度順


def test_names_block_reaches_the_prompt(tmp_path, monkeypatch):
    """表記揺れは part をまたいで起きるので、確定済みの綴りを渡せないと見つからない。"""
    seen = {}
    monkeypatch.setattr(review.llm, "generate_json",
                        lambda m, prompt, *a, **k: seen.setdefault("p", prompt) and "" or
                        json.dumps([result(DRAFT, [])]))
    src = tmp_path / "draft" / "parts"
    src.mkdir(parents=True)
    part = src / "ep_part02.txt"
    part.write_text(DRAFT, encoding="utf-8")
    out = tmp_path / "narration" / "parts" / "ep_part02.txt"
    out.parent.mkdir(parents=True)
    review.review_part(part, out, source="", names=["Balzi Rossi"])
    assert "Balzi Rossi" in seen["p"]
