# GX Works2 Structured Ladder/FBD `.gxw` reverse-engineering notes

> Status: experimental, read-only research. Findings below come from controlled FX3U / GX Works2 samples 48-53 created on 2026-09-06. They are deliberately scope-limited until more GX Works2 versions, PLC families, POU types, labels, FBs and network shapes are tested.

## Goal

The first implementation target is a deterministic read-only path:

```text
GXW
  -> outer CFB reader
  -> _hdb nested CFB
  -> projectdatalist.xml logical-file resolver
  -> *.Program.pou
  -> Structured Ladder/FBD record parser
  -> nodes + wires
  -> future PLC IR / Structured Ladder AST
```

Direct `.gxw` writing is intentionally out of scope for this milestone.

## Controlled samples 48-53

| Sample | Change / program |
|---|---|
| `48_STRUCT_X1_Y1.gxw` | direct device: `X1 -> Y1` |
| `49_STRUCT_GLOBAL_LABEL_X1_Y1.gxw` | same graph, `input_x1 -> X1`, `output_y1 -> Y1` through global labels |
| `50_STRUCT_NC_X1_Y1.gxw` | normally-closed `X1 -> Y1` |
| `51_STRUCT_SERIES_X1_M1_Y1.gxw` | `X1 -- M1 -> Y1` |
| `52_STRUCT_PARALLEL_X1_X2_Y1.gxw` | parallel `X1 / X2 -> Y1` |
| `53_STRUCT_MOV_K10_D1(1).gxw` | `X1` enables built-in `MOV`, input value `10`, output `D1` |

The filename of sample 53 contains `(1)` only because of the local saved-file name; it is not part of the GX format.

## Project-object resolution

Structured-project samples contain an outer Microsoft Compound File Binary (CFB/OLE) container and a nested CFB stream named `_hdb`.

`projectdatalist.xml` provides the current logical-object mapping. In the controlled project it includes entries such as:

```text
12 -> MAIN.res
14 -> Global1.gh
15 -> 1.Labels.lh
16 -> 1.Program.pou
```

The numeric `_hdb` stream IDs must not be hard-coded. The parser resolves them from `projectdatalist.xml`.

## Structured `1.Program.pou` layout

For samples 48-53, the record area starts at offset `0x5F`.

Observed fields:

```text
0x47 uint32  body_size      == file_size - 0x5F
0x57 uint32  canvas_height  (strongly supported by samples 48-53)
0x5B uint32  record_count
0x5F ...     variable-length records
             24 zero trailer bytes
```

The first `uint32` of every record is its byte length, so records can be parsed sequentially.

Two record classes are currently verified:

```text
record_class = 1 -> node
record_class = 2 -> wire
```

## Node record

The controlled samples support this structure:

```text
uint32 record_length
uint32 record_class       # 1
uint32 node_kind
uint32 symbol_char_count  # includes terminating NUL
utf16le symbol[symbol_char_count]
uint32 object_flag        # observed 1
uint16 reserved           # observed 0
uint32 left
uint32 top
uint32 right
uint32 bottom
uint32 port_count
PortDescriptor ports[port_count]
```

`PortDescriptor` is currently structurally decoded but its semantic fields are not yet named:

```text
uint32 size               # observed 16
uint32 field_a
uint32 field_b
uint32 field_c
```

Verified node-kind codes:

| Code | Meaning | Evidence |
|---:|---|---|
| `0x01` | built-in Function node | `MOV` in sample 53 |
| `0x03` | normally-open Contact | X1/M1/X2 samples |
| `0x04` | normally-closed Contact | sample 50 |
| `0x05` | Coil | Y1 samples |
| `0x0D` | Input/value node | `10` in sample 53 |
| `0x0E` | Output/value node | `D1` in sample 53 |

The symbol is stored directly as UTF-16LE text. Examples:

```text
Contact: "X1"
Contact with global label: "input_x1"
Coil with global label: "output_y1"
Function: "MOV"
Input node: "10"
Output node: "D1"
```

The direct-device and global-label samples show that the program node stores the symbol string; global-label binding is held separately in `Global1.gh`.

## Wire record

All wires in samples 48-53 are 44 bytes. The currently useful decoded portion is:

```text
uint32 record_length      # 44
uint32 record_class       # 2
...                       # currently unnamed flags/fields
uint32 start_x            # offset 24
uint32 start_y            # offset 28
uint32 end_x              # offset 32
uint32 end_y              # offset 36
uint32 suffix             # offset 40, observed 0
```

