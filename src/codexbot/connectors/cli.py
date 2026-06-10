"""Headless connector management — configure connectors without the web UI.

Installed as ``codexbot-connectors``. Lets you set up a connector on a server
that doesn't run the web UI: export the config from one box (or the UI) as
JSON, drop it on another, and import it from the console.

  codexbot-connectors list
  codexbot-connectors export <id>            # JSON to stdout
  codexbot-connectors export --all           # all connectors as a JSON array
  codexbot-connectors export <id> --out f.json
  codexbot-connectors import f.json          # create (use '-' for stdin)
  codexbot-connectors import f.json --replace <id>   # update existing
  codexbot-connectors enable <id>
  codexbot-connectors disable <id>
  codexbot-connectors rm <id>

Connectors are loaded when the codexbot service starts, so on a fresh box the
flow is: import → start the service. To apply changes to an already-running
instance, restart it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import store


def _dump(rec: store.ConnectorRecord) -> dict[str, Any]:
    """Portable connector representation (no instance-local id/timestamps)."""
    return {
        "type": rec.type,
        "name": rec.name,
        "enabled": rec.enabled,
        "config": rec.config,
    }


def _cmd_list(args: argparse.Namespace) -> int:
    rows = store.list_connectors()
    if not rows:
        print("No connectors configured.")
        return 0
    for r in rows:
        state = "on " if r.enabled else "off"
        print(f"{r.id}  [{state}]  {r.type:<8}  {r.name}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    if args.all:
        data: Any = [_dump(r) for r in store.list_connectors()]
    elif args.id:
        rec = store.get_connector(args.id)
        if rec is None:
            print(f"connector not found: {args.id}", file=sys.stderr)
            return 1
        data = _dump(rec)
    else:
        print("specify a connector id or --all", file=sys.stderr)
        return 2
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        return 1
    items = data if isinstance(data, list) else [data]
    if args.replace and len(items) != 1:
        print("--replace expects exactly one connector in the JSON", file=sys.stderr)
        return 2
    for item in items:
        if not isinstance(item, dict) or "type" not in item or "name" not in item:
            print("each entry needs at least 'type' and 'name'", file=sys.stderr)
            return 1
        config = item.get("config") or {}
        enabled = bool(item.get("enabled", False))
        if args.replace:
            rec = store.update_connector(
                args.replace, name=item["name"], config=config, enabled=enabled
            )
            if rec is None:
                print(f"connector not found: {args.replace}", file=sys.stderr)
                return 1
            print(f"updated {rec.id}  {rec.name}")
        else:
            rec = store.create_connector(
                type=item["type"],
                name=item["name"],
                config=config,
                enabled=enabled,
            )
            print(f"created {rec.id}  {rec.name}")
    print("Restart the codexbot service to apply.", file=sys.stderr)
    return 0


def _cmd_set_enabled(args: argparse.Namespace, enabled: bool) -> int:
    rec = store.update_connector(args.id, enabled=enabled)
    if rec is None:
        print(f"connector not found: {args.id}", file=sys.stderr)
        return 1
    print(f"{'enabled' if enabled else 'disabled'} {rec.id}  {rec.name}")
    print("Restart the codexbot service to apply.", file=sys.stderr)
    return 0


def _cmd_rm(args: argparse.Namespace) -> int:
    if not store.delete_connector(args.id):
        print(f"connector not found: {args.id}", file=sys.stderr)
        return 1
    print(f"removed {args.id}")
    print("Restart the codexbot service to apply.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codexbot-connectors",
        description="Manage codexbot connectors from the console (no web UI).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list configured connectors")

    p_export = sub.add_parser("export", help="export connector config as JSON")
    p_export.add_argument("id", nargs="?", help="connector id (omit with --all)")
    p_export.add_argument("--all", action="store_true", help="export every connector")
    p_export.add_argument("--out", help="write to file instead of stdout")

    p_import = sub.add_parser("import", help="create/update a connector from JSON")
    p_import.add_argument("file", help="JSON file, or '-' for stdin")
    p_import.add_argument("--replace", metavar="ID", help="update this connector")

    sub.add_parser("enable", help="enable a connector").add_argument("id")
    sub.add_parser("disable", help="disable a connector").add_argument("id")
    sub.add_parser("rm", help="delete a connector").add_argument("id")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "export":
        return _cmd_export(args)
    if args.cmd == "import":
        return _cmd_import(args)
    if args.cmd == "enable":
        return _cmd_set_enabled(args, True)
    if args.cmd == "disable":
        return _cmd_set_enabled(args, False)
    if args.cmd == "rm":
        return _cmd_rm(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
