import base64
import json
from pathlib import Path

from src.gxw.connectivity import build_connectivity_graph
from src.gxw.models import Point
from src.gxw.structured_pou import parse_structured_pou


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gxw_structured_54_58.json"


def _program(sample: int):
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))[str(sample)]
    data = base64.b64decode(fixture["program_pou_base64"])
    return parse_structured_pou(data, logical_name=fixture["logical_name"])


def _node(program, symbol):
    matches = [node for node in program.nodes if node.symbol == symbol]
    assert len(matches) == 1
    return matches[0]


def test_sample_54_confirms_coincident_ports_connect_without_wire_record():
    program = _program(54)
    graph = build_connectivity_graph(program)
    mov = _node(program, "MOV")
    y1 = _node(program, "Y1")

    assert mov.ports[2].port_kind_code == 0
    assert mov.port_point(2) == Point(29, 2)
    assert y1.port_point(0) == Point(29, 2)
    assert all(
        wire.start != Point(29, 2) and wire.end != Point(29, 2)
        for wire in program.wires
    )
    assert graph.ports_connected(mov.offset, 2, y1.offset, 0)


def test_sample_55_spaced_mov_io_creates_explicit_wires():
    program = _program(55)
    graph = build_connectivity_graph(program)
    mov = _node(program, "MOV")
    value = _node(program, "10")
    d1 = _node(program, "D1")

    assert value.port_point(0) == Point(11, 3)
    assert mov.port_point(1) == Point(22, 3)
    assert mov.port_point(3) == Point(29, 3)
    assert d1.port_point(0) == Point(50, 3)
    assert [
        (wire.start.x, wire.start.y, wire.end.x, wire.end.y)
        for wire in program.wires[-2:]
    ] == [(11, 3, 22, 3), (29, 3, 50, 3)]
    assert graph.ports_connected(value.offset, 0, mov.offset, 1)
    assert graph.ports_connected(mov.offset, 3, d1.offset, 0)


def test_sample_56_t_junction_uses_endpoint_on_segment_geometry():
    program = _program(56)
    graph = build_connectivity_graph(program)
    x1 = _node(program, "X1")
    x2 = _node(program, "X2")
    y1 = _node(program, "Y1")

    # X1's right port lands on the branch point (10,7). The two vertical
    # segments then connect to the upper/lower horizontal branch wires.
    assert x1.port_point(1) == Point(10, 7)
    assert graph.ports_connected(x1.offset, 1, x2.offset, 0)
    assert graph.ports_connected(x1.offset, 1, y1.offset, 0)
    assert not graph.ports_connected(x1.offset, 0, x1.offset, 1)


def test_sample_57_interior_crossing_does_not_merge_wire_nets():
    program = _program(57)
    graph = build_connectivity_graph(program)
    vertical = next(
        wire for wire in program.wires
        if (wire.start.x, wire.start.y, wire.end.x, wire.end.y) == (73, 4, 73, 7)
    )
    horizontal = next(
        wire for wire in program.wires
        if (wire.start.x, wire.start.y, wire.end.x, wire.end.y) == (71, 5, 75, 5)
    )

    assert graph.net_for_wire(vertical.offset).index != graph.net_for_wire(horizontal.offset).index


def test_sample_58_endpoint_on_wire_interior_merges_wire_nets():
    program = _program(58)
    graph = build_connectivity_graph(program)
    horizontal = next(
        wire for wire in program.wires
        if (wire.start.x, wire.start.y, wire.end.x, wire.end.y) == (71, 5, 75, 5)
    )
    vertical = next(
        wire for wire in program.wires
        if (wire.start.x, wire.start.y, wire.end.x, wire.end.y) == (73, 5, 73, 8)
    )

    assert graph.net_for_wire(vertical.offset).index == graph.net_for_wire(horizontal.offset).index
