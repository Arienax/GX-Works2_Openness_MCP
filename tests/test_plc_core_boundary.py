import copy
import json

import pytest

from model_provider import ToolCall
from plc_agent_tools import build_default_tool_registry, build_tool_context
from plc_core import PLCCore, accept_candidate_patch
from plc_ir import build_plc_ir, canonical_sha256
from session_store import SessionStore
from tool_runtime import InProcessToolRuntime


def _rung(rung_id, input_address, output_address, note):
    return {
        "rung_id": rung_id,
        "debug_note": note,
        "header_element": None,
        "shared_inputs": [],
        "branches": [
            {
                "branch_id": 1,
                "y_offset_level": 0,
                "inputs": [
                    {"type": "NO", "address": input_address, "label": ""}
                ],
                "outputs": [
                    {"type": "COIL", "address": output_address, "label": ""}
                ],
            }
        ],
    }


def _program(two_networks=False):
    rungs = [_rung(1, "X0", "Y0", "启动输出")]
    comments = {"X0": "启动", "Y0": "运行"}
    if two_networks:
        rungs.append(_rung(2, "X1", "Y1", "辅助输出"))
        comments.update({"X1": "辅助输入", "Y1": "辅助输出"})
    return build_plc_ir(
        {"device_comments": comments, "rungs": rungs},
        plc_model="FX3U",
        program_name="MAIN",
        revision=1,
    )


def _modify_patch(program):
    replacement = copy.deepcopy(program["networks"][0]["ladder"])
    replacement["branches"][0]["inputs"].append(
        {"type": "NC", "address": "X2", "label": ""}
    )
    return {
        "base_revision": program["revision"],
        "base_ir_sha256": canonical_sha256(program),
        "target_revision": program["revision"] + 1,
        "operations": [
            {
                "operation": "modify_network",
                "network": "N0001",
                "ladder": replacement,
            }
        ],
        "device_comments": {"X2": "停止"},
    }


def _persist_base(store, project_id, program):
    core = PLCCore()
    version_id, output_dir = store.prepare_version(project_id)
    compiled = core.compile_project(program, output_dir)
    metadata = store._ir_metadata(program)
    metadata.update(
        {
            "target_mode": "ladder",
            "plc_model": "FX3U",
            "program_name": "MAIN",
            "artifacts": dict(compiled["artifacts"]),
            "confirmed_spec_snapshot": None,
            "confirmed_spec_hash": None,
        }
    )
    return store.complete_version(project_id, version_id, metadata)


def test_plc_core_reads_validates_and_compiles_through_existing_pipeline(tmp_path):
    program = _program()
    output_dir = tmp_path / "compiled"
    core = PLCCore()

    network = core.read_network(program, "N0001")
    diagnostics = core.get_diagnostics(program)
    validation = core.validate_project(program)
    compiled = core.compile_project(program, output_dir)

    assert network["writes"] == ["Y0"]
    assert diagnostics["counts"]["error"] == 0
    assert validation["valid"] is True
    assert set(compiled["artifacts"]) == {
        "json",
        "ir",
        "svg",
        "st_from_ir",
        "program_csv",
        "comment_csv",
    }
    assert all((output_dir / name).is_file() for name in compiled["artifacts"].values())
    assert len(compiled["hashes"]) == 6


def test_network_patch_supports_add_modify_and_delete_with_structured_diff():
    core = PLCCore()
    base = _program(two_networks=True)
    replacement = copy.deepcopy(base["networks"][0]["ladder"])
    replacement["branches"][0]["inputs"].append(
        {"type": "NC", "address": "X2", "label": ""}
    )
    patch = {
        "base_revision": 1,
        "base_ir_sha256": canonical_sha256(base),
        "target_revision": 2,
        "operations": [
            {
                "operation": "modify_network",
                "network": "N0001",
                "ladder": replacement,
            },
            {"operation": "delete_network", "network": "N0002"},
            {
                "operation": "add_network",
                "network": "N0003",
                "after": "N0001",
                "ladder": _rung(3, "X3", "M0", "新增状态"),
            },
        ],
        "device_comments": {"X2": "停止", "X3": "条件", "M0": "状态"},
    }

    candidate = core.patch_program(base, patch)

    assert candidate["target_revision"] == 2
    assert candidate["diff"]["added"] == ["N0003"]
    assert candidate["diff"]["deleted"] == ["N0002"]
    assert candidate["diff"]["modified"] == ["N0001"]
    assert candidate["diff"]["device_comments_changed"] is True
    assert [item["marker"] for item in candidate["diff"]["changes"]] == [
        "+",
        "-",
        "~",
    ]
    assert candidate["diagnostics"]["valid"] is True


