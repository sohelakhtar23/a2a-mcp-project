"""
AGENT CARD BUILDER
=====================
Every agent's card.py calls this with its own name/description/skills.
Keeps the repeated shape (interfaces, capabilities, security scheme)
in one place instead of copy-pasted four times.

Security: every card built here honestly declares a real scheme --
a single shared API key sent as `X-API-Key`, enforced by
common/auth.py. This is the simplest real scheme A2A supports (the
spec also allows OAuth2, OpenID Connect, and mutual TLS -- see
understand.md for why we started with the simple one). A client reads
this declaration from the card and knows exactly what it needs to send,
same as it would for any other A2A agent.
"""

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.types.a2a_pb2 import (
    APIKeySecurityScheme,
    AgentInterface,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from a2a.utils.constants import TransportProtocol

from common.auth import API_KEY_HEADER

_SECURITY_SCHEME_ID = "apiKeyAuth"


def build_agent_card(
    *,
    name: str,
    description: str,
    url: str,
    version: str,
    skills: list[AgentSkill],
) -> AgentCard:
    """Builds a real A2A AgentCard. JSON-RPC only for now -- this
    project doesn't implement the gRPC binding."""
    return AgentCard(
        name=name,
        description=description,
        version=version,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        skills=skills,
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding=TransportProtocol.JSONRPC),
        ],
        security_schemes={
            _SECURITY_SCHEME_ID: SecurityScheme(
                api_key_security_scheme=APIKeySecurityScheme(
                    location="header",
                    name=API_KEY_HEADER,
                    description="Shared secret required to call this agent (except fetching this card).",
                ),
            ),
        },
        security_requirements=[
            SecurityRequirement(schemes={_SECURITY_SCHEME_ID: StringList(list=[])}),
        ],
    )
