"""
AGENT EXECUTOR -- the ONE place our code touches the real A2A protocol
plumbing directly.
=========================================================================
This is the "adapter slot" the official a2a-sdk defines: a class that
implements `execute()` and `cancel()`, which the SDK's own
`DefaultRequestHandler` calls automatically whenever a real, correctly
formatted A2A request comes in (a JSON-RPC `SendMessage` call, or the
equivalent REST `POST /message:send`).

Every one of our four agents (flight, hotel, weather, airbnb) uses this
SAME executor -- it doesn't know or care whether it's booking a flight
or checking the weather. It just:
  1. Makes sure there's a Task for this request (reusing one if the
     client is continuing an existing conversation).
  2. Marks the task "working", asks the agent's `brain` module to think
     for one turn, and gets back a plain `TurnResult`.
  3. Publishes the correct real A2A events for that result: an
     `input-required` status if the brain still needs more info, or a
     real `Artifact` + `completed` status if it's done.

Nothing here is specific to any one agent's business logic -- that all
lives in each agent's own `brain.py`. This file is intentionally the
ONLY one in the whole project that imports from `a2a.server.*`.
"""

from typing import Protocol

from a2a.helpers.proto_helpers import (
    new_data_part,
    new_task_from_user_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater

from common.turn_result import TurnResult


class AgentBrain(Protocol):
    """The tiny interface every agent's brain.py must implement.

    Keeping this as a Protocol (structural typing) means brain.py files
    never need to import anything from a2a.server -- they just need a
    `run_turn` method with this exact shape.

    `memory_key` (not the raw task_id) is what the brain must use to key
    its per-conversation memory -- see `_memory_key` below for why."""

    async def run_turn(self, memory_key: str, user_text: str) -> TurnResult: ...


def _memory_key(context: RequestContext, task_id: str) -> str:
    """Builds the key a brain uses to look up this conversation's memory.

    The task_id is NOT trustworthy on its own: the SDK takes it straight
    from the client's message (`new_task_from_user_message` does
    `id=user_message.task_id or uuid4()`), so a caller can send any task_id
    it likes -- including one belonging to somebody else's conversation.
    Since the brains' checkpointer is keyed only by thread_id, that would
    replay a stranger's prior turns into the model's context and let it
    summarise their travel dates and itinerary back to the attacker.

    Namespacing by the AUTHENTICATED caller closes that: a task_id is only
    resolvable within the identity that created it. Today every caller
    shares one API key, so this is a single namespace -- but it means
    moving to per-caller keys makes the isolation real, instead of
    silently leaving a cross-tenant leak behind."""
    user = context.call_context.user
    caller = user.user_name if user.is_authenticated else "anonymous"
    return f"{caller}:{task_id}"


class BrainBackedExecutor(AgentExecutor):
    """A generic AgentExecutor that delegates all real thinking to a
    `brain` object. One instance of this per agent, constructed with
    that agent's own brain module."""

    def __init__(self, brain: AgentBrain):
        self._brain = brain

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            # First message in a new conversation -- create and publish
            # the initial Task before anything else, as the protocol
            # requires (a TaskStatusUpdateEvent can't come before the
            # Task itself exists).
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        user_text = context.get_user_input()
        result: TurnResult = await self._brain.run_turn(
            _memory_key(context, task.id), user_text
        )

        reply_message = updater.new_agent_message(parts=[new_text_part(result.reply_text)])

        if result.completed:
            if result.artifact is not None:
                await updater.add_artifact(
                    parts=[new_data_part(result.artifact)],
                    name=result.artifact_name,
                )
            await updater.complete(message=reply_message)
        else:
            await updater.requires_input(message=reply_message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
