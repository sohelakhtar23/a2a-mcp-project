"""
WEATHER AGENT -- CARD
========================
This agent's real Agent Card: what it can do, and where to reach it.
Served automatically by the a2a-sdk at the real, standard well-known
path (/.well-known/agent-card.json) -- see server.py.
"""

from a2a.types import AgentSkill

from common.agent_card_builder import build_agent_card

MY_URL = "http://localhost:9004/"

AGENT_CARD = build_agent_card(
    name="weather-agent",
    description="Looks up real weather for any city -- now, or a real forecast up to 16 days ahead.",
    url=MY_URL,
    version="2.0.0",
    skills=[
        AgentSkill(
            id="get-weather",
            name="Get Weather",
            description="Looks up the real current weather, or a real forecast up to 16 days ahead, for a city.",
            tags=["weather", "forecast"],
            examples=[
                "What's the weather in Lahore right now?",
                "How's the weather in Karachi on July 31?",
            ],
        ),
    ],
)
