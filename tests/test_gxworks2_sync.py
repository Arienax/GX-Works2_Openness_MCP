import csv
import json
from pathlib import Path

from draw import generate_gx_works2_csv
from gxworks2.csv_importer import (
    materialize_gxworks2_version,
    parse_gxworks2_csv,
)
from gxworks2.import_service import ImportService
from gxworks2.csv_manager import CSVManager, GXWORKS2_COMMENT_HEADER, GXWORKS2_HEADER
from gxworks2.models import GXWorks2Session, SyncStatus
from gxworks2.sync_service import GXWorks2SyncService


def _write_program(path, output="Y000", condition="X000"):
    rows = [
        ["MAIN - 副本"],
        ["PLC信息:", "FXCPU FX3U/FX3UC"],
        GXWORKS2_HEADER,
        ["0", "起保停", "LD", condition, "", "", ""],
        ["1", "", "OR", output, "", "", ""],
        ["2", "", "ANI", "X001", "", "", ""],
        ["3", "", "OUT", output, "", "", "电机"],
        ["4", "", "END", "", "", "", ""],
    ]
    with Path(path).open("w", encoding="utf-16", newline="") as handle:
        csv.writer(
            handle,
            delimiter="\t",
            quoting=csv.QUOTE_ALL,
            lineterminator="\r\n",
        ).writerows(rows)


def _write_comments(path, comments=None):
    rows = [["COMMENT - 副本"], GXWORKS2_COMMENT_HEADER]
    rows.extend(comments or [["X000", "启动"], ["X001", "停止"], ["Y000", "电机"]])
    with Path(path).open("w", encoding="utf-16", newline="") as handle:
        csv.writer(
            handle,
            delimiter="\t",
            quoting=csv.QUOTE_ALL,
            lineterminator="\r\n",
        ).writerows(rows)


class _Finder:
    def __init__(self):
        self.session = GXWorks2Session(
            process_id=10,
            window_handle=20,
            title="Fixture - GX Works2",
            executable="GD2.exe",
            project_open=True,
            project_name="Fixture",
            project_state_known=True,
        )

    def find_running(self):
        return self.session


class _Automation:
    def __init__(self, program, comments):
        self.program = Path(program)
        self.comments = Path(comments)

    def inspect_project(self, _session):
        return {
            "automation_available": True,
            "project_open": True,
            "program_ready": True,
            "project_name": "Fixture",
        }

    def export_current_program(self, _session, destination):
        Path(destination).write_bytes(self.program.read_bytes())

    def export_current_comments(self, _session, destination):
        Path(destination).write_bytes(self.comments.read_bytes())


class _RoundtripAutomation(_Automation):
    def __init__(self, program, comments, *, apply_import=True):
        super().__init__(program, comments)
        self.program_bytes = self.program.read_bytes()
        self.comment_bytes = self.comments.read_bytes()
        self.apply_import = apply_import
        self.saved = 0

    def export_current_program(self, _session, destination):
        Path(destination).write_bytes(self.program_bytes)

    def export_current_comments(self, _session, destination):
        Path(destination).write_bytes(self.comment_bytes)

    def import_program_csv(self, _session, source):
        if self.apply_import:
            self.program_bytes = Path(source).read_bytes()
        return {"success": True, "message": "导入完成"}

    def import_comments_csv(self, _session, source):
        if self.apply_import:
            self.comment_bytes = Path(source).read_bytes()
        return {"success": True, "message": "注释导入完成"}

    def save_project(self, _session):
        self.saved += 1
        return {"success": True, "save_required": False, "message": "已保存"}


def _service(tmp_path, automation):
    return GXWorks2SyncService(
        _Finder(),
        automation,
        CSVManager(),
        tmp_path / "backups",
    )


