"""
WEATHER AGENT -- BRAIN (LangGraph)
====================================
The actual AI logic. The simplest of the four agents -- a pure lookup, no
"booking" step. Its tool comes from a small MCP server we wrote ourselves
(mcp_servers/weather_server.py), which calls Open-Meteo -- completely free,
no API key. Knows NOTHING about A2A, JSON-RPC, or HTTP -- see
common/executor.py for the adapter that connects this to the outside world.

Framework note: this brain now runs on LangGraph's prebuilt ReAct agent
instead of the OpenAI Agents SDK. Two things changed as a result and
NOTHING else did:
  1. The tool is loaded via langchain-mcp-adapters' MultiServerMCPClient
     (same stdio subprocess, just a different client object).
  2. Per-task conversation memory is now handled by LangGraph's
     checkpointer keyed on thread_id -- we no longer hand-maintain a
     `_conversations` dict.
The `run_turn(memory_key, user_text) -> TurnResult` contract the executor
depends on is otherwise unchanged. Note the first argument is the
executor's `memory_key`, NOT the raw A2A task_id -- the task_id is
client-supplied, so the executor namespaces it by authenticated caller
before handing it here. See `_memory_key` in common/executor.py.
"""

import os
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from common.llm import get_model
from common.langgraph_helpers import latest_tool_call
from common.turn_result import TurnResult

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_PATH = os.path.join(THIS_DIR, "..", "..", "mcp_servers", "weather_server.py")

# Computed once at startup -- gives the agent a reference point so it can
# convert relative dates ("next Tuesday", "in 5 days") into an absolute
# YYYY-MM-DD date itself before calling the tool.
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

INSTRUCTIONS = (
    f"Today's date is {TODAY} (YYYY-MM-DD). You are a weather assistant. Across the "
    "conversation, figure out which city the user wants the weather for, and whether "
    "they want it RIGHT NOW or for a specific date.\n"
    "- If the city is missing or unclear, ask a short, friendly question for it. Do not "
    "guess.\n"
    "- If the user gives a relative date ('next Tuesday', 'in 5 days'), work out the "
    "absolute YYYY-MM-DD date yourself using today's date above, and confirm it back to "
    "them in your reply.\n"
    "- Once you know the city, call the `get_weather` tool with `city` set to it. If the "
    "user wants a specific date, also pass `date` in YYYY-MM-DD format; leave `date` empty "
    "for right-now current weather. Never invent weather data yourself -- always get it "
    "from the tool, even if the tool says no real forecast is available that far out.\n"
    "- After the tool responds, reply with a short, friendly summary of the real weather "
    "data it returned (or say plainly that no real forecast exists for that date, if the "
    "tool said so -- do not make something up instead).\n"
    "- Use only plain ASCII characters and regular spaces/hyphens in your reply -- no em "
    "dashes, curly quotes, or non-breaking spaces."
)

weather_mcp = MultiServerMCPClient({
    "weather-server": {
        "transport": "stdio",
        "command": "python",
        "args": [MCP_SERVER_PATH],
        # No env needed -- Open-Meteo is free with no API key at all.
    },
})

# Built once in connect(), at server startup. LangGraph's MemorySaver
# checkpointer stores each A2A task's conversation, keyed by thread_id.
_agent = None
_memory = MemorySaver()


async def connect() -> None:
    """Loads the MCP tool(s) and builds the ReAct agent once, at startup."""
    global _agent
    tools = await weather_mcp.get_tools()
    _agent = create_agent(
        get_model(), tools, system_prompt=INSTRUCTIONS, checkpointer=_memory
    )


async def cleanup() -> None:
    """Nothing to tear down explicitly -- the stdio subprocess is managed
    per-call by MultiServerMCPClient. Kept so server.py's lifespan stays
    identical across all four agents."""
    return None


async def run_turn(memory_key: str, user_text: str) -> TurnResult:
    """Runs one turn of the agent against this task's conversation so far.
    Ground truth for "done vs still gathering info" is whether the
    `get_weather` tool was actually called this turn -- not the model
    self-reporting a status. The checkpointer replays prior turns for this
    task_id automatically, so we only send the new user message."""
    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=user_text)]},
        config={"configurable": {"thread_id": memory_key}},
    )
    messages = result["messages"]
    message = messages[-1].content

    _call_args, weather_data = latest_tool_call(messages, "get_weather")

    if weather_data is None:
        return TurnResult(reply_text=message, completed=False)

    return TurnResult(
        reply_text=message,
        completed=True,
        artifact=weather_data,
        artifact_name="weather-lookup",
    )
