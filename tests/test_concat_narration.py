"""concat_narration._merge_ssml() — パートを1つの台本にまとめる処理。

以前は "\\n\\n" で連結していたため、_full.txt に <speak> 要素が
パート数だけ並ぶ壊れた XML になっていた。最終成果物として音声合成に
渡せる形であることを保証する。
"""
import xml.etree.ElementTree as ET

from tools.concat_narration import _merge_ssml


def write_parts(tmp_path, bodies: list[str]):
    paths = []
    for i, body in enumerate(bodies, 1):
        p = tmp_path / f"t_part{i:02d}.txt"
        p.write_text(f"<speak>{body}</speak>", encoding="utf-8")
        paths.append(p)
    return paths


def test_single_part_is_valid_ssml(tmp_path):
    out = _merge_ssml(write_parts(tmp_path, ["Only part."]))
    assert ET.fromstring(out).tag == "speak"


def test_multiple_parts_produce_one_speak_element(tmp_path):
    out = _merge_ssml(write_parts(tmp_path, ["One.", "Two.", "Three."]))
    assert out.count("<speak>") == 1
    assert out.count("</speak>") == 1


def test_multiple_parts_parse_as_xml(tmp_path):
    """回帰テスト: 素朴な連結では 'junk after document element' で落ちていた。"""
    out = _merge_ssml(write_parts(tmp_path, ["One.", "Two.", "Three."]))
    assert ET.fromstring(out).tag == "speak"


def test_no_content_is_lost(tmp_path):
    out = _merge_ssml(write_parts(tmp_path, ["Alpha.", "Bravo.", "Charlie."]))
    for word in ("Alpha.", "Bravo.", "Charlie."):
        assert word in out


def test_inner_break_tags_survive(tmp_path):
    out = _merge_ssml(write_parts(tmp_path, ['A. <break time="0.5s"/> B.']))
    assert ET.fromstring(out).findall("break")


def test_a_break_is_inserted_between_parts(tmp_path):
    """パート境界はトピックの切れ目なので間を空ける。"""
    out = _merge_ssml(write_parts(tmp_path, ["One.", "Two."]))
    assert '<break time="1.0s"/>' in out


def test_empty_parts_are_skipped(tmp_path):
    out = _merge_ssml(write_parts(tmp_path, ["Real content.", "", "More content."]))
    assert ET.fromstring(out).tag == "speak"
    assert "Real content." in out and "More content." in out


def test_surrounding_whitespace_is_tolerated(tmp_path):
    p = tmp_path / "t_part01.txt"
    p.write_text("\n  <speak>  Body.  </speak>  \n", encoding="utf-8")
    assert ET.fromstring(_merge_ssml([p])).tag == "speak"
