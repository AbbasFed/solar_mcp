# SunCedar MCP Toolkit · FastMCP + OpenAI Agents SDK

**EECE 503P/798S Agentic Systems · C5 Agent Tools** · Abbas Yassine

**🎥 Demo video:** _add link here_

A small MCP toolkit for **SunCedar Energy**, the fictional Beirut solar installer from C3/C4. It has exactly three
tools on a **FastMCP** server, used by an agent built with the **OpenAI Agents SDK** (the MCP Host/Client), running on
Gemini through its OpenAI-compatible endpoint.

| Category | Tool | What it does | Typed output | Failure handled |
|---|---|---|---|---|
| **Data** | `size_system(appliances: list[str])` | Estimates daily kWh and recommends a package. Read-only. | `Sizing` | no recognised appliances, empty list, load too big |
| **Action** | `book_site_visit(name, email, town, package)` | Saves a site-visit booking to `data/bookings.json`, returns a `booking_id`. | `Booking` | invalid email, town not served, unknown package |
| **Orchestration** | `plan_solar_install(appliances, name, email, town)` | Runs `size_system`, then `book_site_visit` with the recommended package. | `InstallPlan` | says which step failed ("Sizing succeeded … but the booking failed") |

Plus one **resource**, `suncedar://packages`: the package catalogue as pure read-only data.

```
User ─▶ Agent (OpenAI Agents SDK = MCP Host) ─▶ MCP Client ─stdio/JSON-RPC─▶ FastMCP server (server.py) ─▶ core.py
   ◀──────────────── final answer ◀──────────── tool result ◀─────────────────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `core.py` | Business logic as plain functions (no MCP), so it is easy to test |
| `server.py` | FastMCP server: `@mcp.tool` ×3, `@mcp.resource` ×1, Pydantic output models, clear `ToolError`s, logs every call to stderr |
| `agent.py` | OpenAI Agents SDK agent connected to `server.py` with `MCPServerStdio`; prints each round trip |
| `tests/test_tools.py` | 14 tests: each tool, each failure case, and the MCP layer through an in-memory FastMCP client |
| `suncedar_mcp_demo.ipynb` | Self-contained Colab notebook: writes all the files above, runs the tests and the agent demo |
| `SUMMARY.md` | Part 1: article summary and critique of the Fetch MCP server |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # add GEMINI_API_KEY (free at https://aistudio.google.com/apikey)
```

## Run

```bash
python -m pytest -v            # 14 tests, no API key needed
python agent.py --list-tools   # connect to the MCP server and list its tools, no API key needed
python agent.py --demo         # 4 scripted requests: data, action, orchestration, failure
python agent.py                # interactive chat
```

**In Colab:** open `suncedar_mcp_demo.ipynb`, add `GEMINI_API_KEY` in Secrets (Notebook access on), and choose
*Run all*. The notebook writes every project file itself, so nothing needs to be uploaded.

In the demo output, `[MCP server] …` lines come from the server process, and `[agent -> MCP client -> server]` /
`[server -> MCP client -> agent]` lines are printed by the host, so the whole round trip is visible.

## Design notes

- **Single purpose.** Each tool does one thing; the only tool that does two things is the Orchestration tool, and
  that is its job. The descriptions start with the category (DATA / ACTION / ORCHESTRATION) and tell the model when to
  use each one.
- **Orchestration reuses logic, not MCP calls.** `plan_solar_install` calls the same `core` functions the other two
  tools wrap, so the three tools always agree, and there is no server calling itself over the network.
- **Predictable failures.** Every user-fixable problem raises `ToolError` with a message that says what was wrong and
  what is allowed. Nothing is written to `bookings.json` when a booking fails.
- **Typed everything.** Arguments are typed (with an enum for `package`), and outputs are Pydantic models, so FastMCP
  publishes an output schema and returns structured content.

## Reflection

I drew the line between the tools by asking what changes state. Sizing a system only reads data and can be called
freely, even speculatively, while a booking has a side effect that someone at SunCedar will act on. Keeping them apart
means the agent can explore options ("what if I add an AC?") without accidentally creating bookings, and each tool can
fail in its own clear way. The Orchestration tool exists because the most common real request, "here are my
appliances, book me a visit", needs both in a fixed order, and doing it in one tool removes the risk of the model
booking a package other than the one it just sized. When it fails, it reports which step failed, which was the main
challenge: an orchestrator that swallows errors from inner steps becomes unpredictable very quickly.

Three tools felt right for this scope: one per category kept each interface small, and the agent never had to choose
between overlapping tools. In a real deployment I would add a `cancel_booking` action and a `check_service_area` data
tool (the area check currently sits inside the booking tool's validation), move bookings from a JSON file to a
database, require human confirmation before the action tool runs (the Agents SDK supports approval for MCP tools), and
serve the toolkit over HTTP so other hosts, such as Claude Desktop, could use the same server.
