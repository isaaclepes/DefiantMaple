"""Run with python -m defiantmaple. JSON output is suitable for spike tooling."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

from .archive import inspect_archive
from .catalog import SCHEMA_VERSION, duplicates, index_file, initialize, list_assets


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
    add_source = commands.add_parser("add-source")
    add_source.add_argument("database", type=Path)
    add_source.add_argument("root", type=Path)
    add_source.add_argument("--name")
    add_source.add_argument(
        "--existing-file-policy",
        choices=("inbox", "reviewed", "ignore_until_modified"),
        required=True,
    )
    add_source.add_argument("--non-recursive", action="store_true")
    source_list = commands.add_parser("list-sources")
    source_list.add_argument("database", type=Path)
    scan = commands.add_parser("scan-sources")
    scan.add_argument("database", type=Path)
    scan.add_argument("--source-id")
    scan.add_argument("--quiet-seconds", type=float, default=2.0)
    for name in ("pause-source", "resume-source"):
        command = commands.add_parser(name)
        command.add_argument("database", type=Path)
        command.add_argument("source_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            initialize(args.database)
            result = {"database": str(args.database), "schema_version": SCHEMA_VERSION}
        elif args.command == "index":
            result = {"asset_id": index_file(args.database, args.file)}
        elif args.command == "list":
            result = list_assets(args.database, args.limit, args.offset)
        elif args.command == "duplicates":
            result = duplicates(args.database)
        elif args.command == "inspect-zip":
            result = inspect_archive(args.archive)
        elif args.command == "thumbnail":
            from .thumbnail import thumbnail_for
            result = thumbnail_for(
                args.database, args.asset_id, args.cache, max_edge=args.max_edge
            )
        else:
            from .sources import add_source, list_sources, scan_sources, set_source_enabled
            if args.command == "add-source":
                result = add_source(
                    args.database, args.root, name=args.name,
                    existing_file_policy=args.existing_file_policy,
                    recursive=not args.non_recursive,
                )
            elif args.command == "list-sources":
                result = list_sources(args.database)
            elif args.command == "scan-sources":
                result = scan_sources(
                    args.database, source_id=args.source_id,
                    quiet_seconds=args.quiet_seconds,
                )
            else:
                result = set_source_enabled(
                    args.database, args.source_id,
                    enabled=args.command == "resume-source",
                )
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
