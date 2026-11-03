# Agent protocols - which standard this station uses for which link

Agents here talk over four kinds of link, and each has its own standard.
This file records which one the station uses or plans for each link, where its canonical documentation lives, and what is built.
Versions, dates and governance are kept once, in the ai-engineering corpus ([`agent-stack-map.md`](../skills/ai-engineering/resources/agent-stack-map.md) Section B.1 for ACP and B.3 for the full comparison), so they are refreshed in one place.

## The links

| Link | Standard | Canonical docs | State in this station |
|---|---|---|---|
| Orchestrator to one local harness session | ACP (Agent Client Protocol, Zed and JetBrains) | [agentclientprotocol.com](https://agentclientprotocol.com/), [spec repo](https://github.com/agentclientprotocol/agent-client-protocol), [registry](https://github.com/agentclientprotocol/registry) | Designed, not built: the station's harness session layer design makes ACP the driver for every non-Claude harness, with the Claude Agent SDK for Claude Code. The group chat in `app/` still parses each CLI's JSONL directly. |
| Agent to tools and context | MCP | [spec 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28), [spec repo](https://github.com/modelcontextprotocol/modelcontextprotocol), [registry](https://github.com/modelcontextprotocol/registry) | In use per harness; the placement policy is in [`MCP-PLACEMENT.md`](MCP-PLACEMENT.md). |
| Agent to agent across machines, people or vendors | A2A (Agent2Agent) | [a2a-protocol.org](https://a2a-protocol.org/latest/), [spec repo](https://github.com/a2aproject/A2A), [Python SDK](https://github.com/a2aproject/a2a-python) | Not adopted. A design note comparing A2A with generalizing `agent-mail` and `codex-task` is backlogged. |
| Agent to a user-facing UI | AG-UI | [repo](https://github.com/ag-ui-protocol/ag-ui) | Not used; the `app/` UI has its own event frames. |

Asynchronous messages between agents on this machine go through the `agent-mail` skill (files in each agent root's `inbox/`), which follows none of these standards and needs no network listener.

## Related standards, not used here

- AGNTCY ([SLIM](https://github.com/agntcy/slim), [Agent Directory](https://github.com/agntcy/dir), [OASF](https://github.com/agntcy/oasf)) covers agent transport, discovery and an agent description schema.
- ANP ([AgentNetworkProtocol](https://github.com/agent-network-protocol/AgentNetworkProtocol)) covers agent identity and discovery on the open web through W3C DIDs.
- The Agentic AI Foundation ([projects](https://aaif.io/projects)) governs MCP, A2A, AGENTS.md, goose and Agent Skills.
- Three other protocols share the ACP acronym and are unrelated: IBM's Agent Communication Protocol (merged into A2A), AGNTCY's Agent Connect Protocol, and the Agentic Commerce Protocol.

## The rule for choosing

Inside one machine, where every agent is a CLI this station launches, drive it over ACP or the Claude Agent SDK and keep coordination state in the orchestrator.
A2A applies only when an agent must be reachable by agents this station does not launch.
That endpoint needs authentication before it exists, because an A2A listener without authentication accepts work from anyone who can reach the port.
