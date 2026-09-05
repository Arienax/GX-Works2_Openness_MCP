from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch anchor not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


main_path = "src/main.py"
import_path = "src/gxworks2/import_service.py"

replace_once(
    main_path,
    '''        self._gx_sync_request = None
        self._gx_sync_retry_pending = False
        self._pending_gx_pull = None
''',
    '''        self._gx_sync_request = None
        self._gx_sync_retry_pending = False
        self._gx_sync_intent = "idle"
        self._pending_gx_pull = None
''',
)

replace_once(
    main_path,
    '''        self.gxworks2_sync_status.setToolTip(
            "显示当前项目版本与GX Works2中MAIN程序、软元件注释的同步状态"
        )
        self.gxworks2_import_button = QPushButton("同步 GX Works2")
        self.gxworks2_import_button.setObjectName("PrimaryButton")
        set_codicon(
            self.gxworks2_import_button,
            "sync",
            "同步 GX Works2",
            10,
        )
        self.gxworks2_import_button.setEnabled(False)
        self.gxworks2_import_button.clicked.connect(
            self._sync_current_version_with_gxworks2
        )
''',
    '''        self.gxworks2_sync_status.setToolTip(
            "显示当前项目版本与GX Works2中MAIN程序、软元件注释的同步状态"
        )
        self.gxworks2_import_button = QPushButton("写入 GX Works2")
        self.gxworks2_import_button.setObjectName("PrimaryButton")
        set_codicon(
            self.gxworks2_import_button,
            "export",
            "写入 GX Works2",
            10,
        )
        self.gxworks2_import_button.setEnabled(False)
        self.gxworks2_import_button.setToolTip(
            "将当前已验证版本写入GX Works2；写入前仍会自动备份并检查外部修改"
        )
        self.gxworks2_import_button.clicked.connect(
            self._publish_current_version_to_gxworks2
        )
        self.gxworks2_pull_button = QPushButton("读取 GX Works2")
        set_codicon(
            self.gxworks2_pull_button,
            "sync",
            "读取 GX Works2",
            10,
        )
        self.gxworks2_pull_button.setEnabled(False)
        self.gxworks2_pull_button.setToolTip(
            "读取GX Works2当前MAIN和注释；有差异时创建新的本地版本，不覆盖现有版本"
        )
        self.gxworks2_pull_button.clicked.connect(
            self._pull_current_version_from_gxworks2
        )
        self.gxworks2_advanced_button = QPushButton("高级同步")
        self.gxworks2_advanced_button.setEnabled(False)
        self.gxworks2_advanced_button.setToolTip(
            "比较双方与同步基线，仅在首次绑定、冲突或需要决定保留哪一方时使用"
        )
        self.gxworks2_advanced_button.clicked.connect(
            self._sync_current_version_with_gxworks2
        )
''',
)

replace_once(
    main_path,
    '''        actions.addWidget(self.gxworks2_sync_status)
        actions.addWidget(self.gxworks2_import_button)
        actions.addWidget(self.simulator_test_button)
''',
    '''        actions.addWidget(self.gxworks2_sync_status)
        actions.addWidget(self.gxworks2_import_button)
        actions.addWidget(self.gxworks2_pull_button)
        actions.addWidget(self.gxworks2_advanced_button)
        actions.addWidget(self.simulator_test_button)
''',
)

replace_once(
    main_path,
    '"点击“同步 GX Works2”检查当前版本" if mode == "ladder" else "ST版本不使用GX Works2梯形图同步"',
    '"可直接写入或读取GX Works2；需要比较双方改动时使用“高级同步”" if mode == "ladder" else "ST版本不使用GX Works2梯形图同步"',
)

