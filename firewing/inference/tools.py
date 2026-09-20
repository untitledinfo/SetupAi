"""Function/tool calling.

Qwen models (including Qwen3-Omni) are trained on Hermes-style tool
calling: given a list of available tools in the prompt, the model
emits

    <tool_call>
    {"name": "get_weather", "arguments": {"city": "Lahore"}}
    </tool_call>

instead of (or alongside) normal text when it wants to call a tool.
This module parses that convention and exposes it through an
OpenAI-compatible `tool_calls` shape, so existing OpenAI-client code
mostly works unchanged.

FIREWING itself does not execute tools by default — a returned
`tool_calls` list is handed back to the caller (matching OpenAI's
contract), who executes them and sends the results back as `role:
"tool"` messages. A small built-in ToolRegistry is provided for
server-side execution in contexts that want it (e.g. `setup-ai chat`)
— see ToolRegistry below.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

_TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


def extract_tool_calls(generated_text: str) -> tuple[str, list[ToolCall]]:
    """Split model output into (remaining_text, tool_calls).

    Malformed `<tool_call>` blocks (bad JSON) are skipped rather than
    raising — a model hallucinating slightly-wrong JSON shouldn't crash
    the request; the text is left in place so at least something is
    visible to the caller for debugging.
    """
    tool_calls: list[ToolCall] = []

    def _replace(match: re.Match) -> str:
        raw = match.group(1)
        try:
            parsed = json.loads(raw)
            tool_calls.append(
                ToolCall(
                    id=f"call_{uuid.uuid4().hex[:12]}",
                    name=parsed["name"],
                    arguments=parsed.get("arguments", {}),
                )
            )
            return ""
        except (json.JSONDecodeError, KeyError):
            return match.group(0)  # leave malformed block in the text as-is

    remaining = _TOOL_CALL_PATTERN.sub(_replace, generated_text).strip()
    return remaining, tool_calls


def render_tools_for_prompt(tools: list[dict]) -> str:
    """Fallback tool-list rendering for tokenizers whose chat template
    doesn't accept a `tools=` kwarg directly. Prepended to the system
    prompt when needed.
    """
    lines = [
        "You have access to the following tools. To call one, respond "
        "with a <tool_call> block containing JSON: "
        '{"name": "<tool_name>", "arguments": {...}}',
        "",
        "Available tools:",
    ]
    for tool in tools:
        fn = tool.get("function", tool)
        lines.append(f"- {fn.get('name')}: {fn.get('description', '')}")
        params = fn.get("parameters")
        if params:
            lines.append(f"  parameters schema: {json.dumps(params)}")
    return "\n".join(lines)


@dataclass
class RegisteredTool:
    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Callable[[dict], Any]

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Optional server-side tool registry, for callers (like the CLI)
    that want FIREWING to execute tools itself rather than handing
    tool_calls back for the client to run.
    """

    def __init__(self):
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, description: str, parameters: dict):
        def decorator(fn: Callable[[dict], Any]) -> Callable[[dict], Any]:
            self._tools[name] = RegisteredTool(name, description, parameters, fn)
            return fn

        return decorator

    def schemas(self) -> list[dict]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(self, call: ToolCall) -> str:
        tool = self._tools.get(call.name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {call.name}"})
        try:
            result = tool.handler(call.arguments)
        except Exception as exc:  # noqa: BLE001 — a tool's own errors shouldn't crash the chat loop
            return json.dumps({"error": str(exc)})
        return result if isinstance(result, str) else json.dumps(result)


def build_default_registry() -> ToolRegistry:
    """A couple of small, safe example tools — mainly so `setup-ai
    chat` demonstrates the feature end to end without needing external
    services configured.
    """
    registry = ToolRegistry()

    @registry.register(
        "get_current_time",
        "Get the current date and time.",
        {"type": "object", "properties": {}},
    )
    def _get_current_time(_args: dict) -> str:
        import datetime

        return datetime.datetime.now().isoformat()

    @registry.register(
        "calculator",
        "Evaluate a basic arithmetic expression (+ - * / and parentheses only).",
        {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    )
    def _calculator(args: dict) -> str:
        expr = args.get("expression", "")
        if not re.fullmatch(r"[0-9+\-*/().\s]+", expr):
            return json.dumps({"error": "Only numbers and + - * / ( ) are allowed"})
        try:
            # Safe by construction: the regex above already rejects
            # anything except digits/operators/parens/whitespace, so
            # there's no name lookup or attribute access surface left
            # for eval() to exploit.
            result = eval(expr, {"__builtins__": {}}, {})  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        return json.dumps({"result": result})

    return registry
