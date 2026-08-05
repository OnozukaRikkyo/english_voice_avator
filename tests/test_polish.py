"""polish — 完成した台本をフルテキストで点検して直す工程。

この設計の要は「モデルは差分を**提案**するだけで、当てるのはコード」という点。
前の設計はモデルに全文を書き直させたため、直すつもりのない文が巻き添えで
壊れた（"two-thirds of demand" が短縮されて意味を失った）。

だから守るべき性質は3つ:
  - 原文に厳密一致しない引用は当てない（作文された引用を弾く）
  - 一意に決まらない引用は当てない（どちらを直すか決められない）
  - 数値・固有名詞が消えた差分は当てない
"""
import json

import pytest

from pipeline import defects, polish

SCRIPT = ('<speak>The crater was ten meters wide. <break time="0.5s"/> '
          'The fire consumed one hundred thousand square meters. '
          'Officials called it contained.</speak>')


# ── パッチの適用 ──────────────────────────────────────────────────────────────

def test_exact_match_is_applied():
    got, applied, rejected = polish.apply_patches(
        SCRIPT, [{"old": "Officials called it contained.",
                  "new": "Officials reportedly called it contained."}])
    assert "reportedly called it" in got
    assert len(applied) == 1 and not rejected


def test_invented_quote_is_rejected():
    """モデルが引用を作文することは実際に起きる。当てずに棄却する。"""
    got, applied, rejected = polish.apply_patches(
        SCRIPT, [{"old": "Officials said the fire was out.", "new": "..."}])
    assert got == SCRIPT
    assert not applied and "見つかりません" in rejected[0]["reason"]


def test_ambiguous_quote_is_rejected():
    """同じ文が2箇所にあると、どちらを直すのか決められない。"""
    doubled = "<speak>Same line. Same line.</speak>"
    got, applied, rejected = polish.apply_patches(
        doubled, [{"old": "Same line.", "new": "Changed."}])
    assert got == doubled
    assert not applied and "特定できません" in rejected[0]["reason"]


def test_deletion_is_allowed():
    got, applied, _ = polish.apply_patches(
        SCRIPT, [{"old": " Officials called it contained.", "new": ""}])
    assert "Officials" not in got and len(applied) == 1


def test_one_bad_patch_does_not_block_the_others():
    got, applied, rejected = polish.apply_patches(SCRIPT, [
        {"old": "NOT IN THE SCRIPT", "new": "x"},
        {"old": "The crater was ten meters wide.", "new": "The crater was ten meters across."},
    ])
    assert "ten meters across" in got
    assert len(applied) == 1 and len(rejected) == 1


# ── C の機械照合 ──────────────────────────────────────────────────────────────

def test_lost_number_is_caught():
    lost = polish.check_kept("The fire consumed one hundred thousand square meters.",
                             "The fire consumed part of the site.")
    assert lost and "hundred" in lost


def test_lost_proper_noun_is_caught():
    lost = polish.check_kept("According to Bank of Russia, the figure held.",
                             "According to the regulator, the figure held.")
    assert lost and "Bank of Russia" in lost


def test_rewording_that_keeps_the_facts_passes():
    assert polish.check_kept(
        "The Bank of Russia put the figure at one hundred thousand.",
        "One hundred thousand, according to the Bank of Russia.") is None


def test_removing_only_false_provenance_passes():
    """"our sources" を削るのは正しい修正。数も名前も減っていない。"""
    assert polish.check_kept("Our sources say Sberbank absorbed the loss.",
                             "Sberbank reportedly absorbed the loss.") is None


# ── ループ ────────────────────────────────────────────────────────────────────

def test_repair_drops_edits_that_lose_facts(monkeypatch):
    """モデルが「直したつもりで事実を落とす」のは実際に起きた失敗。"""
    patch = [{"old": "The fire consumed one hundred thousand square meters.",
              "new": "The fire spread widely.", "why": "簡潔にしました"}]
    monkeypatch.setattr(polish.llm, "generate_json", lambda *a, **k: json.dumps(patch))
    got, log = polish.repair(SCRIPT, [defects.Defect("X", "y", "z")], "m")
    assert got == SCRIPT                       # 当てていない
    assert log[0]["result"] == "棄却"


