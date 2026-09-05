from pathlib import Path


def replace_once(text, old, new, label):
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one source match, found {count}")
    return text.replace(old, new, 1)


def patch_validator():
    path = Path("src/plc_json_validator.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''        "C": 255,\n        "S": 4095,\n    },\n    "FX5U": {''',
        '''        "C": 255,\n        "S": 4095,\n        # FX3U index registers. V0-V7 are 16-bit index registers; Z0-Z7\n        # are accepted as index registers and may also be used as ordinary\n        # word operands. Indexed operands such as D100Z0 are validated below.\n        "V": 7,\n        "Z": 7,\n    },\n    "FX5U": {''',
        "validator FX3U V/Z limits",
    )

    text = replace_once(
        text,
        '''DEVICE_ADDRESS_RE = re.compile(r"^(SM|SD|X|Y|M|D|T|C|S)(\\d+)$", re.IGNORECASE)\nDEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])(?:SM|SD|X|Y|M|D|T|C|S)\\d+(?![A-Z0-9_])",\n    re.IGNORECASE,\n)''',
        '''DEVICE_ADDRESS_RE = re.compile(\n    r"^(SM|SD|X|Y|M|D|T|C|S|V|Z)(\\d+)$", re.IGNORECASE\n)\nINDEXED_DEVICE_ADDRESS_RE = re.compile(\n    r"^(?P<base>(?:SM|SD|X|Y|M|D|T|C|S)\\d+)(?P<index>[VZ]\\d+)$",\n    re.IGNORECASE,\n)\nINDEXED_DEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])(?:SM|SD|X|Y|M|D|T|C|S)\\d+[VZ]\\d+(?![A-Z0-9_])",\n    re.IGNORECASE,\n)\nDEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])(?:SM|SD|X|Y|M|D|T|C|S|V|Z)\\d+(?![A-Z0-9_])",\n    re.IGNORECASE,\n)''',
        "validator device regexes",
    )

    text = replace_once(
        text,
        '''    return prefix, index\n\n\ndef _is_read_only_special_device(value, plc_model="FX3U"):''',
        '''    return prefix, index\n\n\ndef parse_indexed_device_address(value, plc_model="FX3U"):\n    """Parse an FX-style indexed operand such as ``D100Z0``.\n\n    The legacy external JSON keeps the operand as a string.  This helper only\n    validates and decomposes it so the validator/IR can reason about the base\n    device and the index register without changing that interchange format.\n    """\n\n    model = normalize_plc_model(plc_model)\n    if not isinstance(value, str):\n        return None\n    match = INDEXED_DEVICE_ADDRESS_RE.fullmatch(value.strip())\n    if not match:\n        return None\n    base_text = match.group("base").upper()\n    index_text = match.group("index").upper()\n    base = parse_device_address(base_text, model)\n    index = parse_device_address(index_text, model)\n    if base is None or index is None or index[0] not in {"V", "Z"}:\n        return None\n    return {\n        "base_text": base_text,\n        "index_text": index_text,\n        "base": base,\n        "index": index,\n    }\n\n\ndef _validate_indexed_device_address(value, path, plc_model="FX3U"):\n    if not isinstance(value, str):\n        return None\n    match = INDEXED_DEVICE_ADDRESS_RE.fullmatch(value.strip())\n    if not match:\n        return None\n    base_text = match.group("base").upper()\n    index_text = match.group("index").upper()\n    _validate_device_address(base_text, path, plc_model)\n    _validate_device_address(\n        index_text, path, plc_model, expected_prefixes={"V", "Z"}\n    )\n    return {"base_text": base_text, "index_text": index_text}\n\n\ndef _operand_base_device(value):\n    text = str(value or "").strip().upper()\n    match = INDEXED_DEVICE_ADDRESS_RE.fullmatch(text)\n    return match.group("base").upper() if match else text\n\n\ndef _is_read_only_special_device(value, plc_model="FX3U"):''',
        "validator indexed parser",
    )

    text = replace_once(
        text,
        '''    address = value.strip().upper()\n    if _is_read_only_special_device(address, plc_model):''',
        '''    address = value.strip().upper()\n    indexed = parse_indexed_device_address(address, plc_model)\n    writable_address = indexed["base_text"] if indexed else address\n    if _is_read_only_special_device(writable_address, plc_model):''',
        "validator indexed write target",
    )

    text = replace_once(
        text,
        '''        addressing = "octal X/Y" if model == "FX3U" else "decimal X/Y and SM/SD specials"\n        _fail(path, f"invalid or unsupported {model} device address {value!r} ({addressing})")''',
        '''        addressing = (\n            "octal X/Y and V0-V7/Z0-Z7 index registers"\n            if model == "FX3U"\n            else "decimal X/Y and SM/SD specials"\n        )\n        _fail(path, f"invalid or unsupported {model} device address {value!r} ({addressing})")''',
        "validator address message",
    )

    text = replace_once(
        text,
        '''        expression_registers = {\n            token.upper()\n            for token in re.findall(r"\\bD\\d+\\b", expression, flags=re.IGNORECASE)\n        }\n        for token in DEVICE_TOKEN_RE.findall(expression):\n            _validate_device_address(token, f"{path}.expression", plc_model)''',
        '''        expression_registers = {\n            token.upper()\n            for token in re.findall(r"\\bD\\d+\\b", expression, flags=re.IGNORECASE)\n        }\n        indexed_tokens = INDEXED_DEVICE_TOKEN_RE.findall(expression)\n        for token in indexed_tokens:\n            indexed = _validate_indexed_device_address(\n                token, f"{path}.expression", plc_model\n            )\n            if indexed and indexed["base_text"].startswith("D"):\n                expression_registers.add(indexed["base_text"])\n        residual_expression = INDEXED_DEVICE_TOKEN_RE.sub(" ", expression)\n        for token in DEVICE_TOKEN_RE.findall(residual_expression):\n            _validate_device_address(token, f"{path}.expression", plc_model)''',
        "validator indexed expressions",
    )

    text = replace_once(
        text,
        '''        for operand_idx, operand in enumerate(operands):\n            if isinstance(operand, str) and DEVICE_ADDRESS_RE.fullmatch(operand.strip()):\n                _validate_device_address(\n                    operand, f"{path}.operands[{operand_idx}]", plc_model\n                )''',
        '''        for operand_idx, operand in enumerate(operands):\n            if not isinstance(operand, str):\n                continue\n            operand_path = f"{path}.operands[{operand_idx}]"\n            if INDEXED_DEVICE_ADDRESS_RE.fullmatch(operand.strip()):\n                _validate_indexed_device_address(operand, operand_path, plc_model)\n            elif DEVICE_ADDRESS_RE.fullmatch(operand.strip()):\n                _validate_device_address(operand, operand_path, plc_model)\n\n        # SET/RST are bit operations.  Accepting V/Z as word/index registers\n        # must not accidentally make them valid latch targets.\n        if opcode in {"SET", "RST"} and operands:\n            target = parse_device_address(operands[0], plc_model)\n            if target is not None and target[0] in {"V", "Z"}:\n                _fail(\n                    f"{path}.operands[0]",\n                    f"{opcode} requires a bit target; {operands[0]} is an index register",\n                )''',
        "validator APP_INSTR operands",
    )

    text = replace_once(
        text,
        '''                and operand.upper() in FX3U_DWORD_HIGH_WORDS\n            ):\n                register = operand.upper()''',
        '''                and _operand_base_device(operand) in FX3U_DWORD_HIGH_WORDS\n            ):\n                register = _operand_base_device(operand)''',
        "validator high-word indexed operand",
    )

    text = replace_once(
        text,
        '''                    and operand.upper() in FX3U_DWORD_REGISTER_MEMBERS\n                ):\n                    register = operand.upper()''',
        '''                    and _operand_base_device(operand) in FX3U_DWORD_REGISTER_MEMBERS\n                ):\n                    register = _operand_base_device(operand)''',
        "validator word-only indexed operand",
    )

    path.write_text(text, encoding="utf-8")


