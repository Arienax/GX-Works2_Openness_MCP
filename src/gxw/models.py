from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, Tuple


class GXWFormatError(ValueError):
    """Raised when a GXW/CFB structure cannot be parsed safely."""


class NodeKind(str, Enum):
    FUNCTION = "function"
    CONTACT = "contact"
    CONTACT_NC = "contact_nc"
    COIL = "coil"
    INPUT = "input"
    OUTPUT = "output"
    UNKNOWN = "unknown"


def node_kind_from_code(kind_code: int) -> NodeKind:
    return {
        0x01: NodeKind.FUNCTION,
        0x03: NodeKind.CONTACT,
        0x04: NodeKind.CONTACT_NC,
        0x05: NodeKind.COIL,
        0x0D: NodeKind.INPUT,
        0x0E: NodeKind.OUTPUT,
    }.get(kind_code, NodeKind.UNKNOWN)


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    def __str__(self) -> str:
        return f"({self.left},{self.top})-({self.right},{self.bottom})"


@dataclass(frozen=True)
class PortDescriptor:
    size: int
    field_a: int
    field_b: int
    field_c: int
    raw: bytes = field(repr=False)


@dataclass(frozen=True)
class StructuredNode:
    offset: int
    record_length: int
    kind_code: int
    kind: NodeKind
    symbol: str
    bbox: Rect
    ports: Tuple[PortDescriptor, ...]
    object_flag: int
    reserved: int
    raw: bytes = field(repr=False)


@dataclass(frozen=True)
class StructuredWire:
    offset: int
    record_length: int
    start: Point
    end: Point
    prefix_fields: Tuple[int, int, int, int, int]
    suffix: int
    raw: bytes = field(repr=False)


@dataclass(frozen=True)
class UnknownRecord:
    offset: int
    record_length: int
    record_class: int
    raw: bytes = field(repr=False)


@dataclass(frozen=True)
class StructuredProgram:
    logical_name: str
    source_path: Optional[Path]
    record_count: int
    canvas_height: int
    body_size: int
    nodes: Tuple[StructuredNode, ...]
    wires: Tuple[StructuredWire, ...]
    unknown_records: Tuple[UnknownRecord, ...]
    trailer: bytes = field(repr=False)
    raw: bytes = field(repr=False)

    def iter_records(self) -> Iterable[object]:
        records = [*self.nodes, *self.wires, *self.unknown_records]
        return iter(sorted(records, key=lambda item: item.offset))
