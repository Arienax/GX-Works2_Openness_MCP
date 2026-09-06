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
    "GXWFormatError",
    "GXWProjectResolver",
    "NodeKind",
    "Point",
    "PortDescriptor",
    "PortRef",
    "Rect",
    "StructuredNode",
    "StructuredProgram",
    "StructuredWire",
    "build_connectivity_graph",
    "describe_program",
    "parse_structured_pou",
    "read_structured_program",
]