def patch_ir():
    path = Path("src/plc_ir.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''_DEVICE_RE = re.compile(r"^(SM|SD|X|Y|M|D|T|C|S)(\\d+)$", re.IGNORECASE)\n_DEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])(?:SM|SD|X|Y|M|D|T|C|S)\\d+(?![A-Z0-9_])",\n    re.IGNORECASE,\n)''',
        '''_DEVICE_RE = re.compile(\n    r"^(SM|SD|X|Y|M|D|T|C|S|V|Z)(\\d+)$", re.IGNORECASE\n)\n_INDEXED_DEVICE_RE = re.compile(\n    r"^(?P<base>(?:SM|SD|X|Y|M|D|T|C|S)\\d+)(?P<index>[VZ]\\d+)$",\n    re.IGNORECASE,\n)\n_DEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])"\n    r"(?:(?P<base>(?:SM|SD|X|Y|M|D|T|C|S)\\d+)(?P<index>[VZ]\\d+)"\n    r"|(?P<simple>(?:SM|SD|X|Y|M|D|T|C|S|V|Z)\\d+))"\n    r"(?![A-Z0-9_])",\n    re.IGNORECASE,\n)''',
        "IR device regexes",
    )

    text = replace_once(
        text,
        '''def _device_tokens(value: Any) -> List[str]:\n    text = str(value or "").upper()\n    return [match.group(0).upper() for match in _DEVICE_TOKEN_RE.finditer(text)]''',
        '''def _device_tokens(value: Any) -> List[str]:\n    """Return base devices plus index-register dependencies from an operand."""\n\n    text = str(value or "").upper()\n    result: List[str] = []\n    for match in _DEVICE_TOKEN_RE.finditer(text):\n        if match.group("base"):\n            result.append(match.group("base").upper())\n            result.append(match.group("index").upper())\n        else:\n            result.append(match.group("simple").upper())\n    return result''',
        "IR device token extraction",
    )

    text = replace_once(
        text,
        '''        "D": 6,\n        "SD": 7,\n        "S": 8,\n    }''',
        '''        "D": 6,\n        "SD": 7,\n        "S": 8,\n        "V": 9,\n        "Z": 10,\n    }''',
        "IR device sort order",
    )

    text = replace_once(
        text,
        '''    for index, operand in enumerate(operands or []):\n        tokens = set(_device_tokens(operand))\n        if index in write_indexes:\n            writes.update(tokens)\n            if index in read_write_indexes:\n                reads.update(tokens)\n        else:\n            reads.update(tokens)\n    return reads, writes''',
        '''    for index, operand in enumerate(operands or []):\n        text = str(operand or "").strip().upper()\n        indexed = _INDEXED_DEVICE_RE.fullmatch(text)\n        if indexed:\n            base = indexed.group("base").upper()\n            index_register = indexed.group("index").upper()\n            # The index register is always read to resolve the effective\n            # address.  For a write operand, only the base memory family is\n            # conservatively recorded as written; the external operand string\n            # remains D100Z0/X0V1/etc. in ladder/CSV artifacts.\n            reads.add(index_register)\n            if index in write_indexes:\n                writes.add(base)\n                if index in read_write_indexes:\n                    reads.add(base)\n            else:\n                reads.add(base)\n            continue\n\n        tokens = set(_device_tokens(operand))\n        if index in write_indexes:\n            writes.update(tokens)\n            if index in read_write_indexes:\n                reads.update(tokens)\n        else:\n            reads.update(tokens)\n    return reads, writes''',
        "IR indexed access semantics",
    )

    path.write_text(text, encoding="utf-8")


