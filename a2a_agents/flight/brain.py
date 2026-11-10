"""
FLIGHT AGENT -- BRAIN (LangGraph)
===================================
The actual AI logic that decides what to ask, when to call the real
flight-price tool, and how to turn its real results into a booking record.
Knows NOTHING about A2A, JSON-RPC, or HTTP -- see common/executor.py for
the adapter that connects this to the outside world.

The tool is a REMOTE MCP server -- not a local subprocess. The same tool
code (wrapping FlightAPI.io's one-way search) is deployed independently at
https://github.com/sohelakhtar23/a2a-travel-mcp-servers and reached over plain
HTTPS. Contrast this with the weather/airbnb agents, whose tools are local
stdio subprocesses. Under LangGraph this distinction is just a different
transport string in the MultiServerMCPClient config ("streamable_http" +
url, vs "stdio" + command) -- the rest of this file is identical in shape
to the local-tool agents, exactly as it was under the Agents SDK.

No synthetic fields at all -- there's no free real GDS/booking API to issue
an actual seat/PNR from, so this agent doesn't claim to hand one back.
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

# The real, deployed flight-price MCP server -- see
# https://github.com/sohelakhtar23/a2a-travel-mcp-servers
FLIGHT_MCP_URL = "https://flight-price-service.onrender.com/mcp"

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

INSTRUCTIONS = (
    f"Today's date is {TODAY} (YYYY-MM-DD). You are a flight-booking assistant for "
    "flights between any two cities in the world.\n"
    "Across the conversation, figure out THREE things: the route (from city -> to city), "
    "the cabin class (economy or business), and the travel date.\n"
    "- If any of these is still missing or unclear, ask a short, friendly question for "
    "exactly what's missing. Do not guess.\n"
    "- If the user gives a relative date (e.g. 'next week', 'this Friday', 'tomorrow'), "
    "work out the absolute date yourself using today's date above, and confirm it back to "
    "them in your reply (e.g. 'next Monday, 2026-07-27').\n"
    "- Once you know all THREE, work out the 3-letter IATA airport code for the departure "
    "and arrival cities yourself (use the main international airport if a city has more "
    "than one) and call `search_flights` with dep_iata, arr_iata, date (YYYY-MM-DD format), "
    "and cabin set accordingly, to get REAL live flight prices. Call it even if you're not "
    "sure it will find anything -- that's still a valid result.\n"
    "- Never invent a price, airline, or flight time yourself -- those come from the tool's "
    "real results, not from you.\n"
    "- After the tool responds, reply with a short confirmation message mentioning just the "
    "route, cabin class, and date -- do not mention any specific price, airline or flight "
    "time, that gets shown separately.\n"
    "- Use only plain ASCII characters and regular spaces/hyphens in your reply -- no em "
    "dashes, curly quotes, or non-breaking spaces."
)

flight_mcp = MultiServerMCPClient({
    "flight-price-server": {
        "transport": "streamable_http",
        "url": FLIGHT_MCP_URL,
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
    tools = await flight_mcp.get_tools()
    _agent = create_agent(
        get_model(), tools, system_prompt=INSTRUCTIONS, checkpointer=_memory
    )


async def cleanup() -> None:
    """No explicit teardown -- kept so server.py's lifespan is identical
    across all four agents."""
    return None


def _build_booking(call_args: dict, real_data: dict | None) -> dict:
    """Assembles the final booking record straight from the agent's real
    tool call (route/date/cabin) and FlightAPI's real results (airline,
    times, price, booking site). UNCHANGED from the Agents-SDK version."""
    dep_iata = (call_args.get("dep_iata") or "").upper()
    arr_iata = (call_args.get("arr_iata") or "").upper()
    date = call_args.get("date") or "unknown date"
    cabin = (call_args.get("cabin") or "Economy").strip().lower()

    itineraries = (real_data or {}).get("itineraries") or []
    if itineraries:
        # Read defensively: this dict comes from a remote MCP server we
        # don't control, so a renamed or missing field should degrade the
        # booking record rather than raise mid-request.
        cheapest = itineraries[0]   # tool already sorts cheapest-first
        airline = cheapest.get("airlines") or "Unknown airline"
        price_usd = cheapest.get("price_usd")
        price = f"${price_usd:,.2f}" if isinstance(price_usd, (int, float)) else "Not found"
        departure = cheapest.get("departure") or "?"
        arrival = cheapest.get("arrival") or "?"
        flight_time = f"{departure} -> {arrival}"
        stops = cheapest.get("stops")
        booking_site = cheapest.get("booking_site") or "N/A"
    else:
        airline = "No real flights found for this search"
        price = "Not found"
        flight_time = "N/A"
        stops = None
        booking_site = "N/A"

    return {
        "route": f"{dep_iata} -> {arr_iata}",
        "date": date,
        "cabin": cabin,
        "airline": airline,
        "flight_time": flight_time,
        "stops": stops,
        "price": price,
        "price_source": booking_site,
        "real_flight_search": real_data,   # every real itinerary FlightAPI found, for transparency
    }


async def run_turn(memory_key: str, user_text: str) -> TurnResult:
    """Runs one turn of the agent against this task's conversation so far.
    Ground truth for "done vs still gathering info" is whether the
    `search_flights` tool was actually called this turn -- not the model
    self-reporting a status."""
    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=user_text)]},
        config={"configurable": {"thread_id": memory_key}},
    )
    messages = result["messages"]
    message = messages[-1].content

    call_args, real_data = latest_tool_call(messages, "search_flights")

    if call_args is None:
        return TurnResult(reply_text=message, completed=False)

    booking_data = _build_booking(call_args, real_data)
    return TurnResult(
        reply_text=message,
        completed=True,
        artifact=booking_data,
        artifact_name="flight-search",
    )
