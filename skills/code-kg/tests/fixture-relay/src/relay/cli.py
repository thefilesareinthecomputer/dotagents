"""CLI: the human entry point. `relay run "goal"`, `relay serve`, etc."""
from __future__ import annotations

import argparse
import json
import sys

from relay.config import load_config
from relay.errors import RelayError
from relay.executor import Executor
from relay.memory.compact import compact, plan_compaction
from relay.memory.store import MemoryStore
from relay.report import as_markdown, as_text
from relay.scheduler import Scheduler
from relay.server.app import RelayServer
from relay.tools.registry import get_registry


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(max_steps=args.max_steps)
    store = MemoryStore(config.memory_path)
    try:
        result = Executor(config, store).run(args.goal)
    except RelayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    if args.report == "markdown":
        print(as_markdown(result))
    elif args.report == "text":
        print(as_text(result))
    else:
        print(json.dumps(result.summary(), indent=2, sort_keys=True))
    return 0 if not result.failed else 2


def cmd_serve(args: argparse.Namespace) -> int:
    config = load_config(server_port=args.port)
    store = MemoryStore(config.memory_path)
    executor = Executor(config, store)
    scheduler = Scheduler(lambda goal: executor.run(goal).summary())
    if args.compact_every:
        scheduler.add("compact", "compact memory", args.compact_every)
    print(f"relay serving on 127.0.0.1:{config.server_port}",
          file=sys.stderr)
    RelayServer(config, store).serve_forever()
    return 0


def cmd_compact(args: argparse.Namespace) -> int:
    config = load_config()
    store = MemoryStore(config.memory_path)
    try:
        plan = plan_compaction(store, keep_versions=args.keep)
        if args.dry_run:
            print(json.dumps(vars(plan), indent=2, sort_keys=True))
            return 0
        result = compact(store, keep_versions=args.keep)
        print(result.describe())
        return 0
    finally:
        store.close()


def cmd_tools(args: argparse.Namespace) -> int:
    for spec in get_registry().describe_all():
        print(f"{spec['name']:<8} {spec['description']}")
        if args.verbose:
            print(f"         {spec['signature']}")
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    config = load_config()
    store = MemoryStore(config.memory_path)
    try:
        records = store.search(args.query, limit=args.limit)
        for record in records:
            print(f"[{record.kind}] {record.key}: {record.body[:120]}")
        return 0 if records else 1
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="relay")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="execute a goal")
    p.add_argument("goal")
    p.add_argument("--max-steps", type=int, default=12)
    p.add_argument("--report", choices=["json", "text", "markdown"],
                   default="json")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("serve", help="start the HTTP API")
    p.add_argument("--port", type=int, default=8420)
    p.add_argument("--compact-every", type=float, default=0)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("compact", help="fold surplus memory history")
    p.add_argument("--keep", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_compact)

    p = sub.add_parser("tools", help="list registered tools")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(fn=cmd_tools)

    p = sub.add_parser("memory", help="search stored memory")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(fn=cmd_memory)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