replace_once(
    main_path,
    '''    def _update_gx_sync_button_enabled(self):
        if not hasattr(self, "gxworks2_import_button"):
            return
        version = (
            self.store.get_version(self.current_project_id, self.current_version_id)
            if self.current_project_id and self.current_version_id
            else None
        )
        self.gxworks2_import_button.setEnabled(
            bool(
                version
                and version.get("target_mode") == "ladder"
                and not self._gx_sync_busy()
            )
        )
''',
    '''    def _gx_action_buttons(self):
        return tuple(
            button
            for button in (
                getattr(self, "gxworks2_import_button", None),
                getattr(self, "gxworks2_pull_button", None),
                getattr(self, "gxworks2_advanced_button", None),
            )
            if button is not None
        )

    def _set_gx_action_buttons_enabled(self, enabled):
        for button in self._gx_action_buttons():
            button.setEnabled(bool(enabled))

    def _reset_gx_action_buttons(self):
        if hasattr(self, "gxworks2_import_button"):
            set_codicon(
                self.gxworks2_import_button,
                "export",
                "写入 GX Works2",
                10,
            )
        if hasattr(self, "gxworks2_pull_button"):
            set_codicon(
                self.gxworks2_pull_button,
                "sync",
                "读取 GX Works2",
                10,
            )
        if hasattr(self, "gxworks2_advanced_button"):
            self.gxworks2_advanced_button.setText("高级同步")

    def _update_gx_sync_button_enabled(self):
        if not hasattr(self, "gxworks2_import_button"):
            return
        version = (
            self.store.get_version(self.current_project_id, self.current_version_id)
            if self.current_project_id and self.current_version_id
            else None
        )
        self._set_gx_action_buttons_enabled(
            bool(
                version
                and version.get("target_mode") == "ladder"
                and not self._gx_sync_busy()
            )
        )
''',
)

replace_once(
    main_path,
    '''    def _sync_current_version_with_gxworks2(self):
        if self._gx_sync_busy():
            self.statusBar().showMessage("GX Works2同步任务正在运行。", 3000)
            return
        try:
            request = self._gx_sync_request_for_version()
        except Exception as error:
            QMessageBox.warning(
                self,
                "无法同步",
                naturalize_display_text(error),
            )
            return
        self._pending_gx_sync_result = None
        self._gx_sync_request = request
        self._set_gx_sync_status("checking", "正在比较项目与GX Works2")
        self.gxworks2_import_button.setEnabled(False)
        self.gxworks2_import_button.setText("正在检查…")
        self.statusBar().showMessage("正在读取GX Works2当前MAIN和软元件注释…")
        thread = GXWorks2SyncInspectThread(
            request["program_path"],
            request["comment_path"],
            import_context=request["context"],
        )
        thread.progress_changed.connect(self._gxworks2_sync_progress)
        thread.completed.connect(self._gxworks2_sync_inspected)
        self._retain_worker_thread(
            "_gxworks2_sync_thread",
            thread,
            on_finished=self._gxworks2_sync_thread_finished,
        )
        thread.start()
''',
    '''    def _publish_current_version_to_gxworks2(self):
        if self._gx_sync_busy():
            self.statusBar().showMessage("GX Works2操作正在运行。", 3000)
            return
        try:
            request = self._gx_sync_request_for_version()
        except Exception as error:
            QMessageBox.warning(self, "无法写入", naturalize_display_text(error))
            return
        self._gx_sync_intent = "publish"
        self._import_current_version_to_gxworks2(
            project_id=request["project_id"],
            version_id=request["version_id"],
        )

    def _pull_current_version_from_gxworks2(self):
        self._start_gxworks2_inspection("pull")

    def _sync_current_version_with_gxworks2(self):
        self._start_gxworks2_inspection("reconcile")

    def _start_gxworks2_inspection(self, intent):
        if self._gx_sync_busy():
            self.statusBar().showMessage("GX Works2操作正在运行。", 3000)
            return
        try:
            request = self._gx_sync_request_for_version()
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
            request["program_path"],
            request["comment_path"],
            import_context=request["context"],
        )
        thread.progress_changed.connect(self._gxworks2_sync_progress)
        thread.completed.connect(self._gxworks2_sync_inspected)
        self._retain_worker_thread(
            "_gxworks2_sync_thread",
            thread,
            on_finished=self._gxworks2_sync_thread_finished,
        )
        thread.start()
''',
)

