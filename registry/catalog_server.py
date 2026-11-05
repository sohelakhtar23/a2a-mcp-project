"""
AGENT CATALOG -- our OWN bonus "phone book" for agents. NOT part of the
official A2A protocol.
=============================================================================
Read understand.md (section 4) for the full explanation, but the short
version: the real A2A spec defines no registry/directory service at
all. It only says "if you already have an agent's URL, fetch its
/.well-known/agent-card.json to learn what it can do." It never says
HOW you're supposed to get that URL in the first place.

This file is our own answer to that gap -- entirely optional, entirely
our own invention:
  1) Every agent (flight, hotel, weather, airbnb) tells this catalog
     about itself when it starts up ("registering"), sending the exact
     same real Agent Card JSON a client would get by fetching
     `/.well-known/agent-card.json` directly (see
     common/registry_client.py).
  2) A client that wants something done (e.g. "book a flight") can ask
     THIS catalog "who can do book-flight?" instead of already knowing
     a URL.
  3) The catalog looks through everyone who registered and replies with
     the matching agent's real card (which includes its real URL).

Run this FIRST, before starting any agents -- they need somewhere to
register with. It listens on http://localhost:9000
"""

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException

# Keep `python registry/catalog_server.py` working (the command in the
# README) now that this file imports from common/ -- that form doesn't put
# the project root on sys.path the way `-m` does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config  # noqa: E402
from common.auth import API_KEY_HEADER, keys_match, require_real_key  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")   # so emoji/banners print correctly on Windows

# Registering is a WRITE to the phone book every client trusts, so it needs
# the same shared secret the agents themselves require. Without this, anyone
# who can reach this port could overwrite a real agent's entry with their own
# URL and quietly receive users' travel details. Reads stay open -- discovery
# is the whole point of the catalog.
_EXPECTED_KEY = require_real_key(config.AGENT_API_KEY)


def _require_api_key(x_api_key: str | None) -> None:
    if not x_api_key or not keys_match(x_api_key, _EXPECTED_KEY):
        raise HTTPException(401, f"Missing or invalid {API_KEY_HEADER} header")

app = FastAPI(title="Agent Catalog (our own addition -- not part of the official A2A protocol)")

# The actual "phone book": agent name -> that agent's real Agent Card,
# stored exactly as received (no re-shaping into a custom schema of our
# own). Just a plain Python dict in memory, fine for a demo -- a real
# deployment would use a database so entries survive a restart.
CATALOG: dict[str, dict[str, Any]] = {}


@app.post("/register")
async def register_agent(
    card: dict[str, Any],
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
):
    """An agent calls this once, when it starts up, to say 'I exist,
    here's my real Agent Card.' Requires the shared secret -- see
    `_require_api_key` above for why. We store whatever real card it
    sends; the a2a-sdk on the agent's side already built it correctly."""
    _require_api_key(x_api_key)

    name = card.get("name")
    if not name:
        raise HTTPException(400, "Agent card must include a 'name' field")

    # Pin the URL to the name on first registration. A restarted agent
    # re-registering its own unchanged URL is normal; a *different* URL
    # claiming an existing name is a takeover attempt, not a restart.
    existing = CATALOG.get(name)
    if existing and existing.get("url") != card.get("url"):
        print(f"  [catalog] REJECTED re-registration of {name}: "
              f"{existing.get('url')} -> {card.get('url')}")
        raise HTTPException(
            409,
            f"Agent '{name}' is already registered at a different URL. "
            "Refusing to reassign an existing name to a new address.",
        )

    CATALOG[name] = card
    print(f"  [catalog] Registered agent: {name} -> {card.get('url')}")
    return {"status": "registered", "name": name}


@app.get("/agents")
def list_agents():
    """Returns every agent card currently registered -- the whole catalog."""
    return list(CATALOG.values())


@app.get("/agents/search")
def search_by_skill(skill: str):
    """
    The actual 'discovery' step: given a skill id like 'book-flight',
    look through every registered agent's skill list and return the
    ones that can do it.
    """
    matches = [
        card for card in CATALOG.values()
        if skill in [s.get("id") for s in card.get("skills", [])]
    ]
    print(f"  [catalog] Search for skill='{skill}' -> {len(matches)} match(es)")
    return {"skill": skill, "matches": matches}


if __name__ == "__main__":
    import uvicorn

    print("Starting Agent Catalog on http://localhost:9000")
    print("(Our own bonus discovery layer -- not part of the official A2A protocol)")
    print("Agents will register themselves here when they start.")
    uvicorn.run(app, host="127.0.0.1", port=9000)   # localhost only, like the agents
