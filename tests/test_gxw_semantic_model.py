import base64
import json
from pathlib import Path

from src.gxw.semantic import SemanticPortRole, TerminalRole, build_semantic_model
from src.gxw.structured_pou import parse_structured_pou


_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_FIXTURE_FILES = (
    _FIXTURE_DIR / "gxw_structured_64.json",
    _FIXTURE_DIR / "gxw_structured_65_66.json",
    _FIXTURE_DIR / "gxw_structured_67_71.json",
)


def _fixture(sample: int):
    key = str(sample)
    for path in _FIXTURE_FILES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if key in payload:
            return payload[key]
    raise KeyError(sample)


def _program(sample: int):
    fixture = _fixture(sample)
    data = base64.b64decode(fixture["program_pou_base64"])
    return parse_structured_pou(data, logical_name=fixture["logical_name"])


def _model(sample: int):
    return build_semantic_model(_program(sample))


def _function(model, symbol: str):
    matches = [function for function in model.functions if function.serialized_symbol == symbol]
    assert len(matches) == 1
    return matches[0]


def test_sample_64_preserves_unresolved_terminal_as_semantic_issue():
    model = _model(64)
    unresolved = [terminal for terminal in model.terminals if terminal.symbol == "?"]

    assert len(unresolved) == 1
    assert unresolved[0].role == TerminalRole.SOURCE
    assert unresolved[0].unresolved
    assert any(issue.code == "unresolved_terminal" for issue in model.issues)


def test_sample_65_function_to_function_enable_connection_uses_shared_net():
    model = _model(65)
    mov = _function(model, "MOV")
    add = _function(model, "ADD_E-2")

    assert mov.enable_out is not None
    assert add.enable_in is not None
    assert mov.enable_out.net_index == add.enable_in.net_index
    assert add.declared_arity == 2
    assert add.data_input_count == 2


def test_samples_66_68_resolve_extensible_function_family_and_arity():
    add = _function(_model(66), "ADD_E-3")
    and_fn = _function(_model(68), "AND_E-3")

    assert (add.base_name, add.extensible_inputs, add.declared_arity) == ("ADD_E", True, 3)
    assert (and_fn.base_name, and_fn.extensible_inputs, and_fn.declared_arity) == ("AND_E", True, 3)
    assert add.data_input_count == 3
    assert and_fn.data_input_count == 3
    assert [port.role for port in and_fn.ports] == [
        SemanticPortRole.ENABLE_IN,
        SemanticPortRole.DATA_IN,
        SemanticPortRole.DATA_IN,
        SemanticPortRole.DATA_IN,
        SemanticPortRole.ENABLE_OUT,
        SemanticPortRole.DATA_OUT,
    ]


def test_sample_69_fixed_div_e_is_not_treated_as_extensible_suffix_family():
    div = _function(_model(69), "DIV_E")

    assert div.base_name == "DIV_E"
    assert not div.extensible_inputs
    assert div.declared_arity is None
    assert div.data_input_count == 2
    assert div.has_enable_interface


def test_samples_70_71_plain_vs_enabled_abs_semantics_and_terminal_bindings():
    plain_model = _model(70)
    enabled_model = _model(71)
    plain = _function(plain_model, "ABS")
    enabled = _function(enabled_model, "ABS_E")

    assert [port.role for port in plain.ports] == [
        SemanticPortRole.DATA_IN,
        SemanticPortRole.DATA_OUT,
    ]
    assert not plain.has_enable_interface
    assert plain.data_inputs[0].terminal_symbols == ("D0",)
    assert plain.data_outputs[0].terminal_symbols == ("D2",)

    assert [port.role for port in enabled.ports] == [
        SemanticPortRole.ENABLE_IN,
        SemanticPortRole.DATA_IN,
        SemanticPortRole.ENABLE_OUT,
        SemanticPortRole.DATA_OUT,
    ]
    assert enabled.has_enable_interface
    assert enabled.enable_in.terminal_symbols == ("X1",)
    assert enabled.data_inputs[0].terminal_symbols == ("D0",)
    assert enabled.data_outputs[0].terminal_symbols == ("D2",)


def test_observed_samples_have_no_unexpected_semantic_warnings_except_64_placeholder():
    for sample in range(65, 72):
        assert _model(sample).issues == ()
