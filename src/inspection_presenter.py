"""User-facing presentation helpers for inspection findings.

Inspection reports intentionally persist exact JSON paths because locating and
repair boundary checks need them.  Those paths are implementation details,
though, and should not be the primary evidence shown to an operator.  This
module translates the canonical report data into stable, readable Chinese
without changing or discarding the machine-readable anchors.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from display_names import (
    naturalize_display_text,
    naturalize_identifier,
    source_display_name,
)
from ladder_display import (
    build_rung_display_map,
    display_number_for_anchor,
    rung_index_from_path,
)


_JSON_PATH_RE = re.compile(
    r"\$(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])+"
)
_PATH_TOKEN_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")
_PURE_JSON_PATH_RE = re.compile(
    r"^\s*\$(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])+\s*$"
)
_RUNG_INDEX_RE = re.compile(r"\$\.rungs\[(\d+)\]")
_BRANCH_INDEX_RE = re.compile(r"\.branches\[(\d+)\]")
_OUTPUT_INDEX_RE = re.compile(r"\.outputs\[(\d+)\]")
_INPUT_INDEX_RE = re.compile(r"\.(?:inputs|shared_inputs)\[(\d+)\]")


CATEGORY_LABELS = {
    "review": "程序评审",
    "hard_validation": "程序硬校验",
    "debug_request": "调试输入检查",
    "model_compatibility": "型号与地址兼容",
    "confirmed_io": "确认 I/O 一致性",
    "output_ownership": "输出所有权",
    "set_reset_ownership": "SET/RST 归属",
    "set_reset_toggle": "SET/RST 同扫描翻转",
    "state_ownership": "状态寄存器写入",
    "state_initialization": "状态初始化",
    "state_transition": "状态跳转",
    "state_reset": "状态复位",
    "timer_reset": "定时器复位路径",
    "timer_path": "定时器路径",
    "timer_oscillator": "定时器振荡路径",
    "counter_path": "计数器路径",
    "counter_reset": "计数器复位路径",
    "motion_completion": "运动完成信号",
    "alarm_logic": "故障/报警逻辑",
    "online_observation": "在线观测可读性",
    "fault_diagnosis": "故障诊断",
    "general": "通用检查",
    "multiple_writer": "多写入点",
    "latch_without_reset": "保持位复位路径",
    "mutex_not_enforced": "方向互锁",
    "scan_order_dependency": "扫描顺序依赖",
    "same_scan_read_before_write": "同一扫描先读后写",
    "edge_misuse": "边沿语义",
    "init_value_overwrite_warning": "初始化覆盖",
    "timer_cannot_complete": "定时器完成路径",
    "unreachable_state": "不可达状态",
    "dead_end_state": "无出口状态",
    "scan_budget_warning": "扫描时间预算",
}

SOURCE_LABELS = {
    "local": "本地规则",
    "ai": "AI 深查",
    "merged": "本地 + AI",
    "legacy": "历史报告",
}

CONFIDENCE_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "unknown": "未知",
}

RESOLUTION_LABELS = {
    "open": "待处理",
    "resolved": "已解决",
    "still_present": "仍存在",
    "pending_review": "待复核",
    "not_applicable": "不适用",
}


_FIELD_LABELS = {
    "address": "地址字段",
    "opcode": "指令类型",
    "operands": "指令参数",
    "type": "元件类型",
    "label": "元件说明",
    "expression": "逻辑表达式",
    "preset": "预设值",
    "device_comments": "软元件注释表",
    "header_element": "梯级起始条件",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _unique_strings(values: Iterable[Any]) -> List[str]:
    result = []
    seen = set()
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def category_label(value: Any) -> str:
    text = _clean(value)
    return CATEGORY_LABELS.get(
        text.lower(),
        naturalize_identifier(text, kind="通用检查") if text else "通用检查",
    )


def source_label(value: Any) -> str:
    text = _clean(value)
    return SOURCE_LABELS.get(text.lower(), source_display_name(text or "local"))


def confidence_label(value: Any) -> str:
    text = _clean(value)
    return CONFIDENCE_LABELS.get(
        text.lower(), naturalize_identifier(text, kind="未知")
    )


def resolution_label(value: Any) -> str:
    text = _clean(value)
    return RESOLUTION_LABELS.get(
        text.lower(), naturalize_identifier(text, kind="待处理")
    )


def _path_tokens(path: str):
    return [
        (key, int(raw_index) if raw_index else None)
        for key, raw_index in _PATH_TOKEN_RE.findall(path)
    ]


def describe_json_path(path: Any, rung_id: Any = None) -> str:
    """Translate one canonical JSON path into an operator-facing location.

    ``rung_id`` is used only when the caller can prove that it belongs to this
    exact path.  Otherwise the text explicitly says "program position" so a
    list index is never misrepresented as a ladder rung id.
    """

    raw = _clean(path)
    if raw == "$":
        return "程序整体"
    if not _JSON_PATH_RE.fullmatch(raw):
        return "程序内部位置"

    tokens = _path_tokens(raw)
    parts = []
    index = 0
    in_parallel_block = False
    while index < len(tokens):
        key, number = tokens[index]
        if key:
            next_number = None
            if index + 1 < len(tokens) and tokens[index + 1][0] == "":
                next_number = tokens[index + 1][1]

            if key == "rungs" and next_number is not None:
                verified_rung = _clean(rung_id)
                if verified_rung:
                    parts.append("第 %s 梯级" % verified_rung)
                else:
                    parts.append("程序中的第 %d 个梯级" % (next_number + 1))
                index += 2
                continue
            if key == "branches" and next_number is not None:
                if in_parallel_block:
                    parts.append("并联块第 %d 支路" % (next_number + 1))
                else:
                    parts.append("第 %d 支路" % (next_number + 1))
                index += 2
                continue
            if key in {"inputs", "outputs", "shared_inputs"} and next_number is not None:
                names = {
                    "inputs": "输入元件",
                    "outputs": "输出/指令",
                    "shared_inputs": "公共输入元件",
                }
                parts.append("第 %d 个%s" % (next_number + 1, names[key]))
                index += 2
                continue
            if key == "parallel_block":
                parts.append("并联块")
                in_parallel_block = True
                index += 1
                continue
            if key in _FIELD_LABELS:
                parts.append(_FIELD_LABELS[key])
            elif key not in {"rungs"}:
                # Unknown schema fields stay understandable without exposing
                # their raw implementation name.
                parts.append("相关数据")
        elif number is not None:
            parts.append("第 %d 个元件" % (number + 1))
        index += 1

    return " · ".join(_unique_strings(parts)) or "程序内部位置"


def rung_index_map(base_ladder: Any) -> Dict[int, Any]:
    """Return the legacy array-index to raw-rung-id mapping.

    New UI code should use :func:`rung_display_map`.  This compatibility helper
    remains available for callers that explicitly need persisted identities.
    """

    if not isinstance(base_ladder, Mapping):
        return {}
    rungs = base_ladder.get("rungs")
    if not isinstance(rungs, list):
        return {}
    result = {}
    for index, rung in enumerate(rungs):
        if isinstance(rung, Mapping) and rung.get("rung_id") not in (None, ""):
            result[index] = rung.get("rung_id")
    return result


def rung_display_map(base_ladder: Any) -> Dict[str, Any]:
    """Return the version-local visible-number/raw-id/path mapping."""

    return build_rung_display_map(base_ladder)


def _primary_rung_for_path(finding: Mapping[str, Any], path: str) -> Optional[Any]:
    display_map = finding.get("_rung_display_map") or {}
    raw_rung = finding.get("_locate_raw_rung_id")
    if raw_rung in (None, ""):
        raw_rung = finding.get("rung_id")
    display_number = display_number_for_anchor(
        display_map,
        raw_rung_id=raw_rung,
        json_path=path,
    )
    if display_number is not None:
        return display_number

    # Compatibility for report cards constructed by older callers.
    verified_map = finding.get("_rung_index_map") or {}
    match = _RUNG_INDEX_RE.search(path)
    if match and isinstance(verified_map, Mapping):
        rung_index = int(match.group(1))
        verified = verified_map.get(rung_index)
        if verified is None:
            verified = verified_map.get(str(rung_index))
        if verified not in (None, ""):
            return verified

    primary_path = _clean(finding.get("json_path") or finding.get("path"))
    if not primary_path:
        paths = finding.get("json_paths") or []
        if isinstance(paths, Sequence) and not isinstance(paths, str) and paths:
            primary_path = _clean(paths[0])
    if primary_path != path:
        return None
    rung = finding.get("rung_id")
    if rung in (None, ""):
        rungs = finding.get("rung_ids") or []
        if isinstance(rungs, Sequence) and not isinstance(rungs, str) and rungs:
            rung = rungs[0]
    return rung if rung not in (None, "") else None


def _with_element_label(text: str, element: Mapping[str, Any]) -> str:
    label = _clean(element.get("label"))
    if label and label not in text:
        return "%s（%s）" % (text, label)
    return text


def _condition_description(element: Any) -> str:
    if not isinstance(element, Mapping):
        return ""
    element_type = _clean(element.get("type")).upper()
    address = _clean(element.get("address")).upper()
    expression = _clean(element.get("expression"))
    if element_type == "PARALLEL_BLOCK":
        alternatives = []
        for branch in element.get("branches") or []:
            if not isinstance(branch, list):
                continue
            conditions = []
            for item in branch:
                description = _condition_description(item)
                if description:
                    conditions.append(description)
            if conditions:
                alternatives.append("且".join(conditions))
        return "（%s）" % " 或 ".join(alternatives) if alternatives else "并联条件"
    if element_type in {"P", "RISING"}:
        text = "%s 上升沿" % (address or "信号")
    elif element_type in {"F", "FALLING"}:
        text = "%s 下降沿" % (address or "信号")
    elif element_type == "NC":
        text = "%s 断开" % (address or expression or "条件")
    elif element_type in {"COMPARE", "BLOCK_INPUT"} or expression:
        text = expression or address or "比较条件"
    else:
        text = "%s 接通" % (address or "条件")
    return _with_element_label(text, element)


def _output_description(element: Any) -> str:
    if not isinstance(element, Mapping):
        return ""
    element_type = _clean(element.get("type")).upper()
    address = _clean(element.get("address")).upper()
    value = _clean(element.get("value") or element.get("preset"))
    if element_type == "COIL":
        text = "驱动 %s" % (address or "输出线圈")
    elif element_type == "COUNTER":
        text = "计数 %s%s" % (address, (" " + value) if value else "")
    elif element_type == "TIMER":
        text = "启动定时器 %s%s" % (
            address or "",
            (" " + value) if value else "",
        )
    elif element_type == "APP_INSTR":
        opcode = _clean(element.get("opcode")).upper()
        operands = " ".join(_clean(item) for item in element.get("operands") or [])
        text = "执行 %s" % " ".join(item for item in (opcode, operands) if item)
    elif element_type in {"PLS", "PLF"}:
        text = "执行 %s %s" % (element_type, address)
    elif element_type == "BLOCK_OUTPUT":
        expression = _clean(element.get("expression"))
        text = "执行 %s" % (expression or "输出指令")
    else:
        text = "执行 %s" % (address or element_type or "输出动作")
    return _with_element_label(text.strip(), element)


def _branch_conditions(rung: Mapping[str, Any], branch: Mapping[str, Any]) -> str:
    elements = []
    header = rung.get("header_element")
    if isinstance(header, Mapping):
        elements.append(header)
    elements.extend(
        item for item in (rung.get("shared_inputs") or []) if isinstance(item, Mapping)
    )
    elements.extend(
        item for item in (branch.get("inputs") or []) if isinstance(item, Mapping)
    )
    conditions = [_condition_description(item) for item in elements]
    return "且".join(item for item in conditions if item)


def describe_ladder_path(path: Any, finding: Mapping[str, Any]) -> str:
    """Turn an exact report anchor into an operator-readable ladder sentence."""

    raw_path = _clean(path)
    base_ladder = finding.get("_base_ladder")
    if not isinstance(base_ladder, Mapping):
        return ""
    rungs = base_ladder.get("rungs")
    rung_index = rung_index_from_path(raw_path)
    if not isinstance(rungs, list) or rung_index is None or rung_index >= len(rungs):
        return ""
    rung = rungs[rung_index]
    if not isinstance(rung, Mapping):
        return ""
    display_number = _primary_rung_for_path(finding, raw_path) or (rung_index + 1)
    branches = rung.get("branches") or []
    branch_match = _BRANCH_INDEX_RE.search(raw_path)
    branch_index = int(branch_match.group(1)) if branch_match else 0
    if not isinstance(branches, list) or branch_index >= len(branches):
        return ""
    branch = branches[branch_index]
    if not isinstance(branch, Mapping):
        return ""

    output_match = _OUTPUT_INDEX_RE.search(raw_path)
    if output_match:
        output_index = int(output_match.group(1))
        outputs = branch.get("outputs") or []
        if isinstance(outputs, list) and output_index < len(outputs):
            action = _output_description(outputs[output_index])
            conditions = _branch_conditions(rung, branch)
            if action:
                if conditions:
                    return "梯级 %s：%s时%s" % (
                        display_number,
                        conditions,
                        action,
                    )
                return "梯级 %s：%s" % (display_number, action)

    input_match = _INPUT_INDEX_RE.search(raw_path)
    if input_match or ".header_element" in raw_path:
        conditions = _branch_conditions(rung, branch)
        if conditions:
            return "梯级 %s：条件为 %s" % (display_number, conditions)

    # A whole rung/branch anchor can still be summarized by its first action.
    outputs = branch.get("outputs") or []
    if isinstance(outputs, list) and outputs:
        action = _output_description(outputs[0])
        conditions = _branch_conditions(rung, branch)
        if action:
            return "梯级 %s：%s%s" % (
                display_number,
                (conditions + "时") if conditions else "",
                action,
            )
    return ""


def _replace_json_paths(text: str, finding: Mapping[str, Any]) -> str:
    def replace(match):
        path = match.group(0)
        rung_id = _primary_rung_for_path(finding, path)
        return describe_json_path(path, rung_id=rung_id)

    rendered = _JSON_PATH_RE.sub(replace, text)
    rendered = rendered.replace("confirmed_spec.io_table", "已确认 I/O 表")
    rendered = rendered.replace("基础 JSON", "当前版本程序")
    rendered = rendered.replace("base JSON", "当前版本程序")
    rendered = re.sub(r"指令类型\s*=\s*", "指令类型为 ", rendered)
    return naturalize_display_text(rendered)


def describe_evidence_item(value: Any, finding: Optional[Mapping[str, Any]] = None) -> str:
    finding = finding or {}
    if isinstance(value, Mapping):
        message = _clean(
            value.get("message")
            or value.get("description")
            or value.get("observed")
            or value.get("value")
        )
        path = _clean(value.get("json_path") or value.get("path"))
        rung = value.get("rung_id")
        address = _clean(value.get("address"))
        display_rung = _primary_rung_for_path(finding, path) if path else None
        semantic_location = describe_ladder_path(path, finding) if path else ""
        location = semantic_location or (
            describe_json_path(
                path,
                rung_id=display_rung if display_rung is not None else rung,
            )
            if path
            else ""
        )
        parts = []
        if address:
            parts.append("元件 %s" % address.upper())
        if location:
            parts.append(location)
        if message:
            parts.append(_replace_json_paths(message, finding))
        return "：".join(parts) if parts else "证据内容不完整"

    raw = _clean(value)
    if not raw:
        return ""
    pure_path = bool(_PURE_JSON_PATH_RE.fullmatch(raw))
    if pure_path:
        semantic = describe_ladder_path(raw, finding)
        if semantic:
            return semantic
    rendered = _replace_json_paths(raw, finding)
    if pure_path:
        addresses = finding.get("addresses") or []
        if isinstance(addresses, str):
            addresses = [addresses]
        address_text = "、".join(_unique_strings(addresses))
        prefix = "%s 的相关位置" % address_text if address_text else "相关位置"
        return "%s：%s" % (prefix, rendered)
    return rendered


def evidence_lines(finding: Mapping[str, Any]) -> List[str]:
    value = finding.get("evidence")
    if value is None:
        return []
    if isinstance(value, Mapping):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return _unique_strings(describe_evidence_item(item, finding) for item in values)


def _verified_evidence_rungs(finding: Mapping[str, Any]) -> List[str]:
    display_map = finding.get("_rung_display_map") or {}
    verified_map = finding.get("_rung_index_map") or {}
    if not display_map and (not isinstance(verified_map, Mapping) or not verified_map):
        return []
    evidence = finding.get("evidence") or []
    if isinstance(evidence, (str, Mapping)):
        evidence = [evidence]
    paths = []
    if isinstance(evidence, Sequence):
        for item in evidence:
            if isinstance(item, Mapping):
                path = _clean(item.get("json_path") or item.get("path"))
                if path:
                    paths.append(path)
            else:
                paths.extend(match.group(0) for match in _JSON_PATH_RE.finditer(_clean(item)))
    primary_path = _clean(finding.get("json_path") or finding.get("path"))
    if primary_path:
        paths.append(primary_path)
    raw_paths = finding.get("json_paths") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if isinstance(raw_paths, Sequence):
        paths.extend(_clean(item) for item in raw_paths if _clean(item))
    result = []
    for path in paths:
        display_number = display_number_for_anchor(display_map, json_path=path)
        if display_number is not None:
            result.append(display_number)
            continue
        match = _RUNG_INDEX_RE.search(path)
        if not match:
            continue
        index = int(match.group(1))
        rung = verified_map.get(index)
        if rung is None:
            rung = verified_map.get(str(index))
        if rung not in (None, ""):
            result.append(rung)
    return _unique_strings(result)


def _rung_values(finding: Mapping[str, Any]) -> List[str]:
    verified = _verified_evidence_rungs(finding)
    if verified:
        return verified
    values = []
    rung = finding.get("rung_id")
    if rung not in (None, ""):
        values.append(rung)
    raw = finding.get("rung_ids") or finding.get("related_rungs") or []
    if isinstance(raw, (str, int)):
        raw = [raw]
    if isinstance(raw, Sequence):
        values.extend(raw)
    display_map = finding.get("_rung_display_map") or {}
    if display_map:
        display_values = []
        for raw_rung in values:
            display_number = display_number_for_anchor(
                display_map,
                raw_rung_id=raw_rung,
            )
            display_values.append(
                display_number if display_number is not None else raw_rung
            )
        values = display_values
    return _unique_strings(values)


def location_text(finding: Mapping[str, Any], limit: int = 5) -> str:
    """Build the visible location summary without exposing JSON paths."""

    parts = []
    rungs = _rung_values(finding)
    if rungs:
        visible = rungs[: max(1, limit)]
        if len(rungs) == 1:
            parts.append("梯级 %s" % visible[0])
        elif len(rungs) <= limit:
            parts.append("涉及梯级 " + "、".join(visible))
        else:
            parts.append(
                "涉及梯级 %s 等（共 %d 个）" % ("、".join(visible), len(rungs))
            )
    else:
        path = _clean(finding.get("json_path") or finding.get("path"))
        if not path:
            raw_paths = finding.get("json_paths") or []
            if isinstance(raw_paths, Sequence) and not isinstance(raw_paths, str) and raw_paths:
                path = _clean(raw_paths[0])
        if path:
            parts.append(describe_json_path(path))

    addresses = finding.get("addresses") or finding.get("address") or []
    if isinstance(addresses, str):
        addresses = [addresses]
    address_values = _unique_strings(addresses)
    if address_values:
        parts.append("涉及元件 " + "、".join(address_values))
    return " · ".join(parts)


def technical_location_tooltip(finding: Mapping[str, Any]) -> str:
    """Describe precise binding without exposing raw implementation paths."""

    paths = []
    primary = _clean(finding.get("json_path") or finding.get("path"))
    if primary:
        paths.append(primary)
    raw_paths = finding.get("json_paths") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if isinstance(raw_paths, Sequence):
        paths.extend(raw_paths)
    paths = _unique_strings(paths)
    raw_rung = finding.get("_locate_raw_rung_id")
    if raw_rung in (None, ""):
        raw_rung = finding.get("rung_id")
    if not paths and raw_rung in (None, ""):
        return ""
    lines = ["程序位置已在内部精确绑定，点击“定位”可直接跳转。"]
    if raw_rung not in (None, ""):
        lines.append(
            "关联位置：%s"
            % naturalize_identifier(f"rung_{raw_rung}", kind="梯级")
        )
    if paths:
        lines.append("关联程序位置：%d 处" % len(paths))
    return "\n".join(lines)


__all__ = [
    "category_label",
    "confidence_label",
    "describe_evidence_item",
    "describe_json_path",
    "describe_ladder_path",
    "evidence_lines",
    "location_text",
    "resolution_label",
    "rung_display_map",
    "rung_index_map",
    "source_label",
    "technical_location_tooltip",
]
