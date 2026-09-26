"""Run with python -m defiantmaple. JSON output is suitable for spike tooling."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

from .archive import inspect_archive
from .catalog import duplicates, index_file, initialize, list_assets


def main(argv=None):
    parser = argparse.ArgumentParser(description="DefiantMaple local catalog tools")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "index", "list", "duplicates"):
        command = commands.add_parser(name)
        command.add_argument("database", type=Path)
        if name == "index":
            command.add_argument("file", type=Path)
        if name == "list":
            command.add_argument("--limit", type=int, default=100)
            command.add_argument("--offset", type=int, default=0)
    preview = commands.add_parser("inspect-zip")
    preview.add_argument("archive", type=Path)
    thumbnail = commands.add_parser("thumbnail")
    thumbnail.add_argument("database", type=Path)
    thumbnail.add_argument("asset_id")
    thumbnail.add_argument("cache", type=Path)
    thumbnail.add_argument("--max-edge", type=int, default=256)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            initialize(args.database)
            result = {"database": str(args.database), "schema_version": 1}
        elif args.command == "index":
            result = {"asset_id": index_file(args.database, args.file)}
        elif args.command == "list":
            result = list_assets(args.database, args.limit, args.offset)
        elif args.command == "duplicates":
            result = duplicates(args.database)
        elif args.command == "inspect-zip":
            result = inspect_archive(args.archive)
        else:
            from .thumbnail import thumbnail_for
            result = thumbnail_for(
                args.database, args.asset_id, args.cache, max_edge=args.max_edge
            )
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
