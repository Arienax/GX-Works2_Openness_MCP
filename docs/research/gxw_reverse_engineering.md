# GX Works2 `.gxw` reverse-engineering notes

> Status: experimental / reverse-engineered from controlled FX3U samples created in GX Works2 on 2026-09-05.
>
> These observations are intended to support a future **read-only GXW parser**. Do not treat offsets or encodings as universal until they are validated against more PLC families, project layouts, POU types, GX Works2 versions, and structured-ladder projects.

## Goal

The long-term path under investigation is:

```text
GXW
  -> container reader
  -> project object resolver
  -> Program.pou tokenizer
  -> Mitsubishi instruction decoder
  -> PLC IR
```

Writing `.gxw` directly is a separate, higher-risk problem because a project contains duplicated/derived data, metadata, hashes and compiler state. The first milestone should therefore be a deterministic read-only parser.

## Controlled sample method

Each sample changes one variable where possible. The currently analyzed set includes:

- `00_empty.gxw`
- `02_X0_Y0.gxw`
- `03_X1_Y0.gxw`
- `04_X1_Y1.gxw`
- `05_add_comment.gxw` (`X1` device comment changed to `"1"`)
- `06_X2_Y1.gxw`
- `07_X10_Y1.gxw`
- `08_X100_Y1.gxw`
- `09_M1_Y1.gxw`
- `10_MOV_K10_D1.gxw` through `36_DSUB_D0_D2_D4.gxw`

The filenames beginning with `DM0V` contain a digit zero in the filename only; the actual GX Works2 instruction is `DMOV`.

## Container structure

Observed `.gxw` files are Microsoft Compound File Binary (CFB/OLE) containers rather than a single opaque program blob.

Observed high-level structure:

```text
GXW (outer CFB)
├─ checkout.xml
├─ dataprotection.xml
├─ history.xml
├─ label.xml
├─ projectdatalist.xml
├─ projectlist.xml
├─ ...
└─ _hdb
   └─ nested CFB
      ├─ numbered streams
      ├─ MAIN.res
      ├─ MAIN.Program.pou
      ├─ COMMENT.qcd
      ├─ ESCompiler.stg
      └─ Gppw2.gpj
```

In the current sample project, `history.xml` maps numbered streams to logical files. Observed mappings included:

```text
12 -> MAIN.res
16 -> MAIN.Program.pou
19 -> COMMENT.qcd
37 -> ESCompiler.stg
39 -> Gppw2.gpj
```

**Do not hard-code these numeric stream IDs.** A parser should resolve logical object names from the project metadata (`history.xml`, `projectdatalist.xml`, etc.). Different projects can assign different IDs.

## `MAIN.Program.pou`

### Observed layout

For the current controlled sample set, the instruction token stream begins at offset `0x4F`.

Other observed fields:

- `0x22`: a Windows `SYSTEMTIME`-shaped timestamp block (`WORD Year`, `Month`, `DayOfWeek`, `Day`, `Hour`, `Minute`, `Second`, `Milliseconds`). This is save-time noise for diffing purposes.
- `0x37`: little-endian `uint32` length-like field.
- `0x3B`: duplicate of the same length-like field.
- observed relation: `field_at_0x37 == token_stream_length + 20`.
- observed file-length relation: `file_size == 0x4F + token_stream_length + 24`.
- observed trailer: 24 zero bytes after the token stream.

These offsets are **sample-layout observations**, not yet proven format invariants.

### Token framing

Instruction and operand tokens observed so far use matching leading/trailing length bytes:

```text
[length] [payload ...] [length]
```

Examples:

```text
03 00 03
04 9C 01 04
05 E8 00 01 05
```

This enables sequential tokenization without searching for magic byte patterns.

## Basic instruction tokens

Observed basic instruction opcodes:

| Instruction | Token | Evidence |
|---|---|---|
| `LD` | `03 00 03` | `X1` input samples |
| `OUT` | `03 20 03` | `Y1` output samples |
| `SET` | `03 23 03` | `23_SET_M1.gxw` |
| `RST` | `03 24 03` | `24_RST_M1.gxw` |
| `END` | `03 34 03` | all completed program samples |

Example:

```text
LD X1
SET M1
END

03 00 03
04 9C 01 04
03 23 03
04 90 01 04
03 34 03
```

## Operand tokens

### Device / constant type codes

Observed type bytes:

| Operand class | Type byte | Notes |
|---|---:|---|
| `M` | `0x90` | bit device |
| `X` | `0x9C` | input |
| `Y` | `0x9D` | output |
| `D` | `0xA8` | data register |
| `K` 16-bit semantic constant | `0xE8` | decimal constant |
| `K` 32-bit semantic constant | `0xE9` | decimal constant in double-word context |
| `H` | `0xEA` | hexadecimal constant |

