import os

import pytest

from gxworks2.finder import GXWorks2Finder
from gxworks2.ui_automation import PywinautoGXWorks2UIAutomation


@pytest.mark.skipif(os.name != "nt", reason="Windows-only GX Works2 integration")
def test_running_gxworks2_without_project_has_no_csv_import_command():
    session = GXWorks2Finder().find_running()
    if session is None:
        pytest.skip("GX Works2 is not running")
    if not session.project_state_known or session.project_open:
        pytest.skip("GX Works2 currently has a project open")

    state = PywinautoGXWorks2UIAutomation(timeout=4).inspect_project(session)
    assert state["automation_available"]
    assert not state["project_open"]
    assert not state["program_ready"]
    assert not state["read_csv_available"]


@pytest.mark.skipif(os.name != "nt", reason="Windows-only GX Works2 integration")
def test_running_gxworks2_output_summary_is_machine_readable():
    session = GXWorks2Finder().find_running()
    if session is None or not session.project_open:
        pytest.skip("GX Works2 does not currently have an open program")

    summary = PywinautoGXWorks2UIAutomation._read_output_summary(session)
    if not summary:
        pytest.skip("GX Works2 has no current operation summary")
    assert "Error:" in summary
    assert "Warning:" in summary
