from pathlib import Path


def test_simple_gx_bridge_actions_are_primary_ui():
    text = Path("src/main.py").read_text(encoding="utf-8")
    assert 'QPushButton("写入 GX Works2")' in text
    assert 'QPushButton("读取 GX Works2")' in text
    assert 'QPushButton("高级同步")' in text
    assert "def _publish_current_version_to_gxworks2" in text
    assert "def _pull_current_version_from_gxworks2" in text
    assert 'self._start_gxworks2_inspection("pull")' in text
    assert 'self._start_gxworks2_inspection("reconcile")' in text


def test_direct_pull_does_not_force_three_way_choice():
    text = Path("src/main.py").read_text(encoding="utf-8")
    marker = 'if intent == "pull":'
    assert marker in text
    branch = text.split(marker, 1)[1].split('if status == "synced":', 2)
    assert len(branch) >= 2
    assert "self._start_gxworks2_pull(result, request)" in text


def test_external_modification_points_to_advanced_sync():
    text = Path("src/gxworks2/import_service.py").read_text(encoding="utf-8")
    assert '请使用“高级同步”选择保留哪一方' in text


def test_bridge_button_state_is_managed_as_one_group():
    text = Path("src/main.py").read_text(encoding="utf-8")
    assert "def _set_gx_action_buttons_enabled" in text
    assert 'self._set_gx_action_buttons_enabled(False)' in text
    assert 'self._update_gx_sync_button_enabled()' in text
    assert 'self.setWindowTitle("GX Works2操作未完成")' in text
    retry = text.split("if dialog.retry_requested:", 1)[1].split("return", 1)[0]
    assert "self._set_gx_action_buttons_enabled(False)" in retry
    assert "self.gxworks2_pull_button" in retry
    assert "self.gxworks2_advanced_button" in retry
