from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ImportErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    CSV_NOT_FOUND = "csv_not_found"
    CSV_INVALID = "csv_invalid"
    GXWORKS2_NOT_FOUND = "gxworks2_not_found"
    GXWORKS2_NOT_RUNNING = "gxworks2_not_running"
    TARGET_PROJECT_NOT_OPEN = "target_project_not_open"
    TARGET_PROGRAM_NOT_READY = "target_program_not_ready"
    BACKUP_FAILED = "backup_failed"
    EXTERNAL_MODIFICATION_DETECTED = "external_modification_detected"
    BASELINE_READ_FAILED = "baseline_read_failed"
    BASELINE_WRITE_FAILED = "baseline_write_failed"
    PROJECT_SAVE_REQUIRED = "project_save_required"
    IMPORT_DIALOG_NOT_FOUND = "import_dialog_not_found"
    IMPORT_REJECTED = "import_rejected"
    IMPORT_VERIFICATION_FAILED = "import_verification_failed"
    AUTOMATION_UNAVAILABLE = "automation_unavailable"
    AUTOMATION_FAILED = "automation_failed"


class SyncStatus(str, Enum):
    UNKNOWN = "unknown"
    SYNCED = "synced"
    NEEDS_PUSH = "needs_push"
    NEEDS_PULL = "needs_pull"
    CONFLICT = "conflict"
    UNBOUND = "unbound"
    ERROR = "error"


@dataclass(frozen=True)
class CSVValidationResult:
    valid: bool
    path: str
    encoding: str = ""
    row_count: int = 0
    instruction_count: int = 0
    program_name: str = ""
    plc_info: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommentCSVValidationResult:
    valid: bool
    path: str
    encoding: str = ""
    row_count: int = 0
    comment_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GXWorks2Session:
    process_id: int
    window_handle: int
    title: str
    executable: str = ""
    project_open: bool = False
    project_name: str = ""
    project_state_known: bool = False


@dataclass(frozen=True)
class ImportResult:
    success: bool
    stage: str
    message: str
    error_code: Optional[ImportErrorCode] = None
    csv_path: str = ""
    backup_path: str = ""
    project_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        payload = asdict(self)
        if self.error_code is not None:
            payload["error_code"] = self.error_code.value
        return payload


@dataclass(frozen=True)
class SyncResult:
    success: bool
    status: SyncStatus
    message: str
    error_code: Optional[ImportErrorCode] = None
    project_name: str = ""
    exported_program_path: str = ""
    exported_comment_path: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        payload = asdict(self)
        payload["status"] = self.status.value
        if self.error_code is not None:
            payload["error_code"] = self.error_code.value
        return payload
