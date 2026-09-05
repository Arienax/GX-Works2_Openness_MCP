from pathlib import Path
import re


path = Path("src/approach_contracts.py")
text = path.read_text(encoding="utf-8")

normalize_block = r'''_CONTRACT_VALUE_FIELDS = (
    "required_opcodes",
    "forbidden_opcodes",
    "required_devices",
    "forbidden_devices",
    "required_structures",
    "forbidden_structures",
)
_CONTRACT_GROUP_FIELDS = (
    "any_of_opcode_groups",
    "any_of_structure_groups",
)


def _explicit_contract_fields(raw):
    """Return constraint fields explicitly supplied by the structured contract.

    ``generation_guide`` inference is a compatibility/fallback source.  It may
    fill fields omitted by a structured contract, but it never overrides a
    constraint that was explicitly supplied by the analysis result/user.
    """

    return {
        key
        for key in (*_CONTRACT_VALUE_FIELDS, *_CONTRACT_GROUP_FIELDS)
        if key in raw
    }


def _resolve_required_forbidden_conflicts(contract, explicit_fields, warnings):
    for required_key, forbidden_key, label in (
        ("required_opcodes", "forbidden_opcodes", "指令"),
        ("required_devices", "forbidden_devices", "软元件"),
        ("required_structures", "forbidden_structures", "结构"),
    ):
        required = list(contract.get(required_key) or [])
        forbidden = list(contract.get(forbidden_key) or [])
        overlap = sorted(set(required) & set(forbidden))
        if not overlap:
            continue

        required_explicit = required_key in explicit_fields
        forbidden_explicit = forbidden_key in explicit_fields
        if required_explicit and forbidden_explicit:
            # A structured contract contradicting itself is a real definition
            # error and must remain visible to contract_definition_issues().
            continue
        if required_explicit:
            contract[forbidden_key] = [item for item in forbidden if item not in overlap]
            warnings.append(
                f"显式必用{label}覆盖了 generation_guide 推断的禁用约束：{', '.join(overlap)}"
            )
        elif forbidden_explicit:
            contract[required_key] = [item for item in required if item not in overlap]
            warnings.append(
                f"显式禁用{label}覆盖了 generation_guide 推断的必用约束：{', '.join(overlap)}"
            )
        else:
            # Text inference contradicted itself.  Do not invent a winner and
            # do not block confirmation: remove the ambiguous hard constraint.
            contract[required_key] = [item for item in required if item not in overlap]
            contract[forbidden_key] = [item for item in forbidden if item not in overlap]
            warnings.append(
                f"generation_guide 对同一{label}同时推断为必用和禁用，已取消该歧义约束：{', '.join(overlap)}"
            )


def _resolve_any_of_groups(
    contract,
    *,
    group_key,
    required_key,
    forbidden_key,
    label,
    explicit_fields,
    warnings,
    definition_errors,
):
    groups = list(contract.get(group_key) or [])
    required = set(contract.get(required_key) or [])
    forbidden = set(contract.get(forbidden_key) or [])
    group_explicit = group_key in explicit_fields
    forbidden_explicit = forbidden_key in explicit_fields
    result = []

    for group in groups:
        original = list(group)
        # A separately required member already satisfies this any-of clause.
        if required.intersection(original):
            continue

        legal = [item for item in original if item not in forbidden]
        if not legal:
            if group_explicit and forbidden_explicit:
                definition_errors.append(
                    f"{label}任选组没有可用候选：{', '.join(original)} 全部被显式禁止"
                )
                # Preserve the clause for inspection/signatures.  Validation is
                # blocked by definition_errors rather than silently weakening it.
                if original not in result:
                    result.append(original)
                continue
            if group_explicit and not forbidden_explicit:
                # The explicit any-of requirement outranks inferred forbids.
                contract[forbidden_key] = [
                    item
                    for item in (contract.get(forbidden_key) or [])
                    if item not in original
                ]
                forbidden.difference_update(original)
                legal = original
                warnings.append(
                    f"显式{label}任选组覆盖了 generation_guide 推断的禁用约束：{', '.join(original)}"
                )
            else:
                warnings.append(
                    f"generation_guide 推断的{label}任选组与禁用约束冲突，已取消该歧义任选组：{', '.join(original)}"
                )
                continue

        if legal not in result:
            result.append(legal)

    contract[group_key] = result


def _resolve_contract_constraints(contract, explicit_fields):
    warnings = []
    definition_errors = []

    _resolve_required_forbidden_conflicts(contract, explicit_fields, warnings)
    _resolve_any_of_groups(
        contract,
        group_key="any_of_opcode_groups",
        required_key="required_opcodes",
        forbidden_key="forbidden_opcodes",
        label="指令",
        explicit_fields=explicit_fields,
        warnings=warnings,
        definition_errors=definition_errors,
    )
    _resolve_any_of_groups(
        contract,
        group_key="any_of_structure_groups",
        required_key="required_structures",
        forbidden_key="forbidden_structures",
        label="结构",
        explicit_fields=explicit_fields,
        warnings=warnings,
        definition_errors=definition_errors,
    )
    if warnings:
        contract["normalization_warnings"] = warnings
    if definition_errors:
        contract["definition_errors"] = definition_errors
    return contract


def normalize_generation_contract(contract=None, *, approach=None):
    raw = dict(contract) if isinstance(contract, Mapping) else {}
    for alias, canonical in _FIELD_ALIASES.items():
        if canonical not in raw and alias in raw:
            raw[canonical] = raw[alias]

    explicit_fields = _explicit_contract_fields(raw)
    inferred = _infer_contract_from_guide(approach or {})

    def value_source(key):
        return raw.get(key) if key in explicit_fields else inferred.get(key)

    normalized = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "required_opcodes": _unique_strings(value_source("required_opcodes"), upper=True),
        "forbidden_opcodes": _unique_strings(value_source("forbidden_opcodes"), upper=True),
        "required_devices": _unique_strings(value_source("required_devices"), upper=True),
        "forbidden_devices": _unique_strings(value_source("forbidden_devices"), upper=True),
        "required_structures": _unique_strings(value_source("required_structures"), lower=True),
        "forbidden_structures": _unique_strings(value_source("forbidden_structures"), lower=True),
        "any_of_opcode_groups": _normalize_groups(
            value_source("any_of_opcode_groups"), upper=True
        ),
        "any_of_structure_groups": _normalize_groups(
            value_source("any_of_structure_groups"), lower=True
        ),
        # A selected approach is never advisory. Ignore a model-proposed false
        # value so it cannot opt itself out of the user's decision.
        "enforce": True,
        "source": "explicit" if explicit_fields else inferred.get("source", "inferred"),
    }
    return _resolve_contract_constraints(normalized, explicit_fields)

'''

