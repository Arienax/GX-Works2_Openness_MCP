import base64
import json
from pathlib import Path

from src.gxw.models import NodeKind
from src.gxw.structured_pou import parse_structured_pou


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gxw_structured_67_71.json"


def _program(sample: int):
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))[str(sample)]
    data = base64.b64decode(fixture["program_pou_base64"])
    return parse_structured_pou(data, logical_name=fixture["logical_name"])


def _function(program):
    matches = [node for node in program.nodes if node.kind == NodeKind.FUNCTION]
    assert len(matches) == 1
    return matches[0]


def test_samples_67_68_and_e_suffix_tracks_extensible_input_arity():
    two = _function(_program(67))
    three = _function(_program(68))

    assert two.symbol == "AND_E-2"
    assert three.symbol == "AND_E-3"
    assert [port.port_kind_code for port in two.ports] == [3, 3, 3, 0, 2]
    assert [port.port_kind_code for port in three.ports] == [3, 3, 3, 3, 0, 2]
    assert two.record_length == 138
    assert three.record_length == 154


def test_sample_68_growth_is_one_port_descriptor_plus_one_input_terminal():
    p67 = _program(67)
    p68 = _program(68)

    assert len(p68.raw) - len(p67.raw) == 80
    assert p68.record_count - p67.record_count == 1
    d4 = [node for node in p68.nodes if node.symbol == "D4"]
    assert len(d4) == 1
    assert d4[0].kind == NodeKind.INPUT
    assert d4[0].record_length == 64


def test_sample_69_fixed_two_input_div_e_has_no_arity_suffix():
    function = _function(_program(69))

    assert function.symbol == "DIV_E"
    assert len(function.ports) == 5
    assert [port.port_kind_code for port in function.ports] == [3, 3, 3, 0, 2]


def test_samples_70_71_plain_vs_enabled_abs_port_abi():
    plain = _function(_program(70))
    enabled = _function(_program(71))

    assert plain.symbol == "ABS"
    assert enabled.symbol == "ABS_E"
    assert [port.port_kind_code for port in plain.ports] == [3, 2]
    assert [port.port_kind_code for port in enabled.ports] == [3, 3, 0, 2]


def test_samples_67_71_continue_header_height_observations():
    for sample in range(67, 72):
        program = _program(sample)
        assert program.canvas_height == 17
        assert program.body_size == len(program.raw) - 0x5F
