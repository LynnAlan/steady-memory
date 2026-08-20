"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import error_payload, run_http, run_mcp
from .archive import ArchiveError
from .backup import restore_backup
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
    setup = commands.add_parser("setup", help="create or reuse an Agent-ready local vault"); setup.add_argument("path", nargs="?"); setup.add_argument("--name", default="My Steady Memory"); setup.add_argument("--weight-unit", choices=["kg", "jin"], default="kg"); setup.add_argument("--locale", default="zh-CN"); setup.add_argument("--timezone", default="Asia/Shanghai")
    init = commands.add_parser("init", help="initialize a portable archive"); init.add_argument("path", nargs="?"); init.add_argument("--name", default="My Steady Memory"); init.add_argument("--weight-unit", choices=["kg", "jin"], default="kg"); init.add_argument("--locale", default="zh-CN"); init.add_argument("--timezone", default="Asia/Shanghai")
    commands.add_parser("list-tools")
    call = commands.add_parser("call"); call.add_argument("tool"); call.add_argument("--arguments", "-a", type=arguments, default={}); call.add_argument("--request-id")
    commands.add_parser("validate"); commands.add_parser("doctor"); commands.add_parser("rebuild-index"); commands.add_parser("migrate"); commands.add_parser("mcp")
    serve = commands.add_parser("serve"); serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8765); serve.add_argument("--token")
    backup = commands.add_parser("backup"); backup.add_argument("--output", required=True); backup.add_argument("--replace", action="store_true"); backup.add_argument("--include-media", action="store_true")
    verify = commands.add_parser("verify-backup"); verify.add_argument("backup_path")
    restore = commands.add_parser("restore-backup", help="restore a verified backup into a new directory"); restore.add_argument("backup_path"); restore.add_argument("target_path")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "restore-backup":
            payload = restore_backup(args.backup_path, args.target_path)
        elif args.command in {"setup", "init"}:
            target = Path(args.path or args.root or (Path.cwd() / "vault" if args.command == "setup" else Path.cwd())).resolve()
            if args.command == "setup" and (target / "steady.json").is_file():
                validation = SteadyTools(target).call("validate_archive")["result"]
                payload = {"ready": validation["valid"], "existing": True, "root": str(target), "validation": validation}
            else:
                payload = initialize_archive(target, name=args.name, weight_unit=args.weight_unit, locale=args.locale, timezone_name=args.timezone)
                if args.command == "setup": payload = {"ready": True, "existing": False, **payload}
            if args.command == "setup":
                payload["agent_command"] = "python -m steady_memory call <tool> --arguments '<json>'"
                payload["mcp"] = {"command": sys.executable, "args": ["-m", "steady_memory", "--root", str(target), "mcp"]}
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
            elif args.command == "backup": payload = tools.call("backup_archive", {"output_path": args.output, "replace": args.replace, "include_media": args.include_media})
            elif args.command == "verify-backup": payload = tools.call("verify_backup", {"backup_path": args.backup_path})
            elif args.command == "mcp": run_mcp(tools); return 0
            elif args.command == "serve": run_http(tools, args.host, args.port, args.token); return 0
            else: raise RuntimeError("unreachable")
        print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0
    except (ArchiveError, json.JSONDecodeError) as exc:
        print(json.dumps(error_payload(exc), ensure_ascii=False, indent=2), file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
