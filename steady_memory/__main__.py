"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import error_payload, run_http, run_mcp
from .archive import ArchiveError
from .migrations import initialize_archive
from .tools import ALL_SCOPES, SteadyTools


def arguments(value: str) -> dict:
    if value.startswith("@"): value = Path(value[1:]).read_text(encoding="utf-8")
    parsed = json.loads(value)
    if not isinstance(parsed, dict): raise argparse.ArgumentTypeError("arguments must be a JSON object")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="steady-memory", description="Local-first personal memory archive")
    root.add_argument("--root", help="archive directory (or STEADY_ROOT)")
    root.add_argument("--read-only", action="store_true")
    root.add_argument("--scope", action="append", choices=sorted(ALL_SCOPES), help="allowed capability scope; repeatable")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize a portable archive"); init.add_argument("path", nargs="?"); init.add_argument("--name", default="My Steady Memory"); init.add_argument("--weight-unit", choices=["kg", "jin"], default="kg"); init.add_argument("--locale", default="zh-CN"); init.add_argument("--timezone", default="Asia/Shanghai")
    commands.add_parser("list-tools")
    call = commands.add_parser("call"); call.add_argument("tool"); call.add_argument("--arguments", "-a", type=arguments, default={}); call.add_argument("--request-id")
    commands.add_parser("validate"); commands.add_parser("doctor"); commands.add_parser("rebuild-index"); commands.add_parser("migrate"); commands.add_parser("mcp")
    serve = commands.add_parser("serve"); serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8765); serve.add_argument("--token")
    backup = commands.add_parser("backup"); backup.add_argument("--output", required=True); backup.add_argument("--replace", action="store_true")
    verify = commands.add_parser("verify-backup"); verify.add_argument("backup_path")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init": payload = initialize_archive(args.path or args.root or Path.cwd(), name=args.name, weight_unit=args.weight_unit, locale=args.locale, timezone_name=args.timezone)
        else:
            tools = SteadyTools(args.root, read_only=args.read_only, scopes=set(args.scope) if args.scope else None)
            if args.command == "list-tools": payload = {"tools": tools.definitions}
            elif args.command == "call": payload = tools.call(args.tool, args.arguments, args.request_id)
            elif args.command == "validate": payload = tools.call("validate_archive")
            elif args.command == "doctor":
                validation = tools.call("validate_archive")["result"]
                payload = {"healthy": validation["valid"], "validation": validation, "read_only_available": True}
            elif args.command == "rebuild-index": payload = tools.call("rebuild_index")
            elif args.command == "migrate": payload = tools.call("migrate_archive")
            elif args.command == "backup": payload = tools.call("backup_archive", {"output_path": args.output, "replace": args.replace})
            elif args.command == "verify-backup": payload = tools.call("verify_backup", {"backup_path": args.backup_path})
            elif args.command == "mcp": run_mcp(tools); return 0
            elif args.command == "serve": run_http(tools, args.host, args.port, args.token); return 0
            else: raise RuntimeError("unreachable")
        print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0
    except (ArchiveError, json.JSONDecodeError) as exc:
        print(json.dumps(error_payload(exc), ensure_ascii=False, indent=2), file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
