# Relay

A small agentic workflow engine: a planner turns a goal into tool steps, an
executor walks them with retries and a token budget, and everything lands in
an append-only SQLite memory.

Relay is a **test fixture** for the code-kg skill. It is real, runnable code,
sized and shaped like a production repo on purpose - src-layout python, a
[TypeScript console](web/src/main.tsx), migrations, CI, docker - so the graph
built over it has something honest to measure.

## Running

```bash
pip install -e .
relay run "read the error log then query the runs table"
relay serve --port 8420
bash scripts/dev.sh
```

## Layout

- [src/relay/planner.py](src/relay/planner.py) - goal to steps
- [src/relay/executor.py](src/relay/executor.py) - the run loop
- [src/relay/tools/registry.py](src/relay/tools/registry.py) - decorator
  registration and name routing (deliberate dynamic dispatch)
- [src/relay/memory/store.py](src/relay/memory/store.py) - append-only memory
- [src/relay/server/app.py](src/relay/server/app.py) - table-routed HTTP API
- [migrations/](migrations/001_init.sql) - schema the sql tool queries
