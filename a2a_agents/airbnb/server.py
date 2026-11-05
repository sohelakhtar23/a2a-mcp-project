"""
AIRBNB AGENT -- SERVER (entrypoint)
=======================================
Wires the real A2A protocol plumbing (from common/) around this
agent's brain (brain.py) and card (card.py), and starts listening.

Run with (from the project root):

    python -m a2a_agents.airbnb.server

NOT `python a2a_agents/airbnb/server.py` directly -- that would break
the `from common import ...` imports, since Python needs the project
root on sys.path for those to resolve, which only happens with `-m`.
"""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.routes.rest_routes import create_rest_routes
from a2a.server.tasks import InMemoryTaskStore

from common import config
from common.auth import add_api_key_auth
from common.executor import BrainBackedExecutor
from common.registry_client import register_with_registry

from a2a_agents.airbnb import brain
from a2a_agents.airbnb.card import AGENT_CARD

sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252

PORT = 9003

request_handler = DefaultRequestHandler(
    agent_executor=BrainBackedExecutor(brain),
    task_store=InMemoryTaskStore(),
    agent_card=AGENT_CARD,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await brain.connect()
    print("  Connected to MCP tool server (airbnb_price_server.py)")
    await register_with_registry(AGENT_CARD)
    yield
    await brain.cleanup()


app = FastAPI(title="Airbnb Agent (A2A)", lifespan=lifespan)
add_api_key_auth(app, config.AGENT_API_KEY)
add_a2a_routes_to_fastapi(
    app,
    agent_card_routes=create_agent_card_routes(AGENT_CARD),
    jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/"),
    rest_routes=create_rest_routes(request_handler),
)


if __name__ == "__main__":
    import uvicorn

    print(f"Starting Airbnb Agent on http://localhost:{PORT}")
    print(f"Agent card: http://localhost:{PORT}/.well-known/agent-card.json")

    # Bind to localhost, not 0.0.0.0: a dev run on an untrusted network
    # would otherwise expose this agent -- and your LLM/API quota -- to
    # everyone on the LAN. Change this deliberately when deploying.
    uvicorn.run(app, host="127.0.0.1", port=PORT)
