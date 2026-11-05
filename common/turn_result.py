"""
TURN RESULT -- what an agent's brain hands back after thinking for one turn.
===============================================================================
Every agent's brain.py (flight, hotel, weather, airbnb) returns one of
these from `run_turn()`. It's the one, tiny contract between "your AI
logic" and "the real A2A plumbing" (see common/executor.py) -- the
brain never touches A2A types directly, and the executor never touches
OpenAI Agents SDK types directly.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class TurnResult:
    """The result of one turn of an agent's thinking.

    completed=False means the brain is still gathering information from
    the user (the A2A task will move to the INPUT_REQUIRED state, and
    `artifact` is ignored).

    completed=True means the brain is done -- `artifact` holds the real
    result data to hand back (or None if a real search genuinely found
    nothing, which is still a valid, honest completion).
    """

    reply_text: str
    completed: bool
    artifact: dict[str, Any] | None = None
    artifact_name: str = "result"