def test_repair_applies_a_verified_edit(monkeypatch):
    calls = []

    def fake(model, prompt, schema, **k):
        calls.append(prompt)
        if len(calls) == 1:                    # B: パッチ
            return json.dumps([{"old": "Officials called it contained.",
                                "new": "Officials reportedly called it contained.",
                                "why": "ヘッジを戻しました"}])
        return json.dumps([{"ok": True, "why": "保たれています"}])   # C: 検証

    monkeypatch.setattr(polish.llm, "generate_json", fake)
    got, log = polish.repair(SCRIPT, [defects.Defect("X", "y", "z")], "m")
    assert "reportedly" in got and log[0]["result"] == "適用"


def test_verifier_rejection_blocks_the_edit(monkeypatch):
    def fake(model, prompt, schema, **k):
        if "Defects" in prompt:
            return json.dumps([{"old": "Officials called it contained.",
                                "new": "The fire was contained.", "why": "整えました"}])
        return json.dumps([{"ok": False, "why": "帰属が失われています"}])

    monkeypatch.setattr(polish.llm, "generate_json", fake)
    got, log = polish.repair(SCRIPT, [defects.Defect("X", "y", "z")], "m")
    assert got == SCRIPT and log[0]["result"] == "棄却"


def test_overlapping_edits_are_rejected():
    """重なる修正は適用順で結果が変わる。2つ目を当てずに棄却する。"""
    text = "<speak>The bank absorbed the loss quietly.</speak>"
    got, applied, rejected = polish.apply_patches(text, [
        {"old": "The bank absorbed the loss quietly.",
         "new": "The bank reportedly absorbed the loss."},
        {"old": "absorbed the loss", "new": "wrote off the loss"},
    ])
    assert "reportedly" in got and "wrote off" not in got
    assert len(applied) == 1 and "重なって" in rejected[0]["reason"]


def test_independent_edits_both_apply():
    text = "<speak>First sentence here. Second sentence there.</speak>"
    got, applied, rejected = polish.apply_patches(text, [
        {"old": "First sentence here.", "new": "First line here."},
        {"old": "Second sentence there.", "new": "Second line there."},
    ])
    assert "First line here. Second line there." in got
    assert len(applied) == 2 and not rejected


def test_hedging_fix_is_not_treated_as_a_loss(monkeypatch):
    """A が「断定を可能性に直せ」と言った修正を、C が「弱められた」と棄却していた。

    実測で12件。A の意図した修正を C が潰す自家中毒で、直せない欠陥が
    残存リストに積み上がっていた。修正の理由を C に渡して区別させる。
    """
    seen = {}

    def fake(model, prompt, schema, **k):
        if "Defects" in prompt:
            return json.dumps([{"old": "Officials called it contained.",
                                "new": "Officials may have called it contained.",
                                "why": "断定を可能性に直しました"}])
        seen["verify"] = prompt
        return json.dumps([{"ok": True, "why": "意図どおりです"}])

    monkeypatch.setattr(polish.llm, "generate_json", fake)
    polish.repair(SCRIPT, [defects.Defect("ATTRIBUTION", "q", "断定です")], "m")
    assert "reason for this edit" in seen["verify"]
    assert "断定を可能性に直しました" in seen["verify"]


def test_remaining_defects_are_counted_after_the_last_repair(monkeypatch, tmp_path):
    """記録の「残存欠陥」が最後の修正より前の検出だと、直した分まで残存に並ぶ。"""
    calls = {"detect": 0}

    def fake_detect(script, transcript, model):
        calls["detect"] += 1
        return [] if calls["detect"] > 1 else [defects.Defect("X", "Officials called it contained.", "d")]

    monkeypatch.setattr(polish, "detect", fake_detect)
    monkeypatch.setattr(polish, "repair",
                        lambda s, f, m: (s.replace("contained", "under control"),
                                         [{"result": "適用", "old": "a", "new": "b", "why": "w"}]))
    src = tmp_path / "ep_full.txt"
    src.write_text(SCRIPT * 30, encoding="utf-8")
    polish.polish_file(src, tmp_path / "out_full.txt", "", model="m")

    report = (tmp_path / "out_defects.md").read_text(encoding="utf-8")
    assert "なし。" in report            # 修正後に数え直して0件
    assert calls["detect"] == 2          # 検出で始まり、修正後にもう一度
