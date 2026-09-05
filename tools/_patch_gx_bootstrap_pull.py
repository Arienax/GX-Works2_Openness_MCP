from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, text):
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


def method_span(text, name):
    marker = f"    def {name}("
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"method not found: {name}")
    end = text.find("\n    def ", start + len(marker))
    if end < 0:
        raise SystemExit(f"next method not found after: {name}")
    return start, end + 1


# ---------------------------------------------------------------------------
# GX Works2 sync service: factor the safe GX read/export path away from
# three-way comparison so an empty PLC AI project can bootstrap from GX.
# ---------------------------------------------------------------------------
sync_path = "src/gxworks2/sync_service.py"
sync = read(sync_path)
inspect_pos = sync.index("    def inspect(\n")
block_start = sync.index(
    '        self._report(progress, "check_gxworks2", "正在检查GX Works2当前工程")\n',
    inspect_pos,
)
block_end = sync.index(
    '        self._report(progress, "compare", "正在比较项目与GX Works2版本")\n',
    block_start,
)
common_read_block = sync[block_start:block_end]
inspect_replacement = '''        snapshot = self._read_current_snapshot_core(
            progress=progress,
            import_context=import_context,
            project_identity=project_identity,
        )
        if isinstance(snapshot, SyncResult):
            return snapshot
        session = snapshot["session"]
        state = snapshot["state"]
        project_name = snapshot["project_name"]
        identity = snapshot["identity"]
        folder = snapshot["folder"]
        gx_program_path = snapshot["gx_program_path"]
        gx_comment_path = snapshot["gx_comment_path"]
        attempts = snapshot["attempts"]
        recovery_details = snapshot["recovery_details"]
        completed_attempt = snapshot["completed_attempt"]
        gx_save = snapshot["gx_save"]

'''
sync_without_block = sync[:block_start] + inspect_replacement + sync[block_end:]
inspect_pos = sync_without_block.index("    def inspect(\n")
helper = '''    def _read_current_snapshot_core(
        self,
        *,
        progress=None,
        import_context=None,
        project_identity: Optional[str] = None,
    ):
        """Read one coherent MAIN/comments snapshot without requiring a local version."""
        expected_program_name = str(
            (import_context or {}).get("program_name") or "MAIN"
            if isinstance(import_context, Mapping)
            else "MAIN"
        )
        precheck_state = {
            "project_open": None,
            "program_ready": None,
            "program_name": expected_program_name,
        }
''' + common_read_block + '''        return {
            "session": session,
            "state": state,
            "project_name": project_name,
            "identity": identity,
            "folder": folder,
            "gx_program_path": gx_program_path,
            "gx_comment_path": gx_comment_path,
            "attempts": attempts,
            "recovery_details": recovery_details,
            "completed_attempt": completed_attempt,
            "gx_save": gx_save,
        }

    def read_current_snapshot(
        self,
        *,
        progress=None,
        import_context=None,
        project_identity: Optional[str] = None,
    ) -> SyncResult:
        """Export GX MAIN/comments for bootstrap import into an empty AI project."""
        snapshot = self._read_current_snapshot_core(
            progress=progress,
            import_context=import_context,
            project_identity=project_identity,
        )
        if isinstance(snapshot, SyncResult):
            return snapshot
        state = snapshot["state"]
        details = {
            "project_identity": snapshot["identity"],
            "export_folder": str(snapshot["folder"]),
            "gx_save": snapshot["gx_save"],
            "export_attempt": snapshot["completed_attempt"],
            "max_export_attempts": self.max_export_attempts,
            "export_attempts": snapshot["attempts"],
            "recovery": snapshot["recovery_details"],
            "program_name": str(state.get("program_name") or "MAIN"),
            "bootstrap": True,
        }
        return SyncResult(
            True,
            SyncStatus.SYNCED,
            "已读取GX Works2当前MAIN和软元件注释。",
            project_name=snapshot["project_name"],
            exported_program_path=str(snapshot["gx_program_path"]),
            exported_comment_path=str(snapshot["gx_comment_path"]),
            details=details,
            stage="read_snapshot",
            retryable=False,
        )

'''
sync = sync_without_block[:inspect_pos] + helper + sync_without_block[inspect_pos:]
sync = replace_once(
    sync,
    '__all__ = ["GXWorks2SyncService"]',
    '__all__ = ["GXWorks2SyncService"]',
    "sync service final marker",
)
write(sync_path, sync)