### Small operand shape

Observed general form:

```text
[length] [type] [little-endian value bytes ...] [length]
```

Examples:

```text
X1   -> 04 9C 01 04
M1   -> 04 90 01 04
Y1   -> 04 9D 01 04
D1   -> 04 A8 01 04
D10  -> 04 A8 0A 04
K10  -> 04 E8 0A 04
K11  -> 04 E8 0B 04
H10  -> 04 EA 10 04
```

### Numeric address encoding

Addresses are stored as parsed numeric values, not display strings.

For FX-series octal X addresses:

```text
X1   -> 0x01
X2   -> 0x02
X10  -> 0x08
X100 -> 0x40
```

This strongly indicates GX Works2 converts the displayed octal X/Y address into its numeric value before serialization.

Values greater than `0xFF` expand naturally in little-endian form:

```text
K255 -> 04 E8 FF 04
K256 -> 05 E8 00 01 05

D255 -> 04 A8 FF 04
D256 -> 05 A8 00 01 05
```

### Signed constants and semantic width

The constant type byte carries width semantics; raw payload length alone is insufficient to determine signedness/width.

Observed:

```text
MOV  K-1 D1  -> E8 FF FF
DMOV K-1 D0  -> E9 FF FF FF FF

MOV  K32767 D0  -> E8 FF 7F
DMOV K32767 D0  -> E9 FF 7F
DMOV K1 D0      -> E9 01
DMOV K32768 D0  -> E9 00 80
```

Current interpretation:

- `0xE8`: decimal `K` constant in 16-bit semantic context.
- `0xE9`: decimal `K` constant in 32-bit semantic context.
- negative values are serialized using two's-complement at the semantic width.
- positive values may use a shorter magnitude payload, so the parser must preserve the operand type byte and raw bytes before semantic interpretation.

## Application-instruction header

Observed application instructions use a five-byte header token:

```text
05 FAMILY WIDTH_OR_SLOT_DESCRIPTOR SUBTYPE 05
```

The third byte currently follows this verified rule for the tested instructions:

```text
width_descriptor = 1 + 2 * total_operand_word_slots
```

Examples:

```text
MOV:   2 x 16-bit operands -> 2 word slots -> 1 + 2*2 = 0x05
DMOV:  2 x 32-bit operands -> 4 word slots -> 1 + 2*4 = 0x09
ADD:   3 x 16-bit operands -> 3 word slots -> 1 + 2*3 = 0x07
DADD:  3 x 32-bit operands -> 6 word slots -> 1 + 2*6 = 0x0D
BMOV:  D,D,K              -> 3 word slots -> 1 + 2*3 = 0x07
INC:   1 x 16-bit operand -> 1 word slot  -> 1 + 2*1 = 0x03
```

### Arithmetic family (`0x49`)

Observed:

```text
ADD   D1 D2 D3 -> 05 49 07 28 05
SUB   D1 D2 D3 -> 05 49 07 2A 05
MUL   D1 D2 D3 -> 05 49 07 2C 05
DIV   D1 D2 D3 -> 05 49 07 2E 05
DADD  D0 D2 D4 -> 05 49 0D 29 05
DSUB  D0 D2 D4 -> 05 49 0D 2B 05
```

For the tested arithmetic instructions:

```text
subtype/opcode = FNC_number * 2 + D_modifier
```

where `D_modifier` is `0` for the normal word form and `1` for the tested double-word form.

Examples:

```text
ADD  FNC20 -> 20*2 = 0x28
DADD       -> 0x28 + 1 = 0x29
SUB  FNC21 -> 21*2 = 0x2A
DSUB       -> 0x2A + 1 = 0x2B
MUL  FNC22 -> 0x2C
DIV  FNC23 -> 0x2E
```

Do not assume this arithmetic-family relation applies to every GX Works2 instruction family until separately verified.

### INC/DEC family (`0x4A`)

Observed:

```text
INC D1 -> 05 4A 03 00 05
DEC D1 -> 05 4A 03 02 05
```

Current hypothesis: family-relative subtype based on a family base instruction. More samples are required before generalizing.

### MOV family (`0x4C`)

Observed:

```text
MOV  K10 D1    -> 05 4C 05 00 05
DMOV D1 D10    -> 05 4C 09 01 05
DMOV K32768 D0 -> 05 4C 09 01 05
BMOV D0 D10 K5 -> 05 4C 07 06 05
```

Current interpretation:

- `0x4C` identifies a MOV-like instruction family.
- subtype `0x00` is observed for MOV.
- subtype `0x01` is observed for DMOV.
- subtype `0x06` is observed for BMOV.
- DMOV appears to be represented as MOV-family + double-word variant rather than an unrelated top-level opcode.