The first 24 bytes are preserved raw / as unnamed fields until their semantics are proven.

## Sample 52: explicit graph structure

`52_STRUCT_PARALLEL_X1_X2_Y1.gxw` parses to:

```text
Contact X1 @ (6,1)-(8,3)
Coil Y1    @ (22,1)-(24,3)
Contact X2 @ (6,4)-(8,6)

Wire (1,0) -> (1,6)
Wire (1,2) -> (6,2)
Wire (6,2) -> (6,5)
Wire (8,2) -> (8,5)
Wire (8,2) -> (22,2)
```

This is decisive evidence that Structured Ladder/FBD `1.Program.pou` preserves an editor graph (nodes, coordinates and wires), unlike the ordinary Ladder `MAIN.Program.pou` samples that primarily exposed Mitsubishi mnemonic-like instruction tokens.

## Sample 53: MOV is a graph object

`53_STRUCT_MOV_K10_D1(1).gxw` parses to four nodes:

```text
Function MOV @ (22,0)-(29,4)   port_count=4
Contact X1  @ (6,1)-(8,3)      port_count=2
Input 10    @ (20,2)-(22,4)    port_count=1
Output D1   @ (29,2)-(31,4)    port_count=1
```

and three wires:

```text
Wire (1,0) -> (1,6)
Wire (1,2) -> (6,2)
Wire (8,2) -> (22,2)
```

The Structured Ladder/FBD source stores the constant as the symbol string `"10"`, not the ordinary-Ladder mnemonic spelling `K10`.

The MOV node contains four 16-byte port descriptors, consistent with its visible `EN`, `ENO`, `s`, `d` ports. The three descriptor fields are intentionally left unnamed pending control samples with different functions and port layouts.

## Global-label separation (48 vs 49)

The program graph geometry remains the same while direct device symbols change to labels:

```text
48: X1       -> Y1
49: input_x1 -> output_y1
```

Observed sizes:

```text
1.Program.pou: 411 -> 437 bytes
Global1.gh:      58 -> 296 bytes
1.Labels.lh:    110 -> 110 bytes (save-time changes aside)
MAIN.res:       142 -> 142 bytes
```

The `1.Program.pou` growth is accounted for by the longer UTF-16LE symbol strings. This supports a symbol-based node reference rather than a separately observed global-label ID in these node records.

`Global1.gh` contains the global-label definitions/bindings. `1.Labels.lh` appears to be POU-local label state and did not gain the global-label records in this pair.

## Correction: `MAIN.res` is derived/stale unless compiled

A prior working hypothesis treated Structured Project `MAIN.res` as the current compiled equivalent of `1.Program.pou` after every save. Samples 48-53 disprove that assumption.

Across those samples, `MAIN.res` remained byte-identical while `1.Program.pou` changed and its update timestamp advanced. Therefore:

- `1.Program.pou` is the current saved Structured Ladder/FBD editor model.
- `MAIN.res` is derived/compiled state and may be stale when the user edits/saves without recompiling.
- a read-only source parser must prefer the current `*.Program.pou`, not infer current Structured Ladder logic from `MAIN.res`.

## First read-only parser

The initial implementation is under `src/gxw/`:

```text
src/gxw/
├─ __init__.py
├─ container.py
├─ project_resolver.py
├─ structured_pou.py
├─ models.py
└─ decoder.py
```

Example:

```bash
python -m src.gxw.decoder 52_STRUCT_PARALLEL_X1_X2_Y1.gxw
```

Expected core output:

```text
Contact X1 @ (6,1)-(8,3)
Coil Y1 @ (22,1)-(24,3)
Contact X2 @ (6,4)-(8,6)
Wire (1,0) -> (1,6)
Wire (1,2) -> (6,2)
Wire (6,2) -> (6,5)
Wire (8,2) -> (8,5)
Wire (8,2) -> (22,2)
```

The parser is fail-closed: unsupported structural invariants raise `GXWFormatError` instead of guessing.

## Next samples

After the parser is in place, add samples only to answer specific unknowns, especially:

- function/FB port descriptor semantics;
- additional node kinds (comparison, timer/counter, FB instance, connector, label/local variable);
- multiple networks/pages and multiple POU objects;
- local-label encoding in `*.Labels.lh`;
- global-label schema in `*.gh`;
- compile-state relation between `*.Program.pou`, `MAIN.res`, and other derived streams.

Keep unknown fields raw until controlled samples prove their meanings.