# ---------------------------------------------------------------------------
# Public GX API: expose snapshot-only read separately from reconcile.
# ---------------------------------------------------------------------------
api_path = "src/gxworks2/api.py"
api = read(api_path)
api_marker = "\ndef inspect_current_sync(\n"
if api_marker not in api:
    raise SystemExit("api inspect_current_sync marker not found")
api_func = '''

def read_current_snapshot(
    *,
    progress=None,
    import_context=None,
    project_identity=None,
):
    """Read GX Works2 MAIN/comments without requiring a local application version."""
    return _get_sync_service().read_current_snapshot(
        progress=progress,
        import_context=import_context,
        project_identity=project_identity,
    )
'''
api = api.replace(api_marker, api_func + api_marker, 1)
write(api_path, api)

init_path = "src/gxworks2/__init__.py"
init = read(init_path)
init = replace_once(
    init,
    "    inspect_current_sync,\n    record_sync_snapshot,",
    "    inspect_current_sync,\n    read_current_snapshot,\n    record_sync_snapshot,",
    "gx package import",
)
init = replace_once(
    init,
    '    "inspect_current_sync",\n    "record_sync_snapshot",',
    '    "inspect_current_sync",\n    "read_current_snapshot",\n    "record_sync_snapshot",',
    "gx package all",
)
write(init_path, init)


# ---------------------------------------------------------------------------
# Workbench thread + UI: pull requires a project, not an existing ladder.
# ---------------------------------------------------------------------------
main_path = "src/main.py"
main = read(main_path)
class_start = main.index("class GXWorks2SyncInspectThread(QThread):")
class_end = main.index("class GXWorks2SyncErrorDialog(QDialog):", class_start)
new_thread_class = '''class GXWorks2SyncInspectThread(QThread):
    completed = pyqtSignal(object)
    progress_changed = pyqtSignal(str, str)

    def __init__(
        self,
        program_csv_path=None,
        comment_csv_path=None,
        import_context=None,
        *,
        snapshot_only=False,
    ):
        super().__init__()
        self.program_csv_path = str(program_csv_path or "")
        self.comment_csv_path = str(comment_csv_path or "")
        self.import_context = dict(import_context or {})
        self.snapshot_only = bool(snapshot_only)

    def run(self):
        pythoncom = None
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except ImportError:
                pythoncom = None
            if self.snapshot_only:
                from gxworks2 import read_current_snapshot

                result = read_current_snapshot(
                    progress=self.progress_changed.emit,
                    import_context=self.import_context,
                )
            else:
                from gxworks2 import inspect_current_sync

                result = inspect_current_sync(
                    self.program_csv_path,
                    self.comment_csv_path,
                    progress=self.progress_changed.emit,
                    import_context=self.import_context,
                )
        except Exception as error:
            from gxworks2.diagnostics import describe_exception, exception_details
            from gxworks2.models import GXSyncErrorCode, SyncResult, SyncStatus

            result = SyncResult(
                False,
                SyncStatus.ERROR,
                "GX Works2读取检查异常：" + describe_exception(error),
                GXSyncErrorCode.GX_UNEXPECTED_ERROR,
                details={
                    "category": "precheck",
                    "stage": "unexpected",
                    "error_code": GXSyncErrorCode.GX_UNEXPECTED_ERROR.value,
                    "retryable": False,
                    "suggestion": "请查看技术详情；若问题持续出现，请保留详情用于排查。",
                    "gx_running": None,
                    "gx_process_id": None,
                    "gx_window_handle": None,
                    "project_open": None,
                    "program_ready": None,
                    "program_name": str(
                        self.import_context.get("program_name") or "MAIN"
                    ),
                    "attempt": 1,
                    "max_attempts": 1,
                    "attempts": [],
                    "program_path": self.program_csv_path,
                    "comment_path": self.comment_csv_path,
                    "bootstrap": self.snapshot_only,
                    **exception_details(error),
                },
                stage="unexpected",
                retryable=False,
            )
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
        self.completed.emit(result)


'''
main = main[:class_start] + new_thread_class + main[class_end:]

