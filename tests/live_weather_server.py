"""Launch the REAL weather agent as a real uvicorn process, with ONLY the LLM
faked (always requests current weather for the given city) -- the MCP tool and
Open-Meteo call are 100% REAL. This is the authentic 'external client curls a
live agent' round trip."""
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
import a2a_agents.weather.brain as wb

class AlwaysCurrentWeather(BaseChatModel):
    def bind_tools(self, tools, **kw): return self
    def _decide(self, messages):
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="Here is the current weather you asked for.")
        # always call the real get_weather tool for Karachi, current conditions
        return AIMessage(content="", tool_calls=[{"name":"get_weather","args":{"city":"Karachi"},"id":"c1","type":"tool_call"}])
    def _generate(self, messages, stop=None, run_manager=None, **kw):
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])
    async def _agenerate(self, messages, stop=None, run_manager=None, **kw):
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])
    @property
    def _llm_type(self): return "always-current-weather"

wb.get_model = lambda: AlwaysCurrentWeather()   # ONLY the LLM is faked; tool + Open-Meteo are real

from a2a_agents.weather.server import app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9004, log_level="warning")
