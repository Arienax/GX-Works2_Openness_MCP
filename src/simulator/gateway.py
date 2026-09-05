"""GX Simulator2 gateway discovery and loopback HTTP client."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


DEFAULT_GATEWAY_URL = "http://127.0.0.1:17831"
GATEWAY_PROTOCOL_VERSION = 2
REQUIRED_GATEWAY_CAPABILITIES = frozenset(
    {"device_read", "device_write", "cpu_reset"}
)
# GX Simulator2 does not use one consistent executable name across CPU
# families.  In particular, FX projects run as FXSimRun2.exe while the small
# manager window is SimManager.exe.  Keep explicit tokens so observational
# diagnostics do not report a running FX simulator as stopped.
_DEFAULT_PROCESS_TOKENS = (
    "fxsimrun2",
    "simmanager",
    "qnsimrun2",
    "qnudsimrun2",
    "qnxsimrun2",
    "qutesimrun",
    "simulator2",
    "gxsim",
)

# The PLC AI bridge itself contains ``gxsimulator2`` in its executable name.
# It is evidence that the local HTTP gateway is running, not that Mitsubishi's
# Simulator2 session/CPU is running.
_NON_SIMULATOR_PROCESS_TOKENS = (
    "plcai.gxsimulator2gateway",
)


class GatewayError(RuntimeError):
    """Base class for failures reported by the local Simulator2 gateway."""


class GatewayUnavailableError(GatewayError):
    """The gateway cannot be reached or cannot provide a usable response."""


class GatewayProtocolError(GatewayUnavailableError):
    """The process on the gateway endpoint uses an incompatible protocol."""


class GatewayOperationError(GatewayError):
    """A gateway request reached the service but the operation failed."""

    def __init__(self, message: str, *, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status = int(status or 0)
        self.code = str(code or "").strip().upper()


def gateway_compatibility(health: Mapping[str, Any]) -> tuple[bool, str]:
    """Validate the versioned protocol required by the current test runner."""

    try:
        protocol_version = int(health.get("protocol_version") or 0)
    except (TypeError, ValueError):
        protocol_version = 0
    if protocol_version < GATEWAY_PROTOCOL_VERSION:
        return (
            False,
            "GX Simulator2 网关版本过旧"
            f"（协议 {protocol_version or '未声明'}，需要 {GATEWAY_PROTOCOL_VERSION}）。",
        )
    raw_capabilities = health.get("capabilities")
    if isinstance(raw_capabilities, Mapping):
        capabilities = {
            str(name).strip().casefold()
            for name, enabled in raw_capabilities.items()
            if enabled
        }
    elif isinstance(raw_capabilities, Sequence) and not isinstance(
        raw_capabilities, (str, bytes)
    ):
        capabilities = {
            str(name).strip().casefold() for name in raw_capabilities if str(name).strip()
        }
    else:
        capabilities = set()
    missing = sorted(REQUIRED_GATEWAY_CAPABILITIES - capabilities)
    if missing:
        return False, "GX Simulator2 网关缺少必要能力：" + "、".join(missing)
    return True, ""


def is_gateway_environment_error(error: BaseException) -> bool:
    """Return whether a failure invalidates the shared simulator environment."""

    return isinstance(error, GatewayError)


def _registry_progid_exists(name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        access_modes = [0]
        for flag_name in ("KEY_WOW64_32KEY", "KEY_WOW64_64KEY"):
            flag = getattr(winreg, flag_name, 0)
            if flag and flag not in access_modes:
                access_modes.append(flag)
        for access in access_modes:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT,
                    name,
                    0,
                    winreg.KEY_READ | access,
                ):
                    return True
            except OSError:
                continue
        return False
    except (OSError, ImportError):
        return False


def _running_processes() -> Sequence[str]:
    if os.name != "nt":
        return []
    try:
        output = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    names = []
    for line in output.splitlines():
        if line.startswith('"'):
            names.append(line.split('",', 1)[0].strip('"').casefold())
    return names


def detect_simulator_environment() -> Dict[str, Any]:
    """Report locally observable GX Simulator2/MX Component evidence.

    The bundled gateway uses ``ActProgType`` with ``ActUnitType`` fixed to
    ``UNIT_SIMULATOR2``.  It deliberately does not use a logical station, so a
    logical-station setting is reported only for backwards-compatible
    diagnostics and is never a readiness requirement.
    """

    executable_candidates = [
        Path(r"C:\Program Files (x86)\MELSOFT\GX Simulator2\GXSimulator2.exe"),
        Path(r"C:\Program Files\MELSOFT\GX Simulator2\GXSimulator2.exe"),
        Path(r"C:\MELSEC\GX Simulator2\GXSimulator2.exe"),
        Path(r"D:\GXWORKS2\GPPW2\GX Simulator2\FXCPU\FXSimRun2.exe"),
    ]
    gxworks2_executable = os.environ.get("GXWORKS2_EXE", "").strip()
    if not gxworks2_executable:
        try:
            from gxworks2.finder import GXWorks2Finder

            found_gxworks2 = GXWorks2Finder().find_executable()
            gxworks2_executable = str(found_gxworks2 or "")
        except Exception:
            gxworks2_executable = ""
    if gxworks2_executable:
        gx_root = Path(gxworks2_executable).expanduser().resolve().parent
        executable_candidates[:0] = [
            gx_root / "GX Simulator2" / "FXCPU" / "FXSimRun2.exe",
            gx_root / "GX Simulator2" / "Common" / "SimManager.exe",
        ]
    configured = os.environ.get("GX_SIMULATOR2_EXE", "").strip()
    if configured:
        executable_candidates.insert(0, Path(configured))
    executables = list(
        dict.fromkeys(
            str(path.resolve()) for path in executable_candidates if path.is_file()
        )
    )
    processes = _running_processes()
    configured_tokens = tuple(
        item.strip().casefold()
        for item in os.environ.get("GX_SIMULATOR_PROCESS_NAMES", "").split(",")
        if item.strip()
    )
    process_tokens = configured_tokens or _DEFAULT_PROCESS_TOKENS
    simulator_processes = sorted(
        name
        for name in processes
        if any(token in name for token in process_tokens)
        and not any(token in name for token in _NON_SIMULATOR_PROCESS_TOKENS)
    )
    progids = [
        name
        for name in (
            "ActProgType.ActProgType",
            "ActProgType64.ActProgType64",
        )
        if _registry_progid_exists(name)
    ]
    configured_station = os.environ.get("GX_SIMULATOR_LOGICAL_STATION", "").strip()
    return {
        "platform": os.name,
        "simulator_executables": executables,
        "simulator_processes": simulator_processes,
        "mx_component_progids": progids,
        "simulator_installed": bool(executables),
        "mx_component_installed": bool(progids),
        "logical_station_configured": bool(configured_station),
        "logical_station": int(configured_station) if configured_station.isdigit() else None,
        "gateway_url": os.environ.get("GX_SIMULATOR_GATEWAY_URL", DEFAULT_GATEWAY_URL),
        "ready_for_gateway": bool(progids and simulator_processes),
        "limitations": [
            "Readiness is observational; the gateway must still attest and open its GX Simulator2-only route.",
            "MX Component presence alone does not prove that GX Simulator2 is running.",
        ],
    }


@dataclass
class GXSimulatorGatewayClient:
    base_url: str = DEFAULT_GATEWAY_URL
    token: str = ""
    timeout: float = 5.0
    reset_timeout: float = 15.0
    backend_kind: str = "gx_simulator2_gateway"
    # The real Simulator2 backend can read the FX3U scan monitor registers.
    # Explicit capability signalling prevents test doubles from fabricating
    # zero-valued runtime evidence for devices they do not emulate.
    supports_scan_monitor: bool = False
    supports_cpu_reset: bool = False

    def __post_init__(self):
        self.base_url = str(self.base_url or DEFAULT_GATEWAY_URL).rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("GX Simulator2 gateway must use a loopback HTTP address")
        if not self.token:
            self.token = os.environ.get("GX_SIMULATOR_GATEWAY_TOKEN", "")
        self.connected = False

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ):
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        # A client may be created before the lazy runtime starts the gateway
        # and publishes its per-process token. Resolve it again at request
        # time so the UI can remain fully lazy without retaining a stale blank
        # credential.
        request_token = self.token or os.environ.get(
            "GX_SIMULATOR_GATEWAY_TOKEN", ""
        ).strip()
        if request_token:
            headers["X-PLC-Gateway-Token"] = request_token
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=float(self.timeout if timeout is None else timeout),
            ) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            message = str(
                payload.get("error")
                or payload.get("message")
                or f"HTTP {error.code} {error.reason}"
            )
            code = str(payload.get("error_code") or "").strip()
            if code:
                message = f"{message} [{code}]"
            raise GatewayOperationError(
                message,
                status=error.code,
                code=code,
            ) from error
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise GatewayUnavailableError(f"GX Simulator2 gateway unavailable: {error}") from error
        if not isinstance(result, Mapping):
            raise GatewayUnavailableError("GX Simulator2 gateway returned invalid JSON")
        if result.get("ok") is False:
            code = str(result.get("error_code") or "").strip()
            message = str(result.get("error") or "gateway operation failed")
            if code:
                message = f"{message} [{code}]"
            raise GatewayOperationError(message, code=code)
        return dict(result)

    def health(self) -> Dict[str, Any]:
        result = self._request("GET", "/health")
        raw_capabilities = result.get("capabilities")
        capabilities = raw_capabilities if isinstance(raw_capabilities, Mapping) else {}
        self.supports_scan_monitor = bool(capabilities.get("scan_monitor"))
        self.supports_cpu_reset = bool(capabilities.get("cpu_reset"))
        return result

    def connect(self) -> Dict[str, Any]:
        health = self.health()
        if not health.get("simulator_only"):
            raise GatewayUnavailableError(
                "Gateway did not attest simulator_only=true; refusing device writes."
            )
        compatible, reason = gateway_compatibility(health)
        if not compatible:
            raise GatewayProtocolError(reason)
        result = self._request("POST", "/connect", {})
        self.connected = True
        return result

    def disconnect(self) -> None:
        if self.connected:
            try:
                self._request("POST", "/disconnect", {})
            finally:
                self.connected = False

    def read_many(self, addresses: Sequence[str]) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("GX Simulator2 gateway is not connected")
        result = self._request("POST", "/devices/read", {"addresses": list(addresses)})
        values = result.get("values")
        if not isinstance(values, Mapping):
            raise RuntimeError("gateway response is missing values")
        return {str(key).upper(): value for key, value in values.items()}

    def write_many(self, values: Mapping[str, Any]) -> None:
        if not self.connected:
            raise RuntimeError("GX Simulator2 gateway is not connected")
        self._request("POST", "/devices/write", {"values": dict(values)})

    def reset_cpu(
        self,
        devices: Sequence[str] = (),
        initial_values: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("GX Simulator2 gateway is not connected")
        return self._request(
            "POST",
            "/cpu/reset",
            {
                "devices": [str(address).upper() for address in devices],
                "initial_values": {
                    str(address).upper(): value
                    for address, value in (initial_values or {}).items()
                },
            },
            timeout=self.reset_timeout,
        )

    def advance_ms(self, milliseconds: int) -> None:
        import time

        time.sleep(max(0, int(milliseconds)) / 1000.0)


__all__ = [
    "DEFAULT_GATEWAY_URL",
    "GATEWAY_PROTOCOL_VERSION",
    "REQUIRED_GATEWAY_CAPABILITIES",
    "GXSimulatorGatewayClient",
    "GatewayError",
    "GatewayOperationError",
    "GatewayProtocolError",
    "GatewayUnavailableError",
    "detect_simulator_environment",
    "gateway_compatibility",
    "is_gateway_environment_error",
]
