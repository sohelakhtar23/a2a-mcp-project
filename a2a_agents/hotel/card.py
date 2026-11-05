"""
HOTEL AGENT -- CARD
=======================
This agent's real Agent Card: what it can do, and where to reach it.
Served automatically by the a2a-sdk at the real, standard well-known
path (/.well-known/agent-card.json) -- see server.py.
"""

from a2a.types import AgentSkill

from common.agent_card_builder import build_agent_card

MY_URL = "http://localhost:9002/"

AGENT_CARD = build_agent_card(
    name="hotel-booking-agent",
    description="Finds real hotel prices in any city worldwide, for specific check-in/check-out dates.",
    url=MY_URL,
    version="2.0.0",
    skills=[
        AgentSkill(
            id="book-hotel",
            name="Book a Hotel Room",
            description="Finds a real hotel price in any city worldwide, for specific dates.",
            tags=["hotels", "travel", "booking"],
            examples=[
                "Book a hotel in Karachi next weekend",
                "I need a hotel room in Tokyo from 2026-08-10 to 2026-08-13",
            ],
        ),
    ],
)
