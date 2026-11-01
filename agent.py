"""SunCedar agent: OpenAI Agents SDK as the MCP Host/Client, connected to server.py over stdio.

  python agent.py --list-tools   # connect to the MCP server and list its tools (no API key needed)
  python agent.py --demo         # run the scripted demo queries
  python agent.py                # interactive chat

Model: Gemini through its OpenAI-compatible endpoint (GEMINI_API_KEY), or OpenAI (OPENAI_API_KEY).
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                             "gemini-3.8-flash"] if m]

INSTRUCTIONS = """You are SunCedar Energy's solar assistant for homes in Lebanon.
Use the MCP tools, never guess numbers:
- Customer lists appliances or asks which package fits, and does NOT ask for a visit -> size_system.
- Customer already knows the package and wants a visit -> book_site_visit.
- Customer lists appliances AND wants a visit in one request -> plan_solar_install (it sizes, then books).
- Never invent a name, email or town. If one is missing for a booking, ask for it.
- If a tool returns an error, explain it plainly and say what the customer can do.
Keep answers short (2-4 sentences) and mention the booking ID when a visit is booked."""

DEMO = [
    "I run a fridge, lights, a TV and a washing machine. Which package do I need?",
    "Please book a site visit for the Comfort package. I'm Abbas Yassine, abbasyassine@example.com, in Jounieh.",
    "I have an inverter AC, a fridge and lights. Size my system and book a visit: Abbas Yassine, "
    "abbasyassine@example.com, Hamra.",
    "Book the Starter package for me in Zahle. Name Abbas Yassine, email abbasyassine@example.com.",
]


def make_model(index: int = 0):
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
                             base_url=GEMINI_URL)
        name = GEMINI_MODELS[min(index, len(GEMINI_MODELS) - 1)]
        return OpenAIChatCompletionsModel(model=name, openai_client=client), name
    if os.getenv("OPENAI_API_KEY"):
        name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        return name, name
    sys.exit("No API key: set GEMINI_API_KEY (or OPENAI_API_KEY) in .env or the environment.")


def server_params():
    return {"command": sys.executable, "args": [str(HERE / "server.py")], "cwd": str(HERE)}


def show_round_trip(result) -> None:
    """Print each tool call the agent made and what the MCP server returned."""
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            raw = item.raw_item
            name = getattr(raw, "name", None) or (raw.get("name") if isinstance(raw, dict) else "?")
            args = getattr(raw, "arguments", None) or (raw.get("arguments") if isinstance(raw, dict) else "")
            print(f"  [agent -> MCP client -> server] call {name}({args})")
        elif isinstance(item, ToolCallOutputItem):
            out = item.output if isinstance(item.output, str) else json.dumps(item.output)
            print(f"  [server -> MCP client -> agent] {out[:300]}")


async def ask(server, question: str, history: list, model_index: int = 0):
    model, name = make_model(model_index)
    agent = Agent(name="SunCedar assistant", instructions=INSTRUCTIONS, mcp_servers=[server], model=model)
    try:
        return await Runner.run(agent, history + [{"role": "user", "content": question}], max_turns=8), name
    except Exception as e:
        text = str(e)
        if model_index + 1 < len(GEMINI_MODELS) and ("404" in text or "429" in text or "RESOURCE_EXHAUSTED" in text):
            print(f"  (model {name} unavailable or over quota, trying the next one)")
            return await ask(server, question, history, model_index + 1)
        raise


async def main(mode: str) -> None:
    set_tracing_disabled(True)  # tracing would need an OpenAI key
    async with MCPServerStdio(params=server_params(), name="suncedar-solar", cache_tools_list=True,
                              client_session_timeout_seconds=30) as server:
        tools = await server.list_tools()
        print(f"Connected to MCP server 'suncedar-solar' with {len(tools)} tools: {[t.name for t in tools]}\n")
        if mode == "list":
            for t in tools:
                print(f"- {t.name}: {t.description.splitlines()[0]}")
                print(f"  input schema: {json.dumps((getattr(t, 'inputSchema', None) or getattr(t, 'input_schema', {})).get('properties', {}))}")
            return
        history = []
        questions = DEMO if mode == "demo" else None
        while True:
            if questions is not None:
                if not questions:
                    break
                q = questions.pop(0)
                print(f"USER: {q}")
            else:
                q = input("USER: ").strip()
                if q.lower() in ("", "quit", "exit"):
                    break
            result, model_name = await ask(server, q, history)
            show_round_trip(result)
            print(f"AGENT ({model_name}): {result.final_output}\n")
            history = result.to_input_list() if mode != "demo" else []


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    p.add_argument("--list-tools", action="store_true")
    a = p.parse_args()
    asyncio.run(main("list" if a.list_tools else "demo" if a.demo else "chat"))