A plausible family-relative rule is:

```text
subtype = 2 * (FNC - family_base) + D_modifier
```

For MOV/BMOV this matches the current samples with `family_base = FNC12`, but this remains a hypothesis until more members of the family are tested.

## `COMMENT.qcd`

Adding a device comment `"1"` to `X1` did **not** change `MAIN.Program.pou`, but increased `COMMENT.qcd` from 60 bytes to 82 bytes in the controlled sample.

The changed region contains evidence consistent with:

```text
X type code: 0x9C
X1 address:   0x01
text bytes:   31 00   # UTF-16LE "1"
```

Conclusion: device comments are stored separately from the ladder instruction body. `COMMENT.qcd` should be parsed as a separate logical object rather than inferred from `Program.pou`.

The exact `COMMENT.qcd` record schema is not yet fully decoded.

## `MAIN.res` duplication

For the controlled samples, `MAIN.res` contains a byte-identical copy of the instruction token stream found in `MAIN.Program.pou` (at a different offset).

Implication:

- a read-only parser can prioritize `MAIN.Program.pou`.
- a future writer cannot safely update only `MAIN.Program.pou`; duplicated/derived representations and project metadata would also need consistent updates.

## `ESCompiler.stg` and `Gppw2.gpj`

Both can change when ladder content changes. Current evidence suggests they contain compiler/project-management state rather than being the preferred source of truth for decoding the ladder program.

For the initial reader, treat them as opaque derived state until evidence requires otherwise.

## Provisional grammar

A useful first approximation is:

```text
Program := Header Instruction* END Trailer

Instruction :=
    BasicInstruction
  | ApplicationInstruction

BasicInstruction :=
    [03 opcode 03]
    Operand*

ApplicationInstruction :=
    [05 family width_descriptor subtype 05]
    Operand*

Operand :=
    [length type value_le... length]
```

The decoder still needs an instruction registry to determine the number, role and semantic width of operands after an instruction header.

## Parser design constraints

A first implementation should:

1. Parse the outer CFB container.
2. Locate and parse project metadata rather than hard-coding numbered stream IDs.
3. Resolve `MAIN.Program.pou` by logical name.
4. Keep raw token bytes alongside decoded semantic values.
5. Validate matching token length sentinels.
6. Treat observed fixed offsets as version/layout-specific until proven otherwise.
7. Decode instructions through a registry, not a large handwritten `if/elif` chain.
8. Preserve unknown tokens instead of guessing semantics.
9. Remain read-only until duplicated project state, hashes/checksums and writer invariants are understood.

Suggested internal form:

```python
@dataclass
class RawGXWToken:
    offset: int
    raw: bytes
    kind: str

@dataclass
class GXWOperand:
    type_code: int
    raw_value: bytes
    semantic_width_bits: int | None
    decoded: object | None

@dataclass
class GXWInstruction:
    family: int | None
    opcode: int
    width_descriptor: int | None
    operands: list[GXWOperand]
    raw_tokens: list[RawGXWToken]
```

## Next controlled samples

The next samples should move from arithmetic encoding to **ladder topology**:

```text
37_SERIES_X1_M1_Y1.gxw
X1 NO -- M1 NO -- OUT Y1

38_PARALLEL_X1_X2_Y1.gxw
X1 NO || X2 NO -- OUT Y1

39_NC_X1_Y1.gxw
X1 NC -- OUT Y1

40_SERIES_X1_NC_M1_Y1.gxw
X1 NO -- M1 NC -- OUT Y1

41_TIMER_T0_K10.gxw
LD X1; OUT T0 K10

42_COUNTER_C0_K10.gxw
LD X1; OUT C0 K10
```

These experiments are intended to determine whether `Program.pou` is primarily an instruction sequence (`LD`/`AND`/`OR`/`OUT`) or whether it also encodes explicit ladder branch/merge graph structure.

## Confidence levels

Treat findings in three classes:

- **Verified across controlled pairs:** X/Y/M/D type codes listed above, K/H distinctions listed above, octal X numeric conversion, little-endian value expansion, SET/RST opcodes, arithmetic ADD/SUB/MUL/DIV/DADD/DSUB sample encodings, MOV/DMOV/BMOV sample encodings, width-descriptor relation for the tested instructions.
- **Strong but still scope-limited:** token framing, current `Program.pou` header/trailer relationships, `E8` vs `E9` semantic-width interpretation.
- **Hypotheses requiring more samples:** universal family-relative opcode formula, universal fixed offsets, full `COMMENT.qcd` schema, writer requirements.

Keep this document synchronized with machine-readable observations under `resources/gxw/` as the reverse-engineering corpus grows.
