"""
AIRBNB AGENT -- BRAIN (LangGraph)
===================================
The actual AI logic: decides what to ask, when to call the real
Airbnb-search tool, and how to turn its real results into a booking
record. Knows NOTHING about A2A, JSON-RPC, or HTTP -- see
common/executor.py for the adapter that connects this to the outside world.

This agent's tool is a small local MCP server we wrote ourselves
(mcp_servers/airbnb_price_server.py), wrapping Airbnb13's real search (via
RapidAPI). Our own wrapper trims Airbnb13's huge raw response down to just
name/price/bedrooms/rating/url before the agent ever sees it -- same real
data, small enough to stay within Groq's free-tier rate limit.

No synthetic fields at all -- there's no free real booking API to issue an
actual reservation from, so this agent doesn't claim to hand one back.
Every field in the result is real.

Framework note: runs on LangGraph now instead of the OpenAI Agents SDK.
Tool loading goes through langchain-mcp-adapters; per-task memory is the
LangGraph checkpointer keyed on thread_id (no hand-kept `_conversations`
dict). The `run_turn` contract with the executor is unchanged, and
`_build_booking` is byte-for-byte the original -- it only ever touched the
tool's REAL output dict, which is framework-independent.
"""

import os
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from common import config
from common.llm import get_model
from common.langgraph_helpers import latest_tool_call
from common.turn_result import TurnResult

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_PATH = os.path.join(THIS_DIR, "..", "..", "mcp_servers", "airbnb_price_server.py")

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

INSTRUCTIONS = (
    f"Today's date is {TODAY} (YYYY-MM-DD). You are an Airbnb-search assistant for any "
    "city in the world.\n"
    "Across the conversation, figure out THREE things: the location (city), the check-in "
    "date, and the check-out date.\n"
    "- If any of these is missing or unclear, ask a short, friendly question for exactly "
    "what's missing. Do not guess. If the user gives a relative date ('next weekend', "
    "'tomorrow'), work out the absolute YYYY-MM-DD date yourself using today's date above, "
    "and confirm it back to them in your reply.\n"
    "- Once you know all three, call `search_airbnb` with location, checkin, checkout, and "
    "adults (default 2 if not given), to get REAL live Airbnb listings. Call it even if "
    "you're unsure it will find anything -- that's still a valid result.\n"
    "- Never invent a listing name, price, or rating yourself -- those come from the "
    "tool's real results, not from you.\n"
    "- After the tool responds, reply with a short confirmation message mentioning just "
    "the city and the two dates -- do not mention any specific listing name or price, that "
    "gets shown separately.\n"
    "- Use only plain ASCII characters and regular spaces/hyphens in your reply -- no em "
    "dashes, curly quotes, or non-breaking spaces."
)

airbnb_mcp = MultiServerMCPClient({
    "airbnb-price-server": {
        "transport": "stdio",
        "command": "python",
        "args": [MCP_SERVER_PATH],
        "env": {"RAPIDAPI_KEY": config.RAPIDAPI_KEY},
    },
})

_agent = None
_memory = MemorySaver()


async def connect() -> None:
    """Loads the MCP tool(s) and builds the ReAct agent once, at startup."""
    global _agent
    tools = await airbnb_mcp.get_tools()
    _agent = create_agent(
        get_model(), tools, system_prompt=INSTRUCTIONS, checkpointer=_memory
    )


async def cleanup() -> None:
    """No explicit teardown -- kept so server.py's lifespan is identical
    across all four agents."""
    return None


def _build_booking(call_args: dict, real_data: dict | None) -> dict:
    """Assembles the final booking record straight from the agent's real
    tool call (location/dates) and Airbnb13's real results (listing name,
    price, rating, url) -- no text-scanning, no random price, no synthetic
    fields at all. UNCHANGED from the Agents-SDK version."""
    location = call_args.get("location") or "Unknown location"
    check_in = call_args.get("checkin") or "unknown"
    check_out = call_args.get("checkout") or "unknown"

    listings = (real_data or {}).get("listings") or []
    if listings:
        cheapest = listings[0]   # tool already sorts cheapest-first
        listing_name = cheapest["name"]
        price = f"{cheapest['price_per_night']:.2f} {cheapest['currency']}" if cheapest.get("price_per_night") is not None else "Not found"
        rating = cheapest.get("rating")
        url = cheapest.get("url")
    else:
        listing_name = "No real listings found for this search"
        price = "Not found"
        rating = None
        url = None

    return {
        "location": location,
        "check_in": check_in,
        "check_out": check_out,
        "listing": listing_name,
        "price_per_night": price,
        "rating": rating,
        "listing_url": url,
        "other_real_options": listings[1:],   # more real alternatives, cheapest first
        "real_airbnb_search": real_data,       # proof this came from a real Airbnb13 search
    }


async def run_turn(memory_key: str, user_text: str) -> TurnResult:
    """Runs one turn of the agent against this task's conversation so far.
    Ground truth for "done vs still gathering info" is whether the
    `search_airbnb` tool was actually called this turn -- not the model
    self-reporting a status."""
    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=user_text)]},
        config={"configurable": {"thread_id": memory_key}},
    )
    messages = result["messages"]
    message = messages[-1].content

    call_args, real_data = latest_tool_call(messages, "search_airbnb")

    if call_args is None:
        return TurnResult(reply_text=message, completed=False)

    booking_data = _build_booking(call_args, real_data)
    return TurnResult(
        reply_text=message,
        completed=True,
        artifact=booking_data,
        artifact_name="airbnb-search",
    )
