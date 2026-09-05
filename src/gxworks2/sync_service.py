"""Three-way synchronization between one application version and GX Works2."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Mapping, Optional

from .baseline_store import BaselineStoreError, ImportBaselineStore
from .csv_importer import diff_gxworks2_programs
from .models import ImportErrorCode, SyncResult, SyncStatus
from .import_service import _unsaved_project_identity


class GXWorks2SyncService:
    def __init__(
        self,
        finder,
        automation,
        csv_manager,
        backup_root,
        baseline_store=None,
        export_validation_timeout=2.5,
        export_validation_poll_interval=0.05,
    ):
        self.finder = finder
        self.automation = automation
        self.csv_manager = csv_manager
        self.backup_root = Path(backup_root)
        self.baseline_store = baseline_store or ImportBaselineStore(self.backup_root)
        self.export_validation_timeout = max(0.0, float(export_validation_timeout))
        self.export_validation_poll_interval = max(
            0.01, float(export_validation_poll_interval)
        )

    def _wait_for_valid_export(self, path, validator):
        deadline = time.monotonic() + self.export_validation_timeout
        result = validator(path)
        while not result.valid and time.monotonic() < deadline:
            time.sleep(self.export_validation_poll_interval)
            result = validator(path)
        return result

    @staticmethod
    def _report(progress, stage, message):
        if progress is not None:
            progress(stage, message)

    @staticmethod
    def _error(message, code, *, project_name="", details=None):
        return SyncResult(
            False,
            SyncStatus.ERROR,
            message,
            error_code=code,
            project_name=project_name,
            details=dict(details or {}),
        )

    def _save_snapshot(
        self,
        identity,
        *,
        app_program_path,
        app_comment_path,
        gx_program_path,
        gx_comment_path,
        import_context=None,
    ):
        app_program_hash = self.csv_manager.program_semantic_sha256(app_program_path)
        gx_program_hash = self.csv_manager.program_semantic_sha256(gx_program_path)
        app_comment_hash = self.csv_manager.comments_semantic_sha256(app_comment_path)
        gx_comment_hash = self.csv_manager.comments_semantic_sha256(gx_comment_path)
        return self.baseline_store.save(
            identity,
            program_semantic_sha256=gx_program_hash,
            program_file_sha256=self.csv_manager.file_sha256(app_program_path),
            app_program_semantic_sha256=app_program_hash,
            gx_program_semantic_sha256=gx_program_hash,
            comments_semantic_sha256=gx_comment_hash,
            app_comment_semantic_sha256=app_comment_hash,
            gx_comment_semantic_sha256=gx_comment_hash,
            import_context=import_context,
        )

    def record_snapshot(
        self,
        identity: Mapping[str, Any],
        *,
        app_program_path,
        app_comment_path,
        gx_program_path,
        gx_comment_path,
        import_context=None,
    ):
        return self._save_snapshot(
            dict(identity),
            app_program_path=app_program_path,
            app_comment_path=app_comment_path,
            gx_program_path=gx_program_path,
            gx_comment_path=gx_comment_path,
            import_context=import_context,
        )

    def inspect(
        self,
        app_program_path,
        app_comment_path,
        *,
        progress=None,
        import_context=None,
        project_identity: Optional[str] = None,
    ) -> SyncResult:
        app_program_path = Path(app_program_path).expanduser().resolve()
        app_comment_path = Path(app_comment_path).expanduser().resolve()
        self._report(progress, "validate", "正在校验当前项目版本")
        program_validation = self.csv_manager.validate(app_program_path)
        comment_validation = self.csv_manager.validate_comments(app_comment_path)
        errors = list(program_validation.errors) + list(comment_validation.errors)
        if errors:
            return self._error(
                "当前项目版本无法同步：" + "；".join(errors),
                ImportErrorCode.CSV_INVALID,
            )

        self._report(progress, "check_project", "正在检查GX Works2当前工程")
        session = self.finder.find_running()
        if session is None:
            return self._error(
                "GX Works2未运行，请先打开目标工程和MAIN程序。",
                ImportErrorCode.GXWORKS2_NOT_RUNNING,
            )
        if session.project_state_known and not session.project_open:
            return self._error(
                "GX Works2尚未新建或打开工程。",
                ImportErrorCode.TARGET_PROJECT_NOT_OPEN,
            )
        state = self.automation.inspect_project(session)
        project_name = state.get("project_name") or session.project_name or "GXWorks2"
        if not state.get("automation_available", True):
            return self._error(
                state.get("message", "GX Works2自动化驱动不可用。"),
                ImportErrorCode.AUTOMATION_UNAVAILABLE,
                project_name=project_name,
            )
        if not state.get("project_open"):
            return self._error(
                "GX Works2中没有已打开的目标工程。",
                ImportErrorCode.TARGET_PROJECT_NOT_OPEN,
                project_name=project_name,
            )
        if not state.get("program_ready"):
            return self._error(
                "GX Works2当前MAIN程序不可读取，请先打开MAIN。",
                ImportErrorCode.TARGET_PROGRAM_NOT_READY,
                project_name=project_name,
            )

        effective_project_identity = project_identity or _unsaved_project_identity(
            session,
            project_name,
            import_context=import_context,
        )
        identity = self.baseline_store.project_identity(
            session,
            project_name=project_name,
            project_identity=effective_project_identity,
        )

        self._report(progress, "export_program", "正在从GX Works2读取当前MAIN")
        try:
            folder = self.csv_manager.backup_folder(self.backup_root, project_name)
            gx_program_path = folder / "program_from_gxworks2.csv"
            gx_comment_path = folder / "comments_from_gxworks2.csv"
            self.automation.export_current_program(session, gx_program_path)
            exported_program = self._wait_for_valid_export(
                gx_program_path, self.csv_manager.validate
            )
            if not exported_program.valid:
                raise RuntimeError("；".join(exported_program.errors))
            self._report(progress, "export_comments", "正在从GX Works2读取软元件注释")
            self.automation.export_current_comments(session, gx_comment_path)
            exported_comments = self._wait_for_valid_export(
                gx_comment_path,
                lambda path: self.csv_manager.validate_comments(
                    path, require_crlf=False
                ),
            )
            if not exported_comments.valid:
                raise RuntimeError("；".join(exported_comments.errors))
            self.csv_manager.write_checksum_manifest(folder)
        except Exception as error:
            return self._error(
                f"无法从GX Works2读取当前程序：{error}",
                ImportErrorCode.BACKUP_FAILED,
                project_name=project_name,
                details={"project_identity": identity},
            )

        save_method = getattr(self.automation, "save_project", None)
        if callable(save_method):
            try:
                gx_save = dict(save_method(session) or {})
            except Exception as error:
                gx_save = {
                    "success": False,
                    "save_required": True,
                    "message": f"无法自动保存GX Works2工程：{error}",
                }
        else:
            gx_save = {
                "success": False,
                "save_required": True,
                "message": "请在GX Works2中保存当前工程。",
            }

        self._report(progress, "compare", "正在比较项目与GX Works2版本")
        try:
            app_program_hash = self.csv_manager.program_semantic_sha256(app_program_path)
            gx_program_hash = self.csv_manager.program_semantic_sha256(gx_program_path)
            app_comment_hash = self.csv_manager.comments_semantic_sha256(app_comment_path)
            gx_comment_hash = self.csv_manager.comments_semantic_sha256(gx_comment_path)
            baseline = self.baseline_store.load(identity)
            difference = diff_gxworks2_programs(app_program_path, gx_program_path)
        except (OSError, ValueError, BaselineStoreError) as error:
            return self._error(
                f"无法核对同步基线：{error}",
                ImportErrorCode.BASELINE_READ_FAILED,
                project_name=project_name,
                details={"project_identity": identity},
            )

        hashes = {
            "app_program_semantic_sha256": app_program_hash,
            "gx_program_semantic_sha256": gx_program_hash,
            "app_comment_semantic_sha256": app_comment_hash,
            "gx_comment_semantic_sha256": gx_comment_hash,
        }
        details = {
            "project_identity": identity,
            "baseline_found": baseline is not None,
            "baseline": baseline or {},
            "hashes": hashes,
            "diff": difference,
            "export_folder": str(folder),
            "gx_save": gx_save,
        }

        program_equal = app_program_hash == gx_program_hash
        comments_equal = app_comment_hash == gx_comment_hash
        if baseline is None:
            if program_equal and comments_equal:
                self._save_snapshot(
                    identity,
                    app_program_path=app_program_path,
                    app_comment_path=app_comment_path,
                    gx_program_path=gx_program_path,
                    gx_comment_path=gx_comment_path,
                    import_context=import_context,
                )
                return SyncResult(
                    True,
                    SyncStatus.SYNCED,
                    "项目与GX Works2内容一致，已建立同步关系。",
                    project_name=project_name,
                    exported_program_path=str(gx_program_path),
                    exported_comment_path=str(gx_comment_path),
                    details=details,
                )
            return SyncResult(
                True,
                SyncStatus.UNBOUND,
                "这是首次同步，项目与GX Works2内容不同，请选择保留哪一方。",
                project_name=project_name,
                exported_program_path=str(gx_program_path),
                exported_comment_path=str(gx_comment_path),
                details=details,
            )

        previous_project_id = str(
            (baseline.get("import_context") or {}).get("project_id") or ""
        )
        current_project_id = str(
            (import_context or {}).get("project_id") or ""
            if isinstance(import_context, Mapping)
            else ""
        )
        binding_mismatch = bool(
            previous_project_id
            and current_project_id
            and previous_project_id != current_project_id
        )
        details["binding_mismatch"] = binding_mismatch
        details["previous_project_id"] = previous_project_id
        if binding_mismatch:
            if program_equal and comments_equal:
                self._save_snapshot(
                    identity,
                    app_program_path=app_program_path,
                    app_comment_path=app_comment_path,
                    gx_program_path=gx_program_path,
                    gx_comment_path=gx_comment_path,
                    import_context=import_context,
                )
                return SyncResult(
                    True,
                    SyncStatus.SYNCED,
                    "当前项目与GX Works2内容一致，已更新工程绑定。",
                    project_name=project_name,
                    exported_program_path=str(gx_program_path),
                    exported_comment_path=str(gx_comment_path),
                    details=details,
                )
            return SyncResult(
                True,
                SyncStatus.UNBOUND,
                "当前GX Works2工程上次绑定到另一个项目，请选择本次以哪一方为准。",
                project_name=project_name,
                exported_program_path=str(gx_program_path),
                exported_comment_path=str(gx_comment_path),
                details=details,
            )

        base_app_program = baseline.get("app_program_semantic_sha256")
        base_gx_program = baseline.get("gx_program_semantic_sha256")
        base_app_comment = baseline.get("app_comment_semantic_sha256") or ""
        base_gx_comment = baseline.get("gx_comment_semantic_sha256") or ""
        comment_base_known = bool(base_app_comment and base_gx_comment)
        local_changed = app_program_hash != base_app_program
        gx_changed = gx_program_hash != base_gx_program
        if comment_base_known:
            local_changed = local_changed or app_comment_hash != base_app_comment
            gx_changed = gx_changed or gx_comment_hash != base_gx_comment
        elif comments_equal:
            # A v1 baseline did not track comments. Equal current mappings do
            # not affect change classification.  Persist the upgraded base
            # only after the program sides are also known to be equivalent;
            # otherwise an unresolved conflict would accidentally become the
            # next common base.
            pass
        else:
            local_changed = True
            gx_changed = True

        details["local_changed"] = local_changed
        details["gx_changed"] = gx_changed
        if program_equal and comments_equal:
            self._save_snapshot(
                identity,
                app_program_path=app_program_path,
                app_comment_path=app_comment_path,
                gx_program_path=gx_program_path,
                gx_comment_path=gx_comment_path,
                import_context=import_context,
            )
            status = SyncStatus.SYNCED
            message = "项目与GX Works2内容一致。"
        elif local_changed and not gx_changed:
            status = SyncStatus.NEEDS_PUSH
            message = "项目版本有修改，正在准备同步到GX Works2。"
        elif gx_changed and not local_changed:
            status = SyncStatus.NEEDS_PULL
            message = "GX Works2中有人工修改，正在回读为新的项目版本。"
        else:
            status = SyncStatus.CONFLICT
            message = "项目与GX Works2都已修改，必须先选择保留哪一方。"
        return SyncResult(
            True,
            status,
            message,
            project_name=project_name,
            exported_program_path=str(gx_program_path),
            exported_comment_path=str(gx_comment_path),
            details=details,
        )


__all__ = ["GXWorks2SyncService"]