def patch_st_renderer():
    path = Path("src/plc_st_renderer.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''_ST_OPERAND_RE = re.compile(\n    r"^(?:(?:SM|SD|X|Y|M|D|T|C|S|R|V|Z)\\d+(?:\\.[0-9A-F])?|"\n    r"K-?\\d+|H[0-9A-F]+|E[-+]?\\d+(?:\\.\\d+)?|"\n    r"K\\d+(?:X|Y|M|S)\\d+|[PI]\\d+)$",\n    re.I,\n)''',
        '''_ST_OPERAND_RE = re.compile(\n    r"^(?:(?:(?:SM|SD|X|Y|M|D|T|C|S|R)\\d+(?:[VZ]\\d+)?|"\n    r"(?:V|Z)\\d+)(?:\\.[0-9A-F])?|"\n    r"K-?\\d+|H[0-9A-F]+|E[-+]?\\d+(?:\\.\\d+)?|"\n    r"K\\d+(?:X|Y|M|S)\\d+|[PI]\\d+)$",\n    re.I,\n)''',
        "ST indexed operand syntax",
    )
    path.write_text(text, encoding="utf-8")


def patch_confirmed_spec():
    path = Path("src/confirmed_spec.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''DEVICE_RE = re.compile(r"((?:SM|SD|[XYMTCSD])\\d+)", re.IGNORECASE)\nASSIGNMENT_RE = re.compile(\n    r"((?:SM|SD|[XYMTCSD])\\d+)\\s*=\\s*([^,\\n]+)",\n    re.IGNORECASE,\n)\nIO_KIND_ORDER = ("X", "Y", "M", "T", "C", "D", "S", "特殊")\n\n_EXACT_DEVICE_RE = re.compile(r"^(SM|SD|[XYMTCSD])(\\d+)$", re.IGNORECASE)\n_VALID_IO_KINDS = set(IO_KIND_ORDER)\n_SUGGESTED_IO_DEVICE_KINDS = {"X", "Y", "M", "T", "C", "D", "S"}''',
        '''DEVICE_RE = re.compile(r"((?:SM|SD|[XYMTCSDVZ])\\d+)", re.IGNORECASE)\nASSIGNMENT_RE = re.compile(\n    r"((?:SM|SD|[XYMTCSDVZ])\\d+)\\s*=\\s*([^,\\n]+)",\n    re.IGNORECASE,\n)\nIO_KIND_ORDER = ("X", "Y", "M", "T", "C", "D", "S", "V", "Z", "特殊")\n\n_EXACT_DEVICE_RE = re.compile(r"^(SM|SD|[XYMTCSDVZ])(\\d+)$", re.IGNORECASE)\n_VALID_IO_KINDS = set(IO_KIND_ORDER)\n_SUGGESTED_IO_DEVICE_KINDS = {"X", "Y", "M", "T", "C", "D", "S", "V", "Z"}''',
        "confirmed-spec device regexes",
    )

    text = replace_once(
        text,
        '''        "S": 4095,\n        "D": 8511,\n    },\n    "FX5U": {''',
        '''        "S": 4095,\n        "D": 8511,\n        "V": 7,\n        "Z": 7,\n    },\n    "FX5U": {''',
        "confirmed-spec FX3U V/Z limits",
    )

    text = replace_once(
        text,
        '''    maximum = _DEVICE_LIMITS[plc_model].get(prefix)\n    if maximum is None or number > maximum:\n        display_number = format(maximum, "o") if plc_model == "FX3U" and prefix in {"X", "Y"} else str(maximum)''',
        '''    maximum = _DEVICE_LIMITS[plc_model].get(prefix)\n    if maximum is None:\n        return (\n            f"{plc_model} 当前设备模型不支持 {prefix} 地址",\n            None,\n            prefix,\n            number,\n        )\n    if number > maximum:\n        display_number = format(maximum, "o") if plc_model == "FX3U" and prefix in {"X", "Y"} else str(maximum)''',
        "confirmed-spec unsupported prefix handling",
    )

    path.write_text(text, encoding="utf-8")


