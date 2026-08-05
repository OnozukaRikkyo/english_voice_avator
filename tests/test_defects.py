"""defects — モデルを呼ばずに数えられる欠陥。

生成時に「Xを使うな」と禁じる設計は3度失敗した。禁じた表現の代わりに
別の単一テンプレートへ収束するだけだったので、禁止語リストは持たず、
**完成文から数える**方式にしている。ここはその数え方の回帰テスト。
"""
from pipeline import defects


def test_repeated_phrase_is_counted():
    """実際に起きた失敗: "caught my attention" を禁じたら別の型が5回になった。"""
    t = ("When I first saw that figure I stopped. Something else happened. "
         "When I first saw that figure I checked twice. More text here. "
         "When I first saw that figure I assumed a typo.")
    found = defects.repeated_phrases(t)
    assert found and "when i first saw that figure" in found[0].quote
    assert "3 回" in found[0].detail
    assert len(found[0].occurrences) == 3


def test_two_occurrences_are_not_reported():
    """2回までは許容している。ここを厳しくすると普通の文章が引っかかる。"""
    t = "When I first saw it I stopped. Filler text. When I first saw it I checked."
    assert not defects.repeated_phrases(t)


def test_function_words_alone_are_not_reported():
    t = "It is in the room. It is in the house. It is in the car."
    assert not [d for d in defects.repeated_phrases(t) if d.quote == "is in the"]


def test_substring_of_a_longer_phrase_is_not_reported_twice():
    t = ("The financial nervous system matters. Filler. The financial nervous system holds. "
         "Filler two. The financial nervous system breaks.")
    quotes = [d.quote for d in defects.repeated_phrases(t)]
    assert any("financial nervous system" in q for q in quotes)
    assert "the financial" not in quotes


def test_malformed_tag_is_found():
    """実害: <break time="0.5s/> が検証をすり抜けて最終台本に残った。"""
    found = defects.broken_tags('<speak>a <break time="0.5s/> b</speak>')
    assert found and found[0].category == "BROKEN TAG"


def test_unknown_tag_is_found():
    assert defects.broken_tags("<speak><emphasis>x</emphasis></speak>")


def test_double_break_is_found():
    assert defects.double_breaks('a <break time="0.5s"/> <break time="1.0s"/> b')


def test_digits_in_speech_are_found():
    """合成音声は S-400 を「S マイナス400」と読みうる。型番も例外にしない。"""
    found = defects.digits_in_speech("They moved the S-400 battery. It covered 176,000 meters.")
    assert {d.quote for d in found} == {"S-400", "176,000"}


def test_spelled_numbers_pass():
    assert not defects.digits_in_speech(
        "They moved the S-four-hundred battery covering one hundred thousand meters.")


def test_name_variant_is_found():
    """実害: 同じレストランが part05 で Balzi、part07 で Balti になっていた。"""
    t = "The Balzi Rossi burned. Later the Balzi Rossi closed. The Balti Rossi reopened."
    found = defects.name_variants(t)
    assert found and "Balti Rossi" in found[0].quote
    assert "Balzi Rossi" in found[0].fix          # 多いほうへ寄せる


def test_unrelated_names_are_not_flagged():
    t = "The Bank of Russia acted. The United States responded. Bogdan Parkhomenko spoke."
    assert not defects.name_variants(t)


def test_scan_ignores_tags_when_reading_the_prose():
    t = '<speak>The figure was 400. <break time="1.0s"/> Done.</speak>'
    digits = [d.quote for d in defects.scan(t) if d.category == "DIGITS"]
    assert digits == ["400."]                    # 1.0s を数字として拾わない
