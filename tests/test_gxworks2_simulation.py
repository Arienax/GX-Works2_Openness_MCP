from dataclasses import dataclass

import pytest

from gxworks2.simulation import (
    GXSimulator2PreparationService,
    NativeGXWorks2SimulationAutomation,
)
from simulator.runtime import SimulatorGatewayRuntime


@pytest.fixture(autouse=True)
def _simulator_dependencies_installed(monkeypatch):
    monkeypatch.setattr(
        "simulator.gateway.detect_simulator_environment",
        lambda: {
            "simulator_installed": True,
            "mx_component_installed": True,
            "simulator_processes": [],
        },
    )


@dataclass
class _Session:
    process_id: int = 1
    window_handle: int = 2
    project_open: bool = True
    project_name: str = "fixture"


class _Finder:
    def __init__(self, session=None):
        self.session = session

    def find_running(self):
        return self.session


class _ProjectAutomation:
    def __init__(self, *, project_open=True, program_ready=True):
        self.project_open = project_open
        self.program_ready = program_ready

    def inspect_project(self, _session):
        return {
            "automation_available": True,
            "project_open": self.project_open,
            "program_ready": self.program_ready,
            "project_name": "fixture",
        }


class _SimulationAutomation:
    def __init__(self, runtime):
        self.runtime = runtime
        self.invocations = 0

    def start_stop_simulation(self, _session):
        self.invocations += 1
        self.runtime.ready = not self.runtime.ready
        return {"invoked": True, "command": "开始/停止模拟"}

    def handle_startup_dialogs(self, _session):
        return {"handled": False, "failure": ""}


class _Runtime:
    def __init__(self, *, ready=False, mx=True):
        self.ready = ready
        self.mx = mx
        self.disconnected = False

    def ensure_gateway(self):
        return {
            "service": "plc-ai-gx-simulator2-gateway",
            "simulator_only": True,
            "mx_component_available": self.mx,
        }

    def health(self):
        return self.ensure_gateway()

    def probe_simulator(self):
        return {
            "ready": self.ready,
            "health": self.ensure_gateway(),
            "error": "offline" if not self.ready else "",
        }

    def disconnect(self):
        self.disconnected = True


class _RuntimeClient:
    def __init__(self, run_value):
        self.run_value = run_value
        self.disconnected = False

    def connect(self):
        return {"route": "GX Simulator2"}

    def read_many(self, addresses):
        assert addresses == ["M8000"]
        return {"M8000": self.run_value}

    def disconnect(self):
        self.disconnected = True


def _service(runtime, *, session=True, project_open=True, program_ready=True):
    automation = _SimulationAutomation(runtime)
    return (
        GXSimulator2PreparationService(
            finder=_Finder(_Session() if session else None),
            project_automation=_ProjectAutomation(
                project_open=project_open,
                program_ready=program_ready,
            ),
            simulation_automation=automation,
            runtime=runtime,
        ),
        automation,
    )


def test_prepare_reuses_running_simulator_without_toggling_menu():
    runtime = _Runtime(ready=True)
    service, automation = _service(runtime)
    result = service.prepare(timeout=0.1)
    assert result.success
    assert result.details["already_running"] is True
    assert automation.invocations == 0


def test_prepare_invokes_named_command_and_requires_route_probe():
    runtime = _Runtime(ready=False)
    service, automation = _service(runtime)
    result = service.prepare(timeout=0.1)
    assert result.success
    assert result.details["already_running"] is False
    assert automation.invocations == 1


def test_prepare_rejects_missing_project_program_and_mx_component():
    runtime = _Runtime()
    missing_project, _ = _service(runtime, project_open=False)
    assert not missing_project.prepare(timeout=0.1).success

    missing_program, _ = _service(runtime, program_ready=False)
    assert not missing_program.prepare(timeout=0.1).success

    no_mx, automation = _service(_Runtime(mx=False))
    result = no_mx.prepare(timeout=0.1)
    assert not result.success
    assert result.stage == "mx_component"
    assert automation.invocations == 0


