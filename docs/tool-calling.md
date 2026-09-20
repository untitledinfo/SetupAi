# Function / Tool Calling

FIREWING supports OpenAI-style function calling, built on Qwen's
native Hermes-format tool-call convention.

## Request shape

```json
{
  "model": "firewing-1.0-beta",
  "messages": [
    {"role": "user", "content": "What's 23 * 47?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression.",
        "parameters": {
          "type": "object",
          "properties": {"expression": {"type": "string"}},
          "required": ["expression"]
        }
      }
    }
  ],
  "stream": false
}
```

**`stream` must be `false` when `tools` is set.** Tool-call detection
needs the complete generated text (it looks for `<tool_call>...</tool_call>`
blocks), so this beta rejects `tools` + `stream: true` with a 400
rather than silently ignoring tool calls embedded in a stream.

## Response shape

If the model decides to call a tool, you get back `tool_calls` instead
of `content`, with `finish_reason: "tool_calls"`:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_a1b2c3d4e5f6",
            "type": "function",
            "function": {"name": "calculator", "arguments": "{\"expression\": \"23 * 47\"}"}
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

**FIREWING does not execute tools itself in the API** — matching
OpenAI's contract, execution is the caller's job. Run the tool, then
send the result back as a `role: "tool"` message, including the
`tool_call_id` from the response:

```json
{
  "messages": [
    {"role": "user", "content": "What's 23 * 47?"},
    {"role": "assistant", "content": null, "tool_calls": [/* ... from above ... */]},
    {"role": "tool", "tool_call_id": "call_a1b2c3d4e5f6", "name": "calculator", "content": "{\"result\": 1081}"}
  ],
  "tools": [/* same tools array again */]
}
```

The model then produces its final answer using the tool result.

## Server-side execution (CLI only)

`setup-ai chat` demonstrates a full server-side tool loop using the
built-in `ToolRegistry` (`firewing/inference/tools.py`) — it calls
tools automatically and feeds results back, up to a few hops, so you
can see the whole thing work end to end without writing a client. The
two example tools (`get_current_time`, `calculator`) are intentionally
minimal and safe (the calculator only accepts digits/operators — no
arbitrary code execution surface).

To use this pattern in your own server-side integration instead of
handling tool execution client-side, follow the same pattern: check
`result.tool_calls` after `engine.generate(..., tools=registry.schemas())`,
execute with `registry.execute(call)`, and continue the conversation
with `conversation.add_tool_result(...)`.

## Honesty check

Qwen models are trained on this `<tool_call>` convention, but the
parser and end-to-end flow here **haven't been validated against real
Qwen3-Omni weights** (no GPU/weights in the environment this was
built in) — only the parsing logic and API contract are unit-tested
with synthetic model output. Before relying on this in production,
confirm with a real checkpoint that it actually emits well-formed
`<tool_call>` blocks for your prompts and tool definitions.
