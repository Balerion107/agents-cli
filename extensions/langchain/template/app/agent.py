# ruff: noqa
"""LangChain agent: a Gemini ReAct agent with a sample tool.

Uses Vertex AI with Application Default Credentials, or AI Studio when
`GOOGLE_API_KEY` or `GEMINI_API_KEY` is set in the environment or a `.env` file.
"""

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

load_dotenv()

if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
    import google.auth

    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

LLM = "gemini-3.8-flash"

llm = ChatGoogleGenerativeAI(model=LLM, temperature=0)


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather."""
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


root_agent: CompiledStateGraph = create_agent(
    model=llm, tools=[get_weather], system_prompt="You are a helpful assistant"
)