replace_once(
    main_path,
    '''        self.gxworks2_import_button.setText(labels.get(stage, "正在同步…"))
        self.statusBar().showMessage(naturalize_display_text(message))
''',
    '''        intent = getattr(self, "_gx_sync_intent", "reconcile")
        button = (
            getattr(self, "gxworks2_pull_button", None)
            if intent == "pull"
            else getattr(self, "gxworks2_advanced_button", None)
        )
        if button is not None:
            button.setText(labels.get(stage, "处理中…"))
        self.statusBar().showMessage(naturalize_display_text(message))
''',
)

replace_once(
    main_path,
    '''        status = result.status.value
        if status == "synced":
''',
    '''        status = result.status.value
        intent = getattr(self, "_gx_sync_intent", "reconcile")
        if intent == "pull":
            if status == "synced":
                gx_save = (result.details or {}).get("gx_save", {}) or {}
                self._set_gx_sync_status(
                    "unsaved" if gx_save and not gx_save.get("success") else "synced",
                    gx_save.get("message") or "GX Works2内容与当前版本一致",
                )
                self.activity_panel.set_status("GX Works2内容与当前版本一致，无需创建新版本")
                self.statusBar().showMessage("GX Works2内容与当前版本一致，无需回读。", 6000)
            else:
                self._start_gxworks2_pull(result, request)
            return
        if status == "synced":
''',
)

replace_once(
    main_path,
    '''    def _gxworks2_sync_thread_finished(self):
        if self._gx_sync_retry_pending:
            self.gxworks2_import_button.setEnabled(False)
            self.gxworks2_import_button.setText("准备重试…")
            QTimer.singleShot(0, self._run_pending_gx_sync_retry)
            return
        self.gxworks2_import_button.setText("同步 GX Works2")
        self._update_gx_sync_button_enabled()

    def _run_pending_gx_sync_retry(self):
        if not self._gx_sync_retry_pending or self._gx_sync_busy():
            return
        self._gx_sync_retry_pending = False
        self._sync_current_version_with_gxworks2()
''',
    '''    def _gxworks2_sync_thread_finished(self):
        if self._gx_sync_retry_pending:
            self._set_gx_action_buttons_enabled(False)
            active_button = (
                self.gxworks2_pull_button
                if getattr(self, "_gx_sync_intent", "reconcile") == "pull"
                else self.gxworks2_advanced_button
            )
            active_button.setText("准备重试…")
            QTimer.singleShot(0, self._run_pending_gx_sync_retry)
            return
        self._reset_gx_action_buttons()
        self._update_gx_sync_button_enabled()

    def _run_pending_gx_sync_retry(self):
        if not self._gx_sync_retry_pending or self._gx_sync_busy():
            return
        self._gx_sync_retry_pending = False
        if getattr(self, "_gx_sync_intent", "reconcile") == "pull":
            self._pull_current_version_from_gxworks2()
        else:
            self._sync_current_version_with_gxworks2()
''',
)

replace_once(
    main_path,
    '''        self._set_gx_sync_status("pulling", "正在把GX Works2人工修改保存为新版本")
        self.gxworks2_import_button.setEnabled(False)
        self.gxworks2_import_button.setText("正在回读…")
        self.statusBar().showMessage("正在解析GX Works2程序并创建新的项目版本…")
''',
    '''        self._set_gx_sync_status("pulling", "正在把GX Works2人工修改保存为新版本")
        self._set_gx_action_buttons_enabled(False)
        self.gxworks2_pull_button.setText("正在读取…")
        self.statusBar().showMessage("正在解析GX Works2程序并创建新的项目版本…")
''',
)

