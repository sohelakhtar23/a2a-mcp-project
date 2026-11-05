"""
LANGGRAPH HELPERS -- shared tool-call extraction for every agent's brain.
=============================================================================
When the project ran on the OpenAI Agents SDK, each brain.py hand-rolled
its own `_flatten_tool_output_text` / `_extract_*` pair (copy-pasted four
times) to pull GROUND TRUTH out of `result.new_items`. LangGraph exposes
the same information more directly -- the run's `messages` list contains
`AIMessage`s (whose `.tool_calls` already hold PARSED argument dicts) and
`ToolMessage`s (whose `.content` is the tool's text output) -- so we can
factor the shared logic into this one place instead.

Ground-truth principle is unchanged from the original project: never trust
what the model SAYS in prose about what it did. Look at whether the tool
was actually called this turn, what arguments it was actually called with,
and what the tool actually returned. That -- not the model's self-report --
decides "done vs still gathering info" and fills the artifact.
"""

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


def latest_tool_call(messages: list, tool_name: str) -> tuple[dict | None, dict | None]:
    """Return (call_args, tool_output) for the most recent call to
    `tool_name` in this message list, or (None, None) if it wasn't called.

    - call_args:   the PARSED argument dict the model invoked the tool with
                   (LangGraph already parses these -- no json.loads needed),
                   taken from the matching AIMessage.tool_calls entry.
    - tool_output: the tool's real return value, parsed from the matching
                   ToolMessage.content by tool_call_id. If the content isn't
                   JSON we hand back {"raw": <text>} so the caller still sees
                   something real rather than nothing.

    We match the ToolMessage back to its AIMessage by tool_call_id, so an
    agent that happens to call several different tools in one turn still
    lines the right args up with the right output.
    """
    call_args: dict | None = None
    call_id: str | None = None

    # Walk newest-first so we grab THIS turn's call, not a stale earlier one.
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == tool_name:
                    call_args = tc.get("args") or {}
                    call_id = tc.get("id")
                    break
            if call_args is not None:
                break

    if call_args is None:
        return None, None

    tool_output: dict | None = None
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.tool_call_id == call_id:
            tool_output = _parse_tool_content(msg.content)
            break

    return call_args, tool_output


def _parse_tool_content(content: Any) -> dict:
    """A ToolMessage's content is usually a JSON string, but the SDK can
    also hand back a list of content blocks. Normalise either into a dict."""
    text = _flatten_content(content)
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"raw": text}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def _flatten_content(content: Any) -> str | None:
    """ToolMessage.content is normally a str, but can be a list of blocks
    like [{"type": "text", "text": "..."}]. Pull the text out either way --
    this replaces the `_flatten_tool_output_text` that was duplicated in
    all four brain.py files under the Agents SDK."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict) and "text" in content:
        return content["text"]
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif hasattr(block, "text"):
                parts.append(block.text)
        return "".join(parts) if parts else None
    return None
