from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch anchor not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


main_path = "src/main.py"

replace_once(
    main_path,
    '''        self.gxworks2_import_button.setEnabled(mode == "ladder")
        self._set_gx_sync_status(
''',
    '''        self._update_gx_sync_button_enabled()
        self._set_gx_sync_status(
''',
)
replace_once(
    main_path,
    '''        self.gxworks2_import_button.setEnabled(False)
        self._set_gx_sync_status("unknown")
''',
    '''        self._set_gx_action_buttons_enabled(False)
        self._set_gx_sync_status("unknown")
''',
)
replace_once(
    main_path,
    '''            if dialog.retry_requested:
                self._gx_sync_retry_pending = True
                self.gxworks2_import_button.setEnabled(False)
                self.gxworks2_import_button.setText("准备重试…")
                if self._gxworks2_sync_thread is None:
                    QTimer.singleShot(0, self._run_pending_gx_sync_retry)
''',
    '''            if dialog.retry_requested:
                self._gx_sync_retry_pending = True
                self._set_gx_action_buttons_enabled(False)
                active_button = (
                    self.gxworks2_pull_button
                    if getattr(self, "_gx_sync_intent", "reconcile") == "pull"
                    else self.gxworks2_advanced_button
                )
                active_button.setText("准备重试…")
                if self._gxworks2_sync_thread is None:
                    QTimer.singleShot(0, self._run_pending_gx_sync_retry)
''',
)
replace_once(
    main_path,
    'self.setWindowTitle("GX Works2同步未完成")',
    'self.setWindowTitle("GX Works2操作未完成")',
)
replace_once(
    main_path,
    '"方案约束尚未满足；可以先导出/同步到 GX Works2 检查，"',
    '"方案约束尚未满足；可以先导出或写入 GX Works2 检查，"',
)

test_path = Path("tests/test_gxworks2_simple_bridge_ui.py")
text = test_path.read_text(encoding="utf-8")
extra = '''\n\ndef test_bridge_button_state_is_managed_as_one_group():\n    text = Path("src/main.py").read_text(encoding="utf-8")\n    assert "def _set_gx_action_buttons_enabled" in text\n    assert 'self._set_gx_action_buttons_enabled(False)' in text\n    assert 'self._update_gx_sync_button_enabled()' in text\n    assert 'self.setWindowTitle("GX Works2操作未完成")' in text\n    retry = text.split("if dialog.retry_requested:", 1)[1].split("return", 1)[0]\n    assert "self._set_gx_action_buttons_enabled(False)" in retry\n    assert "self.gxworks2_pull_button" in retry\n    assert "self.gxworks2_advanced_button" in retry\n'''
if "test_bridge_button_state_is_managed_as_one_group" not in text:
    test_path.write_text(text + extra, encoding="utf-8")
