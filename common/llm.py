"""
LLM MODEL BUILDER -- builds the chat model LangGraph's agents need.
============================================================================
LangGraph's `create_react_agent` wants a LangChain chat model, not an API
key. Since Groq speaks the OpenAI-compatible chat-completions shape, we
build a `ChatOpenAI` pointed at Groq's base_url -- same pattern as calling
real OpenAI, just a different endpoint. Every agent's brain.py imports
`get_model()` from here so there's only one place that knows about
common/config.py.

(This is the ONLY behavioural difference from the OpenAI-Agents-SDK version
of this file: it returns a `ChatOpenAI` instead of an
`OpenAIChatCompletionsModel`. base_url / key / model name still all come
from config.py, so switching PROVIDER between 'groq' and 'openai' works
exactly as before.)
"""

from langchain_openai import ChatOpenAI

from common import config


def get_model() -> ChatOpenAI:
    """Returns the chat model to pass into create_react_agent(model=...).

    Works the same whether config.PROVIDER is 'openai' or 'groq' -- the
    only difference is base_url/key/model name, all read from config.py.
    """
    return ChatOpenAI(
        model=config.MODEL,
        api_key=config.API_KEY,
        base_url=config.BASE_URL,   # None for OpenAI -> LangChain uses its default
        temperature=0,
    )
