import base64
import json
from pathlib import Path

from src.gxw.connectivity import build_connectivity_graph
from src.gxw.models import NodeKind, Point
from src.gxw.structured_pou import parse_structured_pou


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gxw_structured_65_66.json"


def _program(sample: int):
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))[str(sample)]
    data = base64.b64decode(fixture["program_pou_base64"])
    return parse_structured_pou(data, logical_name=fixture["logical_name"])


def _node(program, symbol):
    matches = [node for node in program.nodes if node.symbol == symbol]
    assert len(matches) == 1
    return matches[0]


def test_sample_65_mov_eno_connects_to_add_en():
    program = _program(65)
    graph = build_connectivity_graph(program)
    mov = _node(program, "MOV")
    add = _node(program, "ADD_E-2")

    assert all(node.symbol != "?" for node in program.nodes)
    assert [port.port_kind_code for port in add.ports] == [3, 3, 3, 0, 2]
    assert mov.port_point(2) == Point(35, 5)
    assert add.port_point(0) == Point(45, 11)
    assert [(wire.start.x, wire.start.y, wire.end.x, wire.end.y) for wire in program.wires[-2:]] == [
        (35, 5, 45, 5),
        (45, 5, 45, 11),
    ]
    assert graph.ports_connected(mov.offset, 2, add.offset, 0)
    assert not graph.ports_connected(mov.offset, 2, add.offset, 3)


def test_sample_66_add_e_symbol_suffix_tracks_input_arity():
    program = _program(66)
    add = _node(program, "ADD_E-3")

    assert add.kind == NodeKind.FUNCTION
    assert len(add.ports) == 6
    assert [port.port_kind_code for port in add.ports] == [3, 3, 3, 3, 0, 2]
    assert [add.port_point(index) for index in range(6)] == [
        Point(45, 11),
        Point(45, 12),
        Point(45, 13),
        Point(45, 14),
        Point(51, 11),
        Point(51, 12),
    ]
    assert program.canvas_height == 17