# Independent enablement: pull works for a selected project even with no version.
start, end = method_span(main, "_update_gx_sync_button_enabled")
main = main[:start] + '''    def _update_gx_sync_button_enabled(self):
        if not hasattr(self, "gxworks2_import_button"):
            return
        project_ready = bool(self.current_project_id)
        version = (
            self.store.get_version(self.current_project_id, self.current_version_id)
            if self.current_project_id and self.current_version_id
            else None
        )
        ladder_ready = bool(version and version.get("target_mode") == "ladder")
        available = not self._gx_sync_busy()
        self.gxworks2_import_button.setEnabled(ladder_ready and available)
        self.gxworks2_pull_button.setEnabled(project_ready and available)
        self.gxworks2_advanced_button.setEnabled(ladder_ready and available)

''' + main[end:]

# Add a pull request builder that can bootstrap with project-only context.
publish_marker = "    def _publish_current_version_to_gxworks2(self):\n"
if publish_marker not in main:
    raise SystemExit("publish method marker not found")
pull_request_method = '''    def _gx_pull_request(self):
        project_id = self.current_project_id
        if not project_id:
            raise ValueError("请先选择一个项目。")
        project = self.store.get_project(project_id)
        if not project:
            raise ValueError("当前项目不存在。")
        version = (
            self.store.get_version(project_id, self.current_version_id)
            if self.current_version_id
            else None
        )
        if version and version.get("target_mode") == "ladder":
            request = self._gx_sync_request_for_version(
                project_id=project_id,
                version_id=self.current_version_id,
            )
            request["bootstrap"] = False
            return request
        return {
            "project_id": project_id,
            "version_id": None,
            "version": None,
            "program_path": None,
            "comment_path": None,
            "context": {
                "project_id": project_id,
                "version_id": None,
                "revision": None,
                "program_name": "MAIN",
                "ir_schema_version": None,
                "ir_sha256": None,
                "ladder_sha256": None,
            },
            "bootstrap": True,
        }

'''
main = main.replace(publish_marker, pull_request_method + publish_marker, 1)

# Pull uses project-only request for empty projects; reconcile keeps strict local version request.
start, end = method_span(main, "_start_gxworks2_inspection")
main = main[:start] + '''    def _start_gxworks2_inspection(self, intent):
        if self._gx_sync_busy():
            self.statusBar().showMessage("GX Works2操作正在运行。", 3000)
            return
        try:
            request = (
                self._gx_pull_request()
                if intent == "pull"
                else self._gx_sync_request_for_version()
            )
        except Exception as error:
            title = "无法读取" if intent == "pull" else "无法高级同步"
            QMessageBox.warning(self, title, naturalize_display_text(error))
            return
        self._gx_sync_intent = str(intent or "reconcile")
        self._pending_gx_sync_result = None
        self._gx_sync_request = request
        detail = (
            "正在读取GX Works2当前MAIN和软元件注释"
            if self._gx_sync_intent == "pull"
            else "正在比较项目与GX Works2"
        )
        self._set_gx_sync_status("checking", detail)
        self._set_gx_action_buttons_enabled(False)
        active_button = (
            self.gxworks2_pull_button
            if self._gx_sync_intent == "pull"
            else self.gxworks2_advanced_button
        )
        active_button.setText("正在读取…" if self._gx_sync_intent == "pull" else "正在检查…")
        self.statusBar().showMessage("正在读取GX Works2当前MAIN和软元件注释…")
        thread = GXWorks2SyncInspectThread(
            request.get("program_path"),
            request.get("comment_path"),
            import_context=request["context"],
            snapshot_only=bool(request.get("bootstrap")),
        )
        thread.progress_changed.connect(self._gxworks2_sync_progress)
        thread.completed.connect(self._gxworks2_sync_inspected)
        self._retain_worker_thread(
            "_gxworks2_sync_thread",
            thread,
            on_finished=self._gxworks2_sync_thread_finished,
        )
        thread.start()

''' + main[end:]

