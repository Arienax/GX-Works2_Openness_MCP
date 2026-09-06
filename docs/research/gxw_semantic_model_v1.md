# GXW Structured Ladder semantic model v1

> Status: experimental, read-only.
>
> Evidence base: controlled GX Works2 / FX3U Structured Ladder/FBD samples through 71.

## Purpose

The binary parser and `ConnectivityGraph` recover editor records and conductive nets, but they deliberately do not decide what a Function port means. `src/gxw/semantic.py` is the first semantic layer above that geometry.

```text
*.Program.pou
  -> StructuredProgram
  -> ConnectivityGraph
  -> StructuredSemanticModel
  -> future Structured Ladder lowering
  -> project-level plc_ir.py
```

The v1 model does **not** lower Structured Ladder directly into the canonical project PLC IR. It preserves that boundary until contacts/coils, FB instances, timers/counters and additional Function forms are understood well enough to lower without guessing.

## Modeled objects

### Function ports

The model classifies the Function-node port layouts verified by controlled samples:

```text
port_kind_code 3 on the left  -> incoming Function port
port_kind_code 2 on the right -> ordinary data result/output
port_kind_code 0 on the right -> ENO/execution-continuation-like output
```

When a single code-0 right port exists, the aligned code-3 left port is classified as `enable_in`; the remaining incoming ports are `data_in`.

Current semantic roles:

```text
enable_in
data_in
enable_out
data_out
unknown
```

Unknown layouts are retained and reported as semantic warnings rather than guessed.

### Source and sink terminals

Observed terminal node kinds are interpreted as graph roles:

```text
0x0D -> source terminal
0x0E -> sink terminal
```

The terminal `symbol` remains separate from the graph role. A source terminal may contain `X1`, `D0`, `10`, a label, or the observed unresolved placeholder `?`.

`?` is accepted by the binary/semantic parser and emitted as an `unresolved_terminal` semantic issue. It is not treated as a malformed GXW record.

### Function family identity and arity

Controlled samples prove that `-N` is not a universal Function suffix:

```text
ADD_E-2 / ADD_E-3
AND_E-2 / AND_E-3
```

are extensible families, while the fixed two-input function:

```text
DIV_E
```

has no `-2` suffix.

Therefore v1 uses a small evidence-backed family registry. Only registered extensible families interpret a trailing `-N` as declared data-input arity. Unknown symbols such as an unrelated `FOO-3` are preserved verbatim instead of being split speculatively.

Registry entries currently cover:

```text
ADD_E    extensible
AND_E    extensible
MOV      fixed, observed 1 data input
CMP      fixed, observed 2 data inputs
DIV_E    fixed, observed 2 data inputs
ABS      fixed, observed 1 data input
ABS_E    fixed, observed 1 data input
```

## Connectivity binding

Every semantic Function port and terminal keeps its `ConnectivityGraph` net index.

This means function-to-function execution flow does not need a special edge type. Sample 65 is represented by a shared net:

```text
MOV.enable_out.net_index == ADD_E.enable_in.net_index
```

Directly attached terminals and explicit wire paths resolve to the same semantic binding because both have already been normalized by `ConnectivityGraph`.

Each Function port also exposes directly attached/connected terminal symbols when terminals occur on the same conductive net.

## Public API

```python
from gxw import build_semantic_model, read_structured_program

program = read_structured_program("project.gxw")
semantic = build_semantic_model(program)

for function in semantic.functions:
    print(function.serialized_symbol)
    print(function.base_name)
    print(function.data_input_count)
    print(function.has_enable_interface)
    for port in function.ports:
        print(port.role, port.net_index, port.terminal_symbols)
```

Primary model types:

```text
StructuredSemanticModel
SemanticFunction
SemanticFunctionPort
SemanticTerminal
SemanticIssue
UnmodeledNodeRef
```

## Fail-soft semantic policy

The binary parser remains fail-closed for unsupported record structure. The semantic layer is intentionally fail-soft for unknown meaning:

- unknown Function port layouts become `SemanticPortRole.UNKNOWN` plus a warning;
- arity mismatches become warnings;
- unresolved `?` terminals become warnings;
- contacts, coils and other not-yet-modeled node kinds are retained in `unmodeled_nodes`.

This separation avoids turning incomplete reverse-engineering knowledge into false format errors.

## Regression coverage

The v1 semantic tests use extracted real `Program.pou` fixtures from controlled samples 64-71 and lock the following findings:

- sample 64: unresolved `?` source terminal is preserved and reported;
- sample 65: `MOV.ENO -> ADD_E.EN` shares one semantic net;
- samples 66/68: `ADD_E-3` and `AND_E-3` resolve as registered extensible families with arity 3;
- sample 69: fixed two-input `DIV_E` is not interpreted as a `-2` family instance;
- samples 70/71: `ABS` is `[data_in, data_out]`, while `ABS_E` is `[enable_in, data_in, enable_out, data_out]`;
- samples 65-71 produce no unexpected semantic warnings.

## Next semantic milestones

The next layer should not be implemented by guessing from ordinary Function behavior. Controlled samples are still needed for:

1. FB instance records and multi-output behavior;
2. timer/counter node semantics;
3. contact/coil execution semantics combined with conductive nets;
4. labels and typed local variables at terminals;
5. multiple networks/POUs;
6. deterministic lowering from `StructuredSemanticModel` into `plc_ir.py`.
