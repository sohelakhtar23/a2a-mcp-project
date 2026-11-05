"""
REGISTRY CLIENT
==================
Talks to our OWN bonus catalog service (registry/catalog_server.py).

This is NOT part of the official A2A protocol -- the real spec defines
no registry/catalog concept at all (see understand.md, section 4). It's
a convenience layer we built on top: every agent tells the catalog "I
exist, here's my real Agent Card," so a client that doesn't already
know an agent's URL can look one up by skill instead of guessing.

We register the exact same JSON a client would get by fetching
`/.well-known/agent-card.json` directly -- the catalog is just a place
that remembers real cards, not a different, made-up shape.
"""

import httpx
from a2a.server.request_handlers.response_helpers import agent_card_to_dict
from a2a.types import AgentCard

from common import config
from common.auth import API_KEY_HEADER

REGISTRY_URL = "http://localhost:9000"


async def register_with_registry(card: AgentCard) -> None:
    """Tells our own bonus catalog service "I exist, here's my real
    Agent Card." Sends the shared secret, since /register is a write to
    the phone book every client trusts.

    If the catalog isn't running, we don't want to crash the agent over
    it -- this is an optional convenience feature, not part of the real
    protocol -- so we just warn and keep going. Async because this is
    called from the server's async lifespan; the old blocking
    requests.post stalled the event loop during startup."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.post(
                f"{REGISTRY_URL}/register",
                json=agent_card_to_dict(card),
                headers={API_KEY_HEADER: config.AGENT_API_KEY},
            )
        if response.status_code == 200:
            print(f"  Registered with catalog at {REGISTRY_URL}")
        else:
            print(f"  Catalog refused registration ({response.status_code}): {response.text[:200]}")
    except Exception as e:
        print(f"  Could not reach catalog ({e}) -- start registry/catalog_server.py first.")