# A successful bootstrap snapshot is always materialized as the first ladder version.
main = replace_once(
    main,
    '''        status = result.status.value
        intent = getattr(self, "_gx_sync_intent", "reconcile")
        if intent == "pull":
''',
    '''        status = result.status.value
        intent = getattr(self, "_gx_sync_intent", "reconcile")
        if intent == "pull" and request.get("bootstrap"):
            self._start_gxworks2_pull(result, request)
            return
        if intent == "pull":
''',
    "bootstrap pull dispatch",
)

# Make the pull materializer tolerate request[version] == None.
start, end = method_span(main, "_start_gxworks2_pull")
pull_method = main[start:end]
pull_method = replace_once(
    pull_method,
    '''        project = self.store.get_project(request["project_id"])
        if not project:
            return
''',
    '''        project = self.store.get_project(request["project_id"])
        if not project:
            return
        source_version = request.get("version") or {}
        result_details = dict(getattr(result, "details", {}) or {})
''',
    "pull source version",
)
pull_method = pull_method.replace(
    'request["version"].get("plc_model")',
    'source_version.get("plc_model")',
)
pull_method = pull_method.replace(
    'request["version"].get("program_name") or "MAIN"',
    'source_version.get("program_name") or result_details.get("program_name") or "MAIN"',
)
main = main[:start] + pull_method + main[end:]

# Bootstrap gets a true root-version lineage and explicit origin metadata.
start, end = method_span(main, "_gxworks2_pull_completed")
completed_method = main[start:end]
completed_method = replace_once(
    completed_method,
    '''        metadata = dict(metadata or {})
        metadata.update(
            {
                "summary": "从GX Works2同步的人工修改",
                "parent_version_id": pending["request"]["version_id"],
                "confirmed_spec_snapshot": None,
                "confirmed_spec_hash": None,
            }
        )
''',
    '''        metadata = dict(metadata or {})
        bootstrap = bool(pending["request"].get("bootstrap"))
        metadata.update(
            {
                "summary": (
                    "从GX Works2导入的初始程序"
                    if bootstrap
                    else "从GX Works2同步的人工修改"
                ),
                "parent_version_id": (
                    None if bootstrap else pending["request"]["version_id"]
                ),
                "confirmed_spec_snapshot": None,
                "confirmed_spec_hash": None,
                "import_origin": (
                    "gxworks2_bootstrap" if bootstrap else "gxworks2_pull"
                ),
            }
        )
''',
    "pull completion metadata",
)
completed_method = replace_once(
    completed_method,
    '''            f"已从GX Works2回读人工修改并创建{version_display_name(version_id)}。",
''',
    '''            (
                f"已从GX Works2导入初始程序并创建{version_display_name(version_id)}。"
                if bootstrap
                else f"已从GX Works2回读人工修改并创建{version_display_name(version_id)}。"
            ),
''',
    "pull completion message",
)
completed_method = replace_once(
    completed_method,
    '''                "parent_version_id": pending["request"]["version_id"],
''',
    '''                "parent_version_id": (
                    None if bootstrap else pending["request"]["version_id"]
                ),
''',
    "pull message lineage",
)
main = main[:start] + completed_method + main[end:]

# Empty-artifact state must still leave project-level pull enabled.
start, end = method_span(main, "_clear_artifacts")
clear_method = main[start:end]
clear_method = replace_once(
    clear_method,
    "        self._set_gx_action_buttons_enabled(False)\n",
    "        self._update_gx_sync_button_enabled()\n",
    "clear artifacts gx state",
)
main = main[:start] + clear_method + main[end:]
write(main_path, main)