def test_tool_runtime_hides_candidate_ir_from_model_but_keeps_it_for_ui():
    program = _program()
    version = {
        "id": "v0001",
        "target_mode": "ladder",
        "plc_model": "FX3U",
        "program_name": "MAIN",
        "revision": 1,
        "confirmed_spec_snapshot": None,
    }
    context = build_tool_context(
        {
            "id": "project1",
            "name": "测试项目",
            "plc_model": "FX3U",
            "active_version_id": "v0001",
            "versions": [version],
        },
        version=version,
        program_ir=program,
    )
    runtime = InProcessToolRuntime(build_default_tool_registry())

    result = runtime.invoke(
        ToolCall("call_patch", "patch_program", {"patch": _modify_patch(program)}),
        context,
    )

    public = json.loads(result.content)
    assert result.is_error is False
    assert public["status"] == "confirmation_required"
    assert "_candidate_ir" not in result.content
    assert "_confirmed_spec" not in result.content
    pending = result.data["data"]["pending_action"]
    assert pending["_candidate_ir"]["revision"] == 2


def test_invalid_candidate_never_creates_a_version(tmp_path):
    store = SessionStore(base_dir=tmp_path / "workspace", legacy_dir=tmp_path)
    project = store.create_project("候选测试", plc_model="FX3U")
    base = _program()
    version = _persist_base(store, project["id"], base)
    context = build_tool_context(
        store.get_project(project["id"]),
        version=version,
        program_ir=base,
    )
    invalid = _modify_patch(base)
    invalid["operations"][0]["ladder"]["rung_id"] = 99

    result = build_default_tool_registry().call(
        "patch_program", {"patch": invalid}, context
    )

    assert result["ok"] is False
    assert len(store.get_project(project["id"])["versions"]) == 1
    assert sorted(path.name for path in store.version_dir(project["id"], "v0001").parent.iterdir()) == [
        "v0001"
    ]


def test_candidate_cancel_changes_neither_current_version_nor_gx_state(tmp_path):
    store = SessionStore(base_dir=tmp_path / "workspace", legacy_dir=tmp_path)
    project = store.create_project("候选测试", plc_model="FX3U")
    base = _program()
    version = _persist_base(store, project["id"], base)
    original_project = copy.deepcopy(store.get_project(project["id"]))
    original_ir = copy.deepcopy(store.load_program_ir(project["id"], version["id"]))
    context = build_tool_context(original_project, version=version, program_ir=base)

    result = build_default_tool_registry().call(
        "patch_program", {"patch": _modify_patch(base)}, context
    )
    assert result["status"] == "confirmation_required"
    # Cancellation is deliberately represented by not invoking the UI-only accept action.

    assert store.get_project(project["id"])["active_version_id"] == version["id"]
    assert len(store.get_project(project["id"])["versions"]) == 1
    assert store.load_program_ir(project["id"], version["id"]) == original_ir
    assert not (store.project_dir(project["id"]) / "GX Works2 Backups").exists()


def test_accept_candidate_creates_only_one_local_child_version(tmp_path):
    store = SessionStore(base_dir=tmp_path / "workspace", legacy_dir=tmp_path)
    project = store.create_project("候选测试", plc_model="FX3U")
    base = _program()
    version = _persist_base(store, project["id"], base)
    base_ir_path = store.version_dir(project["id"], version["id"]) / "program.ir.json"
    base_bytes = base_ir_path.read_bytes()
    context = build_tool_context(
        store.get_project(project["id"]), version=version, program_ir=base
    )
    tool_result = build_default_tool_registry().call(
        "patch_program", {"patch": _modify_patch(base)}, context
    )
    action = tool_result["data"]["pending_action"]

    accepted = accept_candidate_patch(store, action)

    current = store.get_project(project["id"])
    assert accepted["id"] == "v0002"
    assert accepted["parent_version_id"] == "v0001"
    assert accepted["source_candidate_id"] == action["candidate_id"]
    assert accepted["lifecycle_status"] == "accepted"
    assert current["active_version_id"] == "v0002"
    assert len(current["versions"]) == 2
    assert base_ir_path.read_bytes() == base_bytes
    assert store.load_program_ir(project["id"], "v0002")["revision"] == 2
    assert all(
        (store.version_dir(project["id"], "v0002") / name).is_file()
        for name in accepted["artifacts"].values()
    )
    assert not (store.project_dir(project["id"]) / "GX Works2 Backups").exists()


def test_tampered_candidate_is_rejected_without_creating_a_version(tmp_path):
    store = SessionStore(base_dir=tmp_path / "workspace", legacy_dir=tmp_path)
    project = store.create_project("候选测试", plc_model="FX3U")
    base = _program()
    version = _persist_base(store, project["id"], base)
    context = build_tool_context(
        store.get_project(project["id"]), version=version, program_ir=base
    )
    result = build_default_tool_registry().call(
        "patch_program", {"patch": _modify_patch(base)}, context
    )
    action = copy.deepcopy(result["data"]["pending_action"])
    action["_candidate_ir"]["revision"] = 100

    with pytest.raises(ValueError):
        accept_candidate_patch(store, action)

    assert len(store.get_project(project["id"])["versions"]) == 1