def test_preflight_explains_that_gxworks2_simulator_and_external_api_are_separate(
    monkeypatch,
):
    monkeypatch.setattr(
        "simulator.gateway.detect_simulator_environment",
        lambda: {
            "simulator_installed": True,
            "mx_component_installed": False,
            "simulator_processes": ["fxsimrun2.exe"],
        },
    )
    runtime = _Runtime(mx=False)
    service, automation = _service(runtime)

    result = service.preflight()

    assert not result.success
    assert result.stage == "mx_component"
    assert "GX Works2 可以单独运行仿真" in result.message
    assert result.details["required_architecture"] == "x86"
    assert automation.invocations == 0


def test_stop_disconnects_gateway_before_toggling_simulation():
    runtime = _Runtime(ready=True)
    service, automation = _service(runtime)
    result = service.stop_if_running(timeout=0.5)
    assert result.success
    assert runtime.disconnected
    assert automation.invocations == 1
    assert runtime.ready is False
    assert result.details["verification_samples"] == 3


def test_stop_starts_cold_gateway_before_deciding_simulator_is_not_running():
    class ColdRuntime(_Runtime):
        def __init__(self):
            super().__init__(ready=True)
            self.gateway_starts = 0

        def health(self):
            return None

        def ensure_gateway(self):
            self.gateway_starts += 1
            return super().ensure_gateway()

    runtime = ColdRuntime()
    service, automation = _service(runtime)

    result = service.stop_if_running(timeout=0.5)

    assert result.success
    assert runtime.gateway_starts >= 1
    assert runtime.disconnected
    assert automation.invocations == 1
    assert runtime.ready is False


def test_prepare_fails_cleanly_when_gxworks2_is_not_running():
    runtime = _Runtime()
    service, automation = _service(runtime, session=False)
    result = service.prepare(timeout=0.1)
    assert not result.success
    assert "GX Works2" in result.message
    assert automation.invocations == 0


def test_runtime_probe_requires_m8000_run_monitor(monkeypatch):
    runtime = SimulatorGatewayRuntime(executable="missing.exe")
    monkeypatch.setattr(
        runtime,
        "ensure_gateway",
        lambda: {"mx_component_available": True, "simulator_only": True},
    )
    stopped_client = _RuntimeClient(0)
    monkeypatch.setattr(runtime, "client", lambda timeout=2.0: stopped_client)

    stopped = runtime.probe_simulator()

    assert stopped["connected"] is True
    assert stopped["cpu_run"] is False
    assert stopped["ready"] is False
    assert stopped_client.disconnected is True

    running_client = _RuntimeClient(1)
    monkeypatch.setattr(runtime, "client", lambda timeout=2.0: running_client)
    running = runtime.probe_simulator()
    assert running["ready"] is True
    assert running["run_monitor"] == 1
    assert running_client.disconnected is True


def test_plc_write_completion_dialog_is_closed_before_ready_probe(monkeypatch):
    class DialogAutomation:
        @staticmethod
        def _native_dialog_handles(_session):
            return [42]

        @staticmethod
        def _native_dialog_text(_handle):
            return "PLC写入 参数 写入：完成 程序（MAIN）写入：完成 PLC写入：结束 关闭"

        @staticmethod
        def _native_descendants(_handle):
            return []

        @staticmethod
        def _native_window_title(_handle):
            return ""

    automation = NativeGXWorks2SimulationAutomation(DialogAutomation())
    clicked = []
    monkeypatch.setattr(
        automation,
        "_click_dialog_button",
        lambda handle, pattern: clicked.append((handle, pattern.pattern)) or True,
    )

    result = automation.handle_startup_dialogs(_Session())

    assert result == {"handled": True, "pending": True, "failure": ""}
    assert clicked and clicked[0][0] == 42


def test_custom_gxworks2_menu_invokes_exact_simulation_item_not_only_access_key():
    class Window:
        def __init__(self):
            self.keys = []

        def set_focus(self):
            pass

        def type_keys(self, keys):
            self.keys.append(keys)

    class Command:
        invoked = False

        @staticmethod
        def window_text():
            return "模拟开始/停止(S)"

        def invoke(self):
            self.invoked = True

    window = Window()
    command = Command()

    class UIAutomation:
        @staticmethod
        def _main_window(_session):
            return window

        @staticmethod
        def _find_menu_item(_window, _pattern, enabled=True):
            assert enabled is True
            return command

    automation = NativeGXWorks2SimulationAutomation(UIAutomation())
    result = automation._invoke_popup_command(_Session(), "no native menu")

    assert result["method"] == "visible_menu_invoke"
    assert command.invoked is True
    assert window.keys == ["%b"]
