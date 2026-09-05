from pathlib import Path


def test_contract_mismatch_is_materialized_before_user_repair_choice():
    source = Path("src/main.py").read_text(encoding="utf-8")
    assert "except ApproachContractValidationError as contract_error:" in source
    assert '"contract_mismatch": (' in source
    assert "保留原始候选并先生成 CSV" in source
    assert "contract_repair_button" in source
    assert "修复方案约束" in source
    assert "def _repair_current_contract_mismatch(self):" in source
    assert "原始版本和 CSV 保持不变" in source


def test_contract_mismatch_no_longer_enters_pre_csv_failure_route():
    source = Path("src/main.py").read_text(encoding="utf-8")
    compiler_start = source.index("class CompilerThread")
    artifact_generation = source.index("generate_gx_works2_csv", compiler_start)
    compiler_prefix = source[compiler_start:artifact_generation]
    assert "should_auto_repair_validation_error(first_err)" not in compiler_prefix
    assert "已跳过 AI 自动修复" not in compiler_prefix
