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
