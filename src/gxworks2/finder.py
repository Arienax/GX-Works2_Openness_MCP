import ctypes
import os
from pathlib import Path

from .models import GXWorks2Session


class GXWorks2Finder:
    PROCESS_NAMES = {"gd2.exe"}
    INSTALL_CANDIDATES = (
        Path(r"C:\Program Files (x86)\MELSOFT\GPPW2\GD2.exe"),
        Path(r"C:\MELSEC\GPPW2\GD2.exe"),
        Path(r"D:\GXWORKS2\GPPW2\GD2.exe"),
    )

    def find_executable(self):
        configured = os.environ.get("GXWORKS2_EXE", "").strip()
        candidates = ([Path(configured)] if configured else []) + list(self.INSTALL_CANDIDATES)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def find_running(self):
        if os.name != "nt":
            return None
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        matches = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            title = title_buffer.value.strip()
            if "GX Works2" not in title:
                return True
            process_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            executable = self._process_image(kernel32, process_id.value)
            if executable and Path(executable).name.casefold() not in self.PROCESS_NAMES:
                return True
            project_name = self._project_name_from_title(title)
            matches.append(
                GXWorks2Session(
                    process_id=int(process_id.value),
                    window_handle=int(hwnd),
                    title=title,
                    executable=executable,
                    project_open=bool(project_name),
                    project_name=project_name,
                    project_state_known=(title == "MELSOFT系列 GX Works2"),
                )
            )
            return True

        user32.EnumWindows(callback_type(visit), 0)
        return matches[0] if matches else None

    @staticmethod
    def _process_image(kernel32, process_id):
        query_limited_information = 0x1000
        handle = kernel32.OpenProcess(query_limited_information, False, process_id)
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value
            return ""
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _project_name_from_title(title):
        normalized = str(title or "").strip()
        if not normalized or normalized == "MELSOFT系列 GX Works2":
            return ""

        # A GX Works2 MDI title is normally shaped like:
        #   MELSOFT系列 GX Works2 (工程未设置) - [[PRG]写入 MAIN 84步]
        # The final bracketed part is the active editor, not the project.  It
        # changes when the user opens MAIN, device comments, parameters, etc.
        # Binding overwrite protection to that child title would therefore
        # create a different baseline for every editor.  Prefer the stable
        # text carried by the GX Works2 frame itself.
        for separator in (" - ", " — ", " – "):
            parts = [
                part.strip()
                for part in normalized.split(separator)
                if part.strip()
            ]
            for index, part in enumerate(parts):
                marker = part.find("GX Works2")
                if marker < 0:
                    continue
                suffix = part[marker + len("GX Works2") :].strip()
                if suffix:
                    return suffix
                # Retain compatibility with titles such as
                # ``Fixture - GX Works2`` used by older installations, but
                # never use a segment after GX Works2: that is the MDI child.
                if index > 0:
                    candidate = parts[index - 1]
                    if "MELSOFT" not in candidate and not candidate.startswith("["):
                        return candidate
                return ""
        return ""

    def start(self):
        executable = self.find_executable()
        if executable is None:
            return None
        os.startfile(str(executable))
        return executable
