from __future__ import annotations

import argparse
import json

from python_refactor_mcp.executor import run_refactor
from python_refactor_mcp.models import RefactorRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python-refactor-mcp.cli")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source")
    parser.add_argument("--target")
    parser.add_argument("--module")
    parser.add_argument("--symbol")
    parser.add_argument("--new-name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", default="residual")
    parser.add_argument("--pytest-arg", action="append", dest="pytest_args")
    parser.add_argument("--source-root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verify = [item.strip() for item in args.verify.split(",") if item.strip()]
    request = RefactorRequest(
        operation=args.operation,
        project_root=args.project_root,
        source=args.source,
        target=args.target,
        module=args.module,
        symbol=args.symbol,
        new_name=args.new_name,
        dry_run=args.dry_run,
        verify=verify,  # type: ignore[arg-type]
        pytest_args=args.pytest_args,
        source_root=args.source_root,
    )
    result = run_refactor(request)
    print(result.model_dump_json())
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