def test_comment_semantic_hash_ignores_document_title_and_row_order(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_comments(first, [["X000", "启动"], ["Y000", "电机"]])
    _write_comments(second, [["Y000", "电机"], ["X000", "启动"]])
    rows = list(csv.reader(second.open(encoding="utf-16"), delimiter="\t"))
    rows[0][0] = "生产线工程"
    with second.open("w", encoding="utf-16", newline="") as handle:
        csv.writer(handle, delimiter="\t", quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)

    manager = CSVManager()
    assert manager.comments_semantic_sha256(first) == manager.comments_semantic_sha256(second)


def test_native_program_roundtrips_through_ladder_ir(tmp_path):
    source = tmp_path / "program.csv"
    comments = tmp_path / "comments.csv"
    output = tmp_path / "version"
    _write_program(source)
    _write_comments(comments)

    parsed = parse_gxworks2_csv(source, comments)
    metadata = materialize_gxworks2_version(source, comments, output, revision=7)

    assert len(parsed.ladder["rungs"]) == 1
    inputs = parsed.ladder["rungs"][0]["branches"][0]["inputs"]
    assert inputs[0]["type"] == "parallel_block"
    assert inputs[1]["type"] == "NC"
    assert metadata["revision"] == 7
    assert metadata["source_kind"] == "gxworks2_sync"
    assert CSVManager().program_semantic_sha256(output / "program.csv") == (
        parsed.source_program_semantic_sha256
    )


def test_state_machine_mps_branches_roundtrip_without_rewriting_logic(tmp_path):
    program = tmp_path / "program.csv"
    comments = tmp_path / "comments.csv"
    output = tmp_path / "version"
    ladder = {
        "device_comments": {"D0": "步骤", "M8000": "运行", "T0": "到时"},
        "rungs": [
            {
                "rung_id": 1,
                "debug_note": "步骤一",
                "header_element": {"type": "BLOCK_INPUT", "expression": "= D0 K1", "label": ""},
                "shared_inputs": [],
                "branches": [
                    {
                        "branch_id": 1,
                        "y_offset_level": 0,
                        "inputs": [{"type": "NO", "address": "M8000", "label": ""}],
                        "outputs": [{"type": "TIMER", "address": "T0", "value": "K10", "label": ""}],
                    },
                    {
                        "branch_id": 2,
                        "y_offset_level": 1,
                        "inputs": [
                            {
                                "type": "parallel_block",
                                "branches": [
                                    [{"type": "NO", "address": "T0", "label": ""}],
                                    [{"type": "NO", "address": "M8000", "label": ""}],
                                ],
                            }
                        ],
                        "outputs": [{"type": "APP_INSTR", "opcode": "MOV", "operands": ["K2", "D0"], "label": ""}],
                    },
                ],
            }
        ],
    }
    assert generate_gx_works2_csv(ladder, program, comments)
    source_hash = CSVManager().program_semantic_sha256(program)

    metadata = materialize_gxworks2_version(program, comments, output)

    assert metadata["source_program_semantic_sha256"] == source_hash
    assert CSVManager().program_semantic_sha256(output / "program.csv") == source_hash


def test_sync_inspection_detects_each_three_way_state(tmp_path):
    base_program = tmp_path / "base.csv"
    app_program = tmp_path / "app.csv"
    gx_program = tmp_path / "gx.csv"
    comments = tmp_path / "comments.csv"
    _write_program(base_program)
    _write_program(app_program)
    _write_program(gx_program)
    _write_comments(comments)
    automation = _Automation(gx_program, comments)
    service = _service(tmp_path, automation)
    context = {"project_id": "p1", "version_id": "v1"}

    first = service.inspect(app_program, comments, import_context=context)
    assert first.status == SyncStatus.SYNCED

    _write_program(gx_program, output="Y001")
    gx_only = service.inspect(app_program, comments, import_context=context)
    assert gx_only.status == SyncStatus.NEEDS_PULL

    # Restore the common snapshot, then change only the application side.
    _write_program(gx_program)
    assert service.inspect(app_program, comments, import_context=context).status == SyncStatus.SYNCED
    _write_program(app_program, output="Y002")
    app_only = service.inspect(app_program, comments, import_context=context)
    assert app_only.status == SyncStatus.NEEDS_PUSH

    _write_program(gx_program, output="Y003")
    both = service.inspect(app_program, comments, import_context=context)
    assert both.status == SyncStatus.CONFLICT
    assert both.details["diff"]["changed_instruction_count"] > 0


def test_first_sync_with_different_programs_requires_source_choice(tmp_path):
    app = tmp_path / "app.csv"
    gx = tmp_path / "gx.csv"
    comments = tmp_path / "comments.csv"
    _write_program(app, output="Y000")
    _write_program(gx, output="Y001")
    _write_comments(comments)
    result = _service(tmp_path, _Automation(gx, comments)).inspect(app, comments)

    assert result.success
    assert result.status == SyncStatus.UNBOUND
    assert Path(result.exported_program_path).is_file()


def test_push_roundtrip_verifies_program_comments_and_saves_project(tmp_path):
    current = tmp_path / "current.csv"
    target = tmp_path / "target.csv"
    current_comments = tmp_path / "current-comments.csv"
    target_comments = tmp_path / "target-comments.csv"
    _write_program(current, output="Y000")
    _write_program(target, output="Y001")
    _write_comments(current_comments, [["Y000", "旧输出"]])
    _write_comments(target_comments, [["Y001", "新输出"]])
    automation = _RoundtripAutomation(current, current_comments)
    service = ImportService(
        _Finder(), automation, CSVManager(), tmp_path / "backups"
    )

    result = service.import_current_program(
        target,
        comment_csv_path=target_comments,
        synchronize_comments=True,
        verify_roundtrip=True,
        save_project=True,
    )

    assert result.success
    assert automation.saved == 1
    assert Path(result.details["verified_program_path"]).is_file()
    assert Path(result.details["verified_comment_path"]).is_file()
    assert result.details["project_save"]["success"] is True


def test_push_roundtrip_fails_if_gx_did_not_apply_the_program(tmp_path):
    current = tmp_path / "current.csv"
    target = tmp_path / "target.csv"
    comments = tmp_path / "comments.csv"
    _write_program(current, output="Y000")
    _write_program(target, output="Y001")
    _write_comments(comments)
    automation = _RoundtripAutomation(current, comments, apply_import=False)
    service = ImportService(
        _Finder(), automation, CSVManager(), tmp_path / "backups"
    )

    result = service.import_current_program(
        target,
        comment_csv_path=comments,
        synchronize_comments=True,
        verify_roundtrip=True,
    )

    assert not result.success
    assert result.stage == "verify_roundtrip"
    assert "回读程序" in result.message


def test_legacy_program_only_baseline_does_not_absorb_unresolved_conflict(tmp_path):
    base = tmp_path / "base.csv"
    app = tmp_path / "app.csv"
    gx = tmp_path / "gx.csv"
    comments = tmp_path / "comments.csv"
    _write_program(base, output="Y000")
    _write_program(app, output="Y001")
    _write_program(gx, output="Y002")
    _write_comments(comments)
    automation = _Automation(gx, comments)
    service = _service(tmp_path, automation)
    identity = service.baseline_store.project_identity(
        _Finder().session, project_name="Fixture"
    )
    service.baseline_store.save(
        identity,
        program_semantic_sha256=CSVManager().program_semantic_sha256(base),
        program_file_sha256=CSVManager().file_sha256(base),
    )
    baseline_path = service.baseline_store.path_for(identity)
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    for key in list(payload):
        if key.startswith("app_") or key.startswith("gx_") or key == "comments_semantic_sha256":
            payload.pop(key, None)
    baseline_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert service.inspect(app, comments).status == SyncStatus.CONFLICT
    assert service.inspect(app, comments).status == SyncStatus.CONFLICT


def test_same_gx_project_name_cannot_silently_switch_plc_ai_projects(tmp_path):
    gx = tmp_path / "gx.csv"
    first_app = tmp_path / "first.csv"
    second_app = tmp_path / "second.csv"
    comments = tmp_path / "comments.csv"
    _write_program(gx, output="Y000")
    _write_program(first_app, output="Y000")
    _write_program(second_app, output="Y001")
    _write_comments(comments)
    service = _service(tmp_path, _Automation(gx, comments))

    first = service.inspect(
        first_app,
        comments,
        import_context={"project_id": "project-a", "version_id": "v1"},
    )
    second = service.inspect(
        second_app,
        comments,
        import_context={"project_id": "project-b", "version_id": "v1"},
    )

    assert first.status == SyncStatus.SYNCED
    assert second.status == SyncStatus.UNBOUND
    assert second.details["binding_mismatch"] is True
