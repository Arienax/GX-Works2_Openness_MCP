import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def _transport_field_accesses(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fields = {"choices", "delta", "reasoning_content"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in fields:
            found.append((node.lineno, node.attr))
        elif isinstance(node, ast.Subscript):
            key = node.slice
            if isinstance(key, ast.Constant) and key.value in fields:
                found.append((node.lineno, key.value))
    return found


def test_plc_and_gx_core_do_not_import_model_or_vendor_clients():
    core_files = [
        SOURCE_ROOT / "plc_ir.py",
        SOURCE_ROOT / "plc_json_validator.py",
        SOURCE_ROOT / "plc_semantics.py",
        SOURCE_ROOT / "plc_static_analyzer.py",
        SOURCE_ROOT / "plc_timing.py",
        SOURCE_ROOT / "plc_st_renderer.py",
        SOURCE_ROOT / "draw.py",
        *sorted((SOURCE_ROOT / "gxworks2").rglob("*.py")),
        *sorted((SOURCE_ROOT / "simulator").rglob("*.py")),
    ]
    forbidden_roots = {
        "openai",
        "anthropic",
        "zhipuai",
        "model_provider",
        "plc_agent",
    }

    violations = []
    for path in core_files:
        for imported in _imports(path):
            if imported.split(".", 1)[0] in forbidden_roots:
                violations.append(f"{path.relative_to(ROOT)} -> {imported}")
    assert violations == []


def test_provider_does_not_import_plc_gx_or_automation_implementation():
    forbidden_roots = {"plc_ir", "plc_core", "gxworks2", "simulator", "pywinauto", "draw"}
    violations = [
        imported
        for imported in _imports(SOURCE_ROOT / "model_provider.py")
        if imported.split(".", 1)[0] in forbidden_roots
    ]
    assert violations == []


def test_agent_depends_on_runtime_not_plc_implementation():
    imports = _imports(SOURCE_ROOT / "plc_agent.py")
    forbidden_roots = {"plc_core", "plc_ir", "plc_agent_tools", "gxworks2", "pywinauto"}
    assert [
        imported
        for imported in imports
        if imported.split(".", 1)[0] in forbidden_roots
    ] == []
    assert "tool_runtime" in imports
    assert "model_provider" in imports


def test_only_model_provider_imports_openai_sdk():
    violations = []
    for path in SOURCE_ROOT.rglob("*.py"):
        if path.name == "model_provider.py":
            continue
        if any(imported.split(".", 1)[0] == "openai" for imported in _imports(path)):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_agent_and_api_do_not_parse_vendor_response_fields():
    assert _transport_field_accesses(SOURCE_ROOT / "api.py") == []
    assert _transport_field_accesses(SOURCE_ROOT / "plc_agent.py") == []
