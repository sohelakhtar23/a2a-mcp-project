"""Test-only fakes injected at the TWO external boundaries only:
  1. the LLM (Groq)         -> FakeToolModel
  2. the MCP data tool call -> real @tool funcs returning canned, real-shaped data
Everything else under test (executor, auth, cards, routing, task lifecycle,
registry, and the ported brain logic) runs REAL and UNMODIFIED.
"""
import json, re
from typing import List, Optional
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.tools import tool

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Canned, real-SHAPED tool outputs (match exactly what each brain's _build_* expects)
_ARGS = {
    "get_weather":   {"city": "Karachi", "date": "2026-07-25"},
    "search_flights":{"dep_iata": "LHE", "arr_iata": "KHI", "date": "2026-08-10", "cabin": "economy"},
    "search_hotels": {"city": "Karachi", "arrival_date": "2026-08-10", "departure_date": "2026-08-13", "adults": 2},
    "search_airbnb": {"location": "Lahore", "checkin": "2026-08-10", "checkout": "2026-08-13", "adults": 2},
}

@tool
def get_weather(city: str, date: str = "") -> str:
    """look up weather"""
    return json.dumps({"city": city, "country": "Pakistan", "date": date or "2026-07-25",
                       "condition": "Clear sky", "temp_max_c": 39.5, "temp_min_c": 29.1, "chance_of_rain_pct": 5})

@tool
def search_flights(dep_iata: str, arr_iata: str, date: str, cabin: str = "economy") -> str:
    """search flights"""
    return json.dumps({"itineraries": [{"airlines": "Fake Air", "price_usd": 123.45,
                       "departure": "08:00", "arrival": "10:00", "stops": 0, "booking_site": "Kiwi"}]})

@tool
def search_hotels(city: str, arrival_date: str, departure_date: str, adults: int = 2) -> str:
    """search hotels"""
    return json.dumps({"hotels": [{"name": "Grand Fake Hotel", "price": 88.0, "currency": "USD", "rating": 8.7}]})

@tool
def search_airbnb(location: str, checkin: str, checkout: str, adults: int = 2) -> str:
    """search airbnb"""
    return json.dumps({"ok": True, "listings": [{"name": "Cozy Fake Loft", "price_per_night": 54.0,
                       "currency": "USD", "bedrooms": 1, "bathrooms": 1, "rating": 4.8,
                       "review_count": 120, "type": "Entire home", "url": "https://example.com/x"}]})

_TOOLS = {t.name: t for t in [get_weather, search_flights, search_hotels, search_airbnb]}

def fake_tool_for(name: str):
    async def _get_tools():
        return [_TOOLS[name]]
    return _get_tools

class FakeToolModel(BaseChatModel):
    """Deterministic stand-in for the Groq LLM. Decision rule:
      - a ToolMessage already in the thread -> emit final summary (COMPLETED path)
      - else if the human text contains a YYYY-MM-DD date -> emit a tool call
      - else -> ask a clarifying question (INPUT_REQUIRED path)
    """
    tool_name: str
    bound: Optional[List] = None
    def bind_tools(self, tools, **kw):
        self.bound = list(tools); return self
    def _decide(self, messages) -> AIMessage:
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="All set -- results are ready for your request.")
        human = " ".join(m.content for m in messages if isinstance(m, HumanMessage) and isinstance(m.content, str))
        if DATE_RE.search(human):
            return AIMessage(content="", tool_calls=[{"name": self.tool_name,
                             "args": _ARGS[self.tool_name], "id": "call_1", "type": "tool_call"}])
        return AIMessage(content="Sure -- could you share the missing detail (like the date)?")
    def _generate(self, messages, stop=None, run_manager=None, **kw):
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])
    async def _agenerate(self, messages, stop=None, run_manager=None, **kw):
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])
    @property
    def _llm_type(self): return "fake-tool-model"

def fake_model_for(tool_name: str):
    return lambda: FakeToolModel(tool_name=tool_name)