# ---------------------------------------------------------------------------
# Focused regressions.
# ---------------------------------------------------------------------------
ui_test_path = "tests/test_gxworks2_simple_bridge_ui.py"
ui_tests = '''from pathlib import Path


def test_simple_gx_bridge_actions_are_primary_ui():
    text = Path("src/main.py").read_text(encoding="utf-8")
    assert 'QPushButton("写入 GX Works2")' in text
    assert 'QPushButton("读取 GX Works2")' in text
    assert 'QPushButton("高级同步")' in text
    assert "def _publish_current_version_to_gxworks2" in text
    assert "def _pull_current_version_from_gxworks2" in text
    assert 'self._start_gxworks2_inspection("pull")' in text
    assert 'self._start_gxworks2_inspection("reconcile")' in text


def test_empty_project_pull_has_bootstrap_request():
    text = Path("src/main.py").read_text(encoding="utf-8")
    assert "def _gx_pull_request(self):" in text
    assert '"bootstrap": True' in text
    assert 'snapshot_only=bool(request.get("bootstrap"))' in text
    assert 'if intent == "pull" and request.get("bootstrap"):' in text
    assert "self._start_gxworks2_pull(result, request)" in text


def test_pull_button_only_requires_selected_project():
    text = Path("src/main.py").read_text(encoding="utf-8")
    state = text.split("def _update_gx_sync_button_enabled", 1)[1].split("\n    def ", 1)[0]
    assert "project_ready = bool(self.current_project_id)" in state
    assert "ladder_ready = bool(version" in state
    assert "self.gxworks2_pull_button.setEnabled(project_ready and available)" in state
    assert "self.gxworks2_import_button.setEnabled(ladder_ready and available)" in state
    assert "self.gxworks2_advanced_button.setEnabled(ladder_ready and available)" in state


def test_bootstrap_pull_creates_root_version():
    text = Path("src/main.py").read_text(encoding="utf-8")
    completed = text.split("def _gxworks2_pull_completed", 1)[1].split("\n    def ", 1)[0]
    assert '"从GX Works2导入的初始程序"' in completed
    assert '"gxworks2_bootstrap"' in completed
    assert "None if bootstrap" in completed


def test_direct_pull_does_not_force_three_way_choice():
    text = Path("src/main.py").read_text(encoding="utf-8")
    assert 'if intent == "pull":' in text
    assert "self._start_gxworks2_pull(result, request)" in text


def test_external_modification_points_to_advanced_sync():
    text = Path("src/gxworks2/import_service.py").read_text(encoding="utf-8")
    assert '请使用“高级同步”选择保留哪一方' in text


def test_snapshot_only_thread_uses_public_read_api():
    text = Path("src/main.py").read_text(encoding="utf-8")
    thread = text.split("class GXWorks2SyncInspectThread", 1)[1].split(
        "class GXWorks2SyncErrorDialog", 1
    )[0]
    assert "snapshot_only=False" in thread
    assert "from gxworks2 import read_current_snapshot" in thread
    assert "result = read_current_snapshot(" in thread
'''
write(ui_test_path, ui_tests)

sync_test_path = "tests/test_gxworks2_sync.py"
sync_tests = read(sync_test_path)
if "def test_read_current_snapshot_needs_no_local_version" not in sync_tests:
    sync_tests += '''\n\ndef test_read_current_snapshot_needs_no_local_version(tmp_path):
    gx_program = tmp_path / "gx-bootstrap.csv"
    gx_comments = tmp_path / "gx-bootstrap-comments.csv"
    _write_program(gx_program, output="Y007")
    _write_comments(gx_comments, [["X000", "启动"], ["Y007", "已有输出"]])
    service = _service(tmp_path, _Automation(gx_program, gx_comments))

    result = service.read_current_snapshot(
        import_context={"project_id": "empty-project", "program_name": "MAIN"}
    )

    assert result.success
    assert result.details["bootstrap"] is True
    assert result.details["project_identity"]
    assert Path(result.exported_program_path).is_file()
    assert Path(result.exported_comment_path).is_file()
    assert CSVManager().program_semantic_sha256(result.exported_program_path) == (
        CSVManager().program_semantic_sha256(gx_program)
    )
'''
write(sync_test_path, sync_tests)
