"""
FLIGHT AGENT -- CARD
=======================
This agent's real Agent Card: what it can do, and where to reach it.
Served automatically by the a2a-sdk at the real, standard well-known
path (/.well-known/agent-card.json) -- see server.py.
"""

from a2a.types import AgentSkill

from common.agent_card_builder import build_agent_card

MY_URL = "http://localhost:9001/"

AGENT_CARD = build_agent_card(
    name="flight-booking-agent",
    description="Finds real flight prices between any two cities worldwide, for a specific date.",
    url=MY_URL,
    version="2.0.0",
    skills=[
        AgentSkill(
            id="book-flight",
            name="Book a Flight",
            description="Finds a real flight price between any two cities worldwide, for a specific date.",
            tags=["flights", "travel", "booking"],
            examples=[
                "Book a flight Lahore -> Karachi next Monday",
                "I want to fly from London to Dubai on 2026-08-02",
            ],
        ),
    ],
)
