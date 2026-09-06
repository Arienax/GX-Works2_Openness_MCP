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
    DEFAULT_FUNCTION_FAMILY_REGISTRY,
    FunctionFamilySpec,
    SemanticFunction,
    SemanticFunctionPort,
    SemanticIssue,
    SemanticIssueSeverity,
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
    "ConnectivityGraph",
    "ConnectivityNet",
    "DEFAULT_FUNCTION_FAMILY_REGISTRY",
    "FunctionFamilySpec",
    "GXWFormatError",
    "GXWProjectResolver",
    "NodeKind",
    "Point",
    "PortDescriptor",
    "PortRef",
    "Rect",
    "SemanticFunction",
    "SemanticFunctionPort",
    "SemanticIssue",
    "SemanticIssueSeverity",
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
