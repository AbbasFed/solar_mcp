# Part 1 · MCP article summary and server critique

**Author:** Abbas Yassine · EECE 503P/798S Agentic Systems · C5

## The Model Context Protocol (Hugging Face article)

The article presents MCP as an open protocol, introduced by Anthropic in November 2024, that standardises how AI
applications connect to external tools and data. It is often compared to a USB-C port for AI: instead of writing a
custom integration for every pair of model application and data source (an M×N problem), each application implements
the protocol once as a client and each tool provider implements it once as a server, turning the problem into M+N.

MCP has three roles. The **Host** is the AI application the user interacts with, such as Claude Desktop, an IDE or a
custom agent; it owns the model and decides when to use external context. Inside the host, each **Client** keeps a
one-to-one connection with a single server and handles the protocol messages (JSON-RPC) for it. The **Server** is a
lightweight program that exposes capabilities: **tools** (functions the model can call, possibly with side effects),
**resources** (read-only data the application can load as context) and **prompts** (reusable templates). Servers run
locally over stdio or remotely over HTTP, and clients discover their capabilities at runtime instead of having them
hard-coded. The article also notes open challenges: security for tools with side effects, authentication for remote
servers, and the work of running many servers.

## Server explored: the Fetch MCP server

The reference Fetch server (`modelcontextprotocol/servers/fetch`) exposes essentially one tool, `fetch`, which
retrieves a URL and converts the HTML into Markdown so a model can read it. Its arguments are typed and documented
(`url`, `max_length`, `start_index`, `raw`).

**Against the design principles from class:**
- *Well-defined interface:* strong. One clear purpose, typed parameters with defaults, and a description that tells the
  model what it returns.
- *Isolated functionality:* mostly good. Fetching and converting are bundled, but they are one user-level intent
  ("read this page"), so splitting them would add calls without adding value.
- *Predictable behaviour:* good. It respects `robots.txt` by default and returns explicit errors for failed requests,
  but output size and content can vary a lot between sites, and the `raw` flag changes the output format, which is
  the one place where a single tool does two different things.

Overall it is a good single-purpose tool; its main risk is its power, since an unrestricted fetch can reach
internal network addresses.
