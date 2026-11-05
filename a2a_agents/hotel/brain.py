"""
HOTEL AGENT -- BRAIN (LangGraph)
==================================
The actual AI logic: decides what to ask, when to call the real hotel-price
tool, and how to turn its real results into a booking record. Knows NOTHING
about A2A, JSON-RPC, or HTTP -- see common/executor.py for the adapter that
connects this to the outside world.

The tool is a REMOTE MCP server (wrapping Booking.com's real search via
RapidAPI), deployed at https://github.com/Zalaid/a2a-travel-mcp-servers and
reached over plain HTTPS -- same remote-vs-local contrast as the flight
agent. Under LangGraph that's just a "streamable_http" transport string.

No synthetic fields at all -- there's no free real booking/GDS API to issue
an actual reservation from, so this agent doesn't claim to hand one back.
Every field in the result is real.
"""

from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from common.llm import get_model
from common.langgraph_helpers import latest_tool_call
from common.turn_result import TurnResult

# The real, deployed hotel-price MCP server -- see
# https://github.com/Zalaid/a2a-travel-mcp-servers
HOTEL_MCP_URL = "https://booking-mcp-server.onrender.com/mcp"

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

INSTRUCTIONS = (
    f"Today's date is {TODAY} (YYYY-MM-DD). You are a hotel-booking assistant for any "
    "city in the world.\n"
    "Across the conversation, figure out THREE things: the city, the check-in date, and "
    "the check-out date.\n"
    "- If any of these is missing or unclear, ask a short, friendly question for exactly "
    "what's missing. Do not guess. If the user gives a relative date ('next weekend', "
    "'tomorrow'), work out the absolute YYYY-MM-DD date yourself using today's date above, "
    "and confirm it back to them in your reply.\n"
    "- Once you know all three, call `search_hotels` with city, arrival_date, "
    "departure_date, and adults (default 2 if not given), to get REAL live hotel prices. "
    "Call it even if you're unsure it will find anything -- that's still a valid result.\n"
    "- Never invent a hotel name, price, or rating yourself -- those come from the tool's "
    "real results, not from you.\n"
    "- After the tool responds, reply with a short confirmation message mentioning just "
    "the city and the two dates -- do not mention any specific hotel name or price, that "
    "gets shown separately.\n"
    "- Use only plain ASCII characters and regular spaces/hyphens in your reply -- no em "
    "dashes, curly quotes, or non-breaking spaces."
)

hotel_mcp = MultiServerMCPClient({
    "hotel-price-server": {
        "transport": "streamable_http",
        "url": HOTEL_MCP_URL,
    },
})

_agent = None
_memory = MemorySaver()


async def connect() -> None:
    """Loads the remote MCP tool(s) and builds the ReAct agent once, at
    startup. The free-tier host sleeps after inactivity and can take up to
    ~60s to wake on the first request, so this first get_tools() may be
    slow."""
    global _agent
    tools = await hotel_mcp.get_tools()
    _agent = create_agent(
        get_model(), tools, system_prompt=INSTRUCTIONS, checkpointer=_memory
    )


async def cleanup() -> None:
    """No explicit teardown -- kept so server.py's lifespan is identical
    across all four agents."""
    return None


def _build_booking(call_args: dict, real_data: dict | None) -> dict:
    """Assembles the final booking record straight from the agent's real
    tool call (city/dates) and Booking.com's real results (hotel name,
    price, rating). UNCHANGED from the Agents-SDK version."""
    city = call_args.get("city") or "Unknown city"
    check_in = call_args.get("arrival_date") or "unknown"
    check_out = call_args.get("departure_date") or "unknown"

    hotels = (real_data or {}).get("hotels") or []
    if hotels:
        cheapest = hotels[0]   # tool already sorts cheapest-first
        hotel_name = cheapest["name"]
        price = f"{cheapest['price']:.2f} {cheapest['currency']}" if cheapest.get("price") is not None else "Not found"
        rating = cheapest.get("rating")
    else:
        hotel_name = "No real hotels found for this search"
        price = "Not found"
        rating = None

    return {
        "city": city,
        "check_in": check_in,
        "check_out": check_out,
        "hotel": hotel_name,
        "price_per_night": price,
        "rating": rating,
        "other_real_options": hotels[1:],   # more real alternatives, cheapest first
        "real_hotel_search": real_data,      # proof this came from a real Booking.com search
    }


async def run_turn(memory_key: str, user_text: str) -> TurnResult:
    """Runs one turn of the agent against this task's conversation so far.
    Ground truth for "done vs still gathering info" is whether the
    `search_hotels` tool was actually called this turn -- not the model
    self-reporting a status."""
    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=user_text)]},
        config={"configurable": {"thread_id": memory_key}},
    )
    messages = result["messages"]
    message = messages[-1].content

    call_args, real_data = latest_tool_call(messages, "search_hotels")

    if call_args is None:
        return TurnResult(reply_text=message, completed=False)

    booking_data = _build_booking(call_args, real_data)
    return TurnResult(
        reply_text=message,
        completed=True,
        artifact=booking_data,
        artifact_name="hotel-search",
    )
