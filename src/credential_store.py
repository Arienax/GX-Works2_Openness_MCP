"""Store the API key in Windows Credential Manager."""

import ctypes
from ctypes import wintypes


CREDENTIAL_TARGET = "PLC AI Studio/GXWorks2 Ladder Generator/API Key"
PROFILE_CREDENTIAL_PREFIX = "PLC-AI-Studio/model-profile/"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_PCREDENTIALW = ctypes.POINTER(_CREDENTIALW)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.CredReadW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(_PCREDENTIALW),
]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
_advapi32.CredWriteW.restype = wintypes.BOOL
_advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_advapi32.CredDeleteW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]


def credential_target_for_profile(profile_id):
    """Return the stable Windows Credential Manager target for one profile."""

    value = str(profile_id or "").strip()
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
        raise ValueError("模型配置 ID 只能包含字母、数字、点、下划线和连字符。")
    return PROFILE_CREDENTIAL_PREFIX + value


def read_api_key(target=CREDENTIAL_TARGET):
    credential_pointer = _PCREDENTIALW()
    if not _advapi32.CredReadW(
        str(target),
        _CRED_TYPE_GENERIC,
        0,
        ctypes.byref(credential_pointer),
    ):
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_FOUND:
            return ""
        raise ctypes.WinError(error)

    try:
        credential = credential_pointer.contents
        if not credential.CredentialBlob or not credential.CredentialBlobSize:
            return ""
        raw = ctypes.string_at(
            credential.CredentialBlob,
            credential.CredentialBlobSize,
        )
        return raw.decode("utf-8")
    finally:
        _advapi32.CredFree(credential_pointer)


def write_api_key(api_key, target=CREDENTIAL_TARGET):
    value = str(api_key or "").strip()
    if not value:
        raise ValueError("API Key 不能为空。")
    raw = value.encode("utf-8")
    blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    credential = _CREDENTIALW()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = str(target)
    credential.Comment = "GXWorks2 梯形图生成系统 API Key"
    credential.CredentialBlobSize = len(raw)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "API Key"
    if not _advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def delete_api_key(target=CREDENTIAL_TARGET):
    if _advapi32.CredDeleteW(str(target), _CRED_TYPE_GENERIC, 0):
        return
    error = ctypes.get_last_error()
    if error != _ERROR_NOT_FOUND:
        raise ctypes.WinError(error)


def has_api_key(target=CREDENTIAL_TARGET):
    return bool(read_api_key(target).strip())
