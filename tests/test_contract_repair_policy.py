from pathlib import Path

import pytest

from plc_json_validator import (
    ApproachContractValidationError,
    PLCJsonValidationError,
    should_auto_repair_validation_error,
    validate_ladder_full,
)


def _direct_ladder():
    return {
        "device_comments": {"X0": "启动", "Y0": "输出"},
        "rungs": [
            {
                "rung_id": 1,
                "header_element": None,
                "shared_inputs": [],
                "branches": [
                    {
                        "branch_id": 1,
                        "y_offset_level": 0,
                        "inputs": [
                            {"type": "NO", "address": "X0", "label": "启动"}
                        ],
                        "outputs": [
                            {"type": "COIL", "address": "Y0", "label": "输出"}
                        ],
                    }
                ],
            }
        ],
    }


def test_missing_required_opcode_is_contract_mismatch_not_auto_repairable():
    spec = {
        "selected_approach": {
            "name": "MOV方案",
            "generation_guide": "使用 MOV 完成方案",
            "generation_contract": {
                "required_opcodes": ["MOV"],
                "enforce": True,
            },
        }
    }

    with pytest.raises(ApproachContractValidationError) as captured:
        validate_ladder_full(_direct_ladder(), "FX3U", spec)

    error = captured.value
    assert isinstance(error, PLCJsonValidationError)
    assert "缺少方案必用指令 MOV" in str(error)
    assert error.repair_policy == "manual"
    assert should_auto_repair_validation_error(error) is False


def test_normal_plc_validation_errors_remain_auto_repairable():
    error = PLCJsonValidationError("syntactic validation failure")
    assert should_auto_repair_validation_error(error) is True



def test_compiler_keeps_contract_mismatch_candidate_before_repair_choice():
    source = Path("src/main.py").read_text(encoding="utf-8")
    compiler_start = source.index("class CompilerThread")
    catch = source.index("except ApproachContractValidationError as contract_error:", compiler_start)
    csv_generation = source.index("generate_gx_works2_csv", catch)
    remote = source.index('"stage": "repairing_remote"', compiler_start)
    assert catch < csv_generation
    assert remote < csv_generation
    block = source[catch:csv_generation]
    assert "保留原始候选并先生成 CSV" in block
    assert "should_auto_repair_validation_error(first_err)" not in block