replace_once(
    main_path,
    '''    def _gxworks2_pull_thread_finished(self):
        self._pending_gx_pull = None
        self.gxworks2_import_button.setText("同步 GX Works2")
        self._update_gx_sync_button_enabled()
''',
    '''    def _gxworks2_pull_thread_finished(self):
        self._pending_gx_pull = None
        self._gx_sync_intent = "idle"
        self._reset_gx_action_buttons()
        self._update_gx_sync_button_enabled()
''',
)

replace_once(
    main_path,
    '''        self.gxworks2_import_button.setEnabled(False)
        self.gxworks2_import_button.setText("正在同步…")
        self._set_gx_sync_status("pushing", "正在备份并写入GX Works2")
''',
    '''        self._set_gx_action_buttons_enabled(False)
        self.gxworks2_import_button.setText("正在写入…")
        self._set_gx_sync_status("pushing", "正在备份并写入GX Works2")
''',
)

replace_once(
    main_path,
    '''    def _gxworks2_import_finished(self, result):
        self.gxworks2_import_button.setText("同步 GX Works2")
        display_message = naturalize_display_text(result.message)
''',
    '''    def _gxworks2_import_finished(self, result):
        self._reset_gx_action_buttons()
        display_message = naturalize_display_text(result.message)
''',
)

replace_once(
    main_path,
    '"同步完成（需要核对）",',
    '"写入完成（需要核对）",',
)
replace_once(
    main_path,
    '"GX Works2同步未完成",\n            display_message + backup_note,',
    '"GX Works2写入未完成",\n            display_message + backup_note,',
)

replace_once(
    main_path,
    '''    def _gxworks2_import_thread_finished(self):
        self._gxworks2_import_thread = None
        self.gxworks2_import_button.setText("同步 GX Works2")
        if hasattr(self, "_update_gx_sync_button_enabled"):
''',
    '''    def _gxworks2_import_thread_finished(self):
        self._gxworks2_import_thread = None
        self._gx_sync_intent = "idle"
        self._reset_gx_action_buttons()
        if hasattr(self, "_update_gx_sync_button_enabled"):
''',
)

replace_once(
    main_path,
    'self.retry_button = QPushButton("重试同步", self)',
    'self.retry_button = QPushButton("重试", self)',
)

replace_once(
    import_path,
    '"为避免串项目覆盖，已停止导入；请使用“同步 GX Works2”选择保留哪一方。"',
    '"为避免串项目覆盖，已停止写入；请使用“高级同步”选择保留哪一方。"',
)

# Add a small source-level regression test without importing the Windows/Qt runtime.
test_path = Path("tests/test_gxworks2_simple_bridge_ui.py")
test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_simple_gx_bridge_actions_are_primary_ui():\n    text = Path("src/main.py").read_text(encoding="utf-8")\n    assert 'QPushButton("写入 GX Works2")' in text\n    assert 'QPushButton("读取 GX Works2")' in text\n    assert 'QPushButton("高级同步")' in text\n    assert "def _publish_current_version_to_gxworks2" in text\n    assert "def _pull_current_version_from_gxworks2" in text\n    assert 'self._start_gxworks2_inspection("pull")' in text\n    assert 'self._start_gxworks2_inspection("reconcile")' in text\n\n\ndef test_direct_pull_does_not_force_three_way_choice():\n    text = Path("src/main.py").read_text(encoding="utf-8")\n    marker = 'if intent == "pull":'\n    assert marker in text\n    branch = text.split(marker, 1)[1].split('if status == "synced":', 2)\n    assert len(branch) >= 2\n    assert "self._start_gxworks2_pull(result, request)" in text\n\n\ndef test_external_modification_points_to_advanced_sync():\n    text = Path("src/gxworks2/import_service.py").read_text(encoding="utf-8")\n    assert '请使用“高级同步”选择保留哪一方' in text\n''',
    encoding="utf-8",
)