def patch_static_analyzer():
    path = Path("src/plc_static_analyzer.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''_DEVICE_RE = re.compile(r"^(SM|SD|X|Y|M|D|T|C|S)(\\d+)$", re.I)\n_DEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])(?:SM|SD|X|Y|M|D|T|C|S)\\d+(?![A-Z0-9_])",\n    re.I,\n)''',
        '''_DEVICE_RE = re.compile(r"^(SM|SD|X|Y|M|D|T|C|S|V|Z)(\\d+)$", re.I)\n_DEVICE_TOKEN_RE = re.compile(\n    r"(?<![A-Z0-9_])(?:SM|SD|X|Y|M|D|T|C|S|V|Z)\\d+(?![A-Z0-9_])",\n    re.I,\n)''',
        "static-analyzer V/Z devices",
    )
    path.write_text(text, encoding="utf-8")


def write_tests():
    path = Path("tests/test_index_register_operands.py")
    content = '''import pytest\n\nfrom confirmed_spec import _validate_device_address as validate_spec_device\nfrom plc_ir import analyze_instruction_access, build_plc_ir, ir_to_ladder\nfrom plc_json_validator import (\n    PLCJsonValidationError,\n    parse_device_address,\n    parse_indexed_device_address,\n    validate_ladder_full,\n)\nfrom plc_st_renderer import render_plc_ir_to_st\n\n\ndef app(opcode, *operands):\n    return {\n        "type": "APP_INSTR",\n        "opcode": opcode,\n        "operands": list(operands),\n        "label": "",\n    }\n\n\ndef rung(rung_id, output):\n    return {\n        "rung_id": rung_id,\n        "debug_note": "",\n        "header_element": None,\n        "shared_inputs": [{"type": "NO", "address": "M8000", "label": ""}],\n        "branches": [\n            {\n                "branch_id": 1,\n                "y_offset_level": 0,\n                "inputs": [],\n                "outputs": [output],\n            }\n        ],\n    }\n\n\ndef indexed_ladder():\n    return {\n        "device_comments": {\n            "Z0": "索引寄存器",\n            "V7": "索引寄存器",\n            "D100": "变址基址",\n        },\n        "rungs": [\n            rung(1, app("MOV", "K1", "Z0")),\n            rung(2, app("MOV", "D0", "D100Z0")),\n            rung(3, app("MOV", "D100V7", "D200")),\n        ],\n    }\n\n\ndef test_fx3u_v_z_ranges_are_validated():\n    assert parse_device_address("V0", "FX3U") == ("V", 0)\n    assert parse_device_address("V7", "FX3U") == ("V", 7)\n    assert parse_device_address("Z0", "FX3U") == ("Z", 0)\n    assert parse_device_address("Z7", "FX3U") == ("Z", 7)\n    assert parse_device_address("V8", "FX3U") is None\n    assert parse_device_address("Z8", "FX3U") is None\n\n\ndef test_fx3u_indexed_operands_are_decomposed_without_changing_text():\n    parsed = parse_indexed_device_address("D100Z0", "FX3U")\n    assert parsed["base_text"] == "D100"\n    assert parsed["index_text"] == "Z0"\n    assert parse_indexed_device_address("D100Z8", "FX3U") is None\n\n\ndef test_ladder_validator_accepts_v_z_and_indexed_operands():\n    ladder = indexed_ladder()\n    assert validate_ladder_full(ladder, plc_model="FX3U") is ladder\n\n\ndef test_index_registers_are_not_accepted_as_bit_contacts():\n    ladder = indexed_ladder()\n    ladder["rungs"][0]["shared_inputs"] = [\n        {"type": "NO", "address": "Z0", "label": "非法位触点"}\n    ]\n    with pytest.raises(PLCJsonValidationError, match="expected prefix"):\n        validate_ladder_full(ladder, plc_model="FX3U")\n\n\ndef test_invalid_index_range_is_not_silently_ignored():\n    ladder = indexed_ladder()\n    ladder["rungs"][1]["branches"][0]["outputs"] = [\n        app("MOV", "D0", "D100Z8")\n    ]\n    with pytest.raises(PLCJsonValidationError, match="Z8"):\n        validate_ladder_full(ladder, plc_model="FX3U")\n\n\ndef test_ir_tracks_index_register_as_read_dependency():\n    reads, writes = analyze_instruction_access("MOV", ["D0", "D100Z0"])\n    assert reads == ["D0", "Z0"]\n    assert writes == ["D100"]\n\n    reads, writes = analyze_instruction_access("MOV", ["D100V7", "D200"])\n    assert reads == ["D100", "V7"]\n    assert writes == ["D200"]\n\n    reads, writes = analyze_instruction_access("MOV", ["K1", "Z0"])\n    assert reads == []\n    assert writes == ["Z0"]\n\n\ndef test_ir_and_st_renderer_preserve_indexed_operand_spelling():\n    ladder = indexed_ladder()\n    program = build_plc_ir(ladder, plc_model="FX3U")\n    assert ir_to_ladder(program) == ladder\n    assert program["devices"]["Z0"]["access"] == "read_write"\n    assert program["devices"]["V7"]["access"] == "read"\n    st_text = render_plc_ir_to_st(program)\n    assert "D100Z0" in st_text\n    assert "D100V7" in st_text\n\n\ndef test_confirmed_spec_accepts_fx3u_v_z_but_not_out_of_range_values():\n    assert validate_spec_device("V0", "FX3U")[0] is None\n    assert validate_spec_device("Z7", "FX3U")[0] is None\n    assert validate_spec_device("Z8", "FX3U")[0] is not None\n'''\n    path.write_text(content, encoding="utf-8")\n

if __name__ == "__main__":
    patch_validator()
    patch_ir()
    patch_st_renderer()
    patch_confirmed_spec()
    patch_static_analyzer()
    write_tests()
    print("patched FX3U V/Z index-register support")
