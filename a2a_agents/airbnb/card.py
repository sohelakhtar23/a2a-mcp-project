"""
AIRBNB AGENT -- CARD
=======================
This agent's real Agent Card: what it can do, and where to reach it.
Served automatically by the a2a-sdk at the real, standard well-known
path (/.well-known/agent-card.json) -- see server.py.
"""

from a2a.types import AgentSkill

from common.agent_card_builder import build_agent_card

MY_URL = "http://localhost:9003/"

AGENT_CARD = build_agent_card(
    name="airbnb-agent",
    description="Finds real Airbnb listings and prices in any city worldwide, for specific check-in/check-out dates.",
    url=MY_URL,
    version="2.0.0",
    skills=[
        AgentSkill(
            id="book-airbnb",
            name="Book an Airbnb",
            description="Finds a real Airbnb listing and price in any city worldwide, for specific dates.",
            tags=["airbnb", "travel", "booking"],
            examples=[
                "Find me an Airbnb in Lahore next weekend",
                "I need an Airbnb in Paris from 2026-08-10 to 2026-08-13",
            ],
        ),
    ],
)
