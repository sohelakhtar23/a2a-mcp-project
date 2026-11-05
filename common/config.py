
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")   # loads .env into os.environ

# 1) CHANGE THIS -----------------------------------------------------
PROVIDER = "groq"        # "openai"  or  "groq"  -- which company's API to call

# 2) These come from .env -- fill your real keys in there, not here ---
API_KEY = os.getenv("GROQ_API_KEY", "PUT_YOUR_GROQ_KEY_HERE")            # LLM key for PROVIDER above
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "PUT_YOUR_RAPIDAPI_KEY_HERE")                # airbnb agent (local) -> Airbnb13 (via RapidAPI)
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "PUT_YOUR_OWN_MADE_UP_SECRET_HERE")        # shared secret callers must send to reach ANY of our agents

# ---------------------------------------------------------------------

# You normally don't need to touch anything below this line.

PROVIDER_SETTINGS = {                                  # lookup table: provider name -> its settings
    "openai": {
        "base_url": None,             # None = use OpenAI's default endpoint
        "model": "gpt-4o-mini",       # which OpenAI model to call
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",   # Groq's OpenAI-compatible address
        "model": "openai/gpt-oss-120b",                  # which Groq model to call
    },
}

if PROVIDER not in PROVIDER_SETTINGS:                                        # catch typos early
    raise ValueError(f"PROVIDER must be 'openai' or 'groq', got: {PROVIDER!r}")

BASE_URL = PROVIDER_SETTINGS[PROVIDER]["base_url"]   # the address every agent's brain will call
MODEL = PROVIDER_SETTINGS[PROVIDER]["model"]         # the model name every agent's brain will use
