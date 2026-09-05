from pathlib import Path


def replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_validator():
    path = Path("src/plc_json_validator.py")
    replace_once(
        path,
        '''class PLCJsonValidationError(ValueError):
    pass


def _fail(path, message):
    raise PLCJsonValidationError(f"{path}: {message}")
''',
        '''class PLCJsonValidationError(ValueError):
    pass


class ApproachContractValidationError(PLCJsonValidationError):
    """A generated candidate violates the user-confirmed implementation contract."""

    repair_policy = "manual"

    def __init__(self, path, approach_name, issues):
        self.path = str(path)
        self.approach_name = str(approach_name or "已选方案").strip() or "已选方案"
        self.issues = tuple(str(item) for item in (issues or []) if str(item).strip())
        detail = "；".join(self.issues) or "方案约束未满足"
        super().__init__(
            f"{self.path}: 生成结果不符合用户选择的“{self.approach_name}”：{detail}"
        )


def should_auto_repair_validation_error(error):
    """Whether CompilerThread may enter the generic remote AI repair path."""

    return not isinstance(error, ApproachContractValidationError)


def _fail(path, message):
    raise PLCJsonValidationError(f"{path}: {message}")
''',
        "validator exception classification",
    )
    replace_once(
        path,
        '''        if approach_issues:
            approach_name = str(
                (selected_approach or {}).get("name")
                or "已选方案"
            ).strip()
            _fail(
                "$.confirmed_spec.selected_approach",
                f"生成结果不符合用户选择的“{approach_name}”："
                + "；".join(approach_issues),
            )
''',
        '''        if approach_issues:
            approach_name = str(
                (selected_approach or {}).get("name")
                or "已选方案"
            ).strip()
            raise ApproachContractValidationError(
                "$.confirmed_spec.selected_approach",
                approach_name,
                approach_issues,
            )
''',
        "selected approach mismatch raise",
    )


def patch_main():
    path = Path("src/main.py")
    replace_once(
        path,
        '''from plc_json_validator import (
    PLCJsonValidationError,
    validate_ladder_full,
    validate_ladder_partial,
    validate_st_json,
)
''',
        '''from plc_json_validator import (
    PLCJsonValidationError,
    should_auto_repair_validation_error,
    validate_ladder_full,
    validate_ladder_partial,
    validate_st_json,
)
''',
        "main validator import",
    )
    replace_once(
        path,
        '''            except Exception as first_err:
                if self.target_mode != "ladder":
''',
        '''            except Exception as first_err:
                if not should_auto_repair_validation_error(first_err):
                    validation_messages.append(str(first_err))
                    self.progress_updated.emit(
                        self.task_id,
                        {
                            "stage": "contract_mismatch",
                            "severity": "error",
                            "message": (
                                "生成结果未满足已确认方案约束；"
                                "不会启动 AI 自动修复，请明确重新生成或手动修复。"
                            ),
                        },
                    )
                    self.failure.emit(
                        self.task_id,
                        "生成结果未满足已确认方案约束，已跳过 AI 自动修复: "
                        f"{first_err}",
                    )
                    return
                if self.target_mode != "ladder":
''',
        "compiler repair routing",
    )


if __name__ == "__main__":
    patch_validator()
    patch_main()
    print("patched contract mismatch repair routing")
