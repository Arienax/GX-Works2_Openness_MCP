"""MCP-shaped tool boundary used by the Agent in the desktop process."""

from __future__ import annotations

import copy
import json
from typing import Any, List, Mapping, Protocol

from model_provider import ToolCall, ToolResult


class ToolRuntime(Protocol):
    def list_tools(self, context: Any = None) -> List[Mapping[str, Any]]: ...

    def invoke(self, tool_call: ToolCall, context: Any) -> ToolResult: ...


def _public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _public_value(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return copy.deepcopy(value)


class InProcessToolRuntime:
    """Adapt the existing deterministic registry to the ToolRuntime contract."""

    def __init__(self, registry: Any):
        self.registry = registry

    def list_tools(self, context: Any = None) -> List[Mapping[str, Any]]:
        del context
        return self.registry.schemas()

    def invoke(self, tool_call: ToolCall, context: Any) -> ToolResult:
        envelope = self.registry.call(
            tool_call.name,
            tool_call.arguments,
            context,
        )
        public = _public_value(envelope)
        return ToolResult(
            call_id=tool_call.id,
            name=tool_call.name,
            content=json.dumps(
                public,
                ensure_ascii=False,
                separators=(",", ":"),
            )[:18000],
            data=envelope,
            is_error=not bool(envelope.get("ok")),
        )


def build_default_tool_runtime() -> InProcessToolRuntime:
    from plc_agent_tools import build_default_tool_registry

    return InProcessToolRuntime(build_default_tool_registry())


__all__ = [
    "InProcessToolRuntime",
    "ToolRuntime",
    "build_default_tool_runtime",
]
