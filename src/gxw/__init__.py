"""Experimental read-only GX Works2 .gxw parser."""

from .connectivity import (
    ConnectivityGraph,
    ConnectivityNet,
    PortRef,
    build_connectivity_graph,
)
from .models import (
    GXWFormatError,
    NodeKind,
    Point,
    PortDescriptor,
    Rect,
    StructuredNode,
    StructuredProgram,
    StructuredWire,
)
from .project_resolver import GXWProjectResolver
from .semantic import (
    CoilRole,
    ContactPolarity,
    DEFAULT_FUNCTION_BLOCK_REGISTRY,
    DEFAULT_FUNCTION_FAMILY_REGISTRY,
    FunctionFamilySpec,
    FunctionBlockCategory,
    FunctionBlockPortSpec,
    FunctionBlockSpec,
    SemanticCoil,
    SemanticContact,
    SemanticFunction,
    SemanticFunctionBlock,
    SemanticFunctionBlockPort,
    SemanticFunctionPort,
    SemanticIssue,
    SemanticIssueSeverity,
    SemanticLadderPort,
    SemanticPortRole,
    SemanticTerminal,
    StructuredSemanticModel,
    TerminalRole,
    UnmodeledNodeRef,
    build_semantic_model,
)
from .structured_pou import parse_structured_pou


def read_structured_program(*args, **kwargs):
    from .decoder import read_structured_program as _read_structured_program

    return _read_structured_program(*args, **kwargs)


def describe_program(*args, **kwargs):
    from .decoder import describe_program as _describe_program

    return _describe_program(*args, **kwargs)


__all__ = [
    "CoilRole",
    "ConnectivityGraph",
    "ConnectivityNet",
    "ContactPolarity",
    "DEFAULT_FUNCTION_BLOCK_REGISTRY",
    "DEFAULT_FUNCTION_FAMILY_REGISTRY",
    "FunctionFamilySpec",
    "FunctionBlockCategory",
    "FunctionBlockPortSpec",
    "FunctionBlockSpec",
    "GXWFormatError",
    "GXWProjectResolver",
    "NodeKind",
    "Point",
    "PortDescriptor",
    "PortRef",
    "Rect",
    "SemanticCoil",
    "SemanticContact",
    "SemanticFunction",
    "SemanticFunctionBlock",
    "SemanticFunctionBlockPort",
    "SemanticFunctionPort",
    "SemanticIssue",
    "SemanticIssueSeverity",
    "SemanticLadderPort",
    "SemanticPortRole",
    "SemanticTerminal",
    "StructuredNode",
    "StructuredProgram",
    "StructuredSemanticModel",
    "StructuredWire",
    "TerminalRole",
    "UnmodeledNodeRef",
    "build_connectivity_graph",
    "build_semantic_model",
    "describe_program",
    "parse_structured_pou",
    "read_structured_program",
]
