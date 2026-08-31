# Relay architecture

One-way flow, four seams.

```
goal -> Planner -> Plan -> Executor -> ToolRegistry -> tools
                              |             |
                        MemoryStore    (dynamic dispatch:
                         AuditLog       the table IS the routing)
```

## Seams a deployment replaces

- [LLMClient._transport](../src/relay/llm/client.py) - the model call.
- [web_tool.install_fetcher](../src/relay/tools/web_tool.py) - the network.
- [Scheduler](../src/relay/scheduler.py)'s clock and callback - time and work.
- [Telemetry](../src/relay/telemetry.py) - wrap for OTLP; events are JSON lines.

## Invariants

- Memory is append-only; [compaction](../src/relay/memory/compact.py) folds
  history but never touches the latest record per key.
- Every run lands in the hash-chained [audit log](../src/relay/audit.py).
- The [HTTP surface](../src/relay/server/app.py) is a data table of routes;
  handlers raise nothing outward.
- Plans are data before they are behavior: inspect, edit, or refuse a
  [Plan](../src/relay/planner.py) before any tool runs.