issues_block = r'''def contract_definition_issues(approach):
    normalized = normalize_approach(approach)
    if not normalized:
        return ["未选择实现方案"]
    contract = normalized["generation_contract"]
    issues = list(contract.get("definition_errors") or [])
    for required_key, forbidden_key, label in (
        ("required_opcodes", "forbidden_opcodes", "指令"),
        ("required_devices", "forbidden_devices", "软元件"),
        ("required_structures", "forbidden_structures", "结构"),
    ):
        conflict = sorted(
            set(contract.get(required_key) or [])
            & set(contract.get(forbidden_key) or [])
        )
        if conflict:
            issues.append(f"同一{label}同时被要求和禁止：{', '.join(conflict)}")
    unknown_structures = sorted(
        {
            *(contract.get("required_structures") or []),
            *(contract.get("forbidden_structures") or []),
            *(
                item
                for group in contract.get("any_of_structure_groups") or []
                for item in group
            ),
        }
        - SUPPORTED_STRUCTURES
    )
    if unknown_structures:
        issues.append("包含无法校验的方案结构：" + ", ".join(unknown_structures))
    constraint_count = sum(
        len(contract.get(key) or [])
        for key in (
            "required_opcodes",
            "forbidden_opcodes",
            "required_devices",
            "forbidden_devices",
            "required_structures",
            "forbidden_structures",
            "any_of_opcode_groups",
            "any_of_structure_groups",
        )
    )
    if constraint_count == 0:
        issues.append("方案缺少可执行的生成约束，请明确必用/禁用指令或结构")
    return list(dict.fromkeys(issues))

'''

text, count = re.subn(
    r"def normalize_generation_contract\(contract=None, \*, approach=None\):.*?(?=\ndef normalize_approach\()",
    normalize_block,
    text,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"normalize_generation_contract replacement count={count}")

text, count = re.subn(
    r"def contract_definition_issues\(approach\):.*?(?=\ndef generation_contract_signature\()",
    issues_block,
    text,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"contract_definition_issues replacement count={count}")

path.write_text(text, encoding="utf-8")
print("patched", path)
