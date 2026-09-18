---
name: python-refactor
description: Prefer the python_refactor MCP tool for Python module/symbol moves and renames. Use when the user asks to move or rename a Python package, module, class, or function, or when imports must be updated across files. Do not use for business-logic edits or unsupported dynamic string rewrites.
---

# Python Refactor Router

## Purpose

Use this skill to keep structural Python refactors off the agent's multi-file edit loop. Rope updates imports; you only handle leftovers.

## Tool names

This skill talks to the `python-refactor` MCP server. Use the name your host exposes:

| Capability | OpenCode / Cursor | Claude Code |
| --- | --- | --- |
| python refactor | `python_refactor` or `python-refactor_python_refactor` | `mcp__python-refactor__python_refactor` |

In the steps below, `python_refactor` means whichever host-specific name applies.

## When To Use

- Move or rename a Python module or package
- Rename a top-level class, function, or `Class.method`
- Move a top-level class/function to another module
- The user asks to reorganize package paths and update imports

## Do NOT Use When

- The change is business logic inside a function
- The user only wants docstring/comment edits
- The operation is extract method, change signature, or inline
- The references live only in JSON/YAML/Markdown/shell (report leftovers; do not expect Rope to edit them)

## Required Steps

1. Resolve the target Python project absolute path as `project_root`.
2. Prefer `dry_run=true` first when the blast radius is unclear.
3. Call `python_refactor` with one of: `move_module`, `rename_module`, `rename_symbol`, `move_symbol`.
4. Do **not** glob/read/edit many files just to rewrite imports when this tool can do it.
5. After success, inspect `leftover_samples` / `remaining_old_references`. Manually fix only dynamic leftovers such as `importlib.import_module(...)`, `getattr(...)`, and config strings.
6. Direct edits remain allowed for business logic and for leftovers the tool cannot rewrite.

## Arguments

- `move_module`: `source` + `target` (dotted paths)
- `rename_module`: `source` + `new_name` (new_name is a single identifier; changing package requires `move_module`)
- `rename_symbol`: `module` + `symbol` + `new_name` (`symbol` is `Name` or `Class.method`)
- `move_symbol`: `module` + `symbol` + `target` (destination module dotted path)

Always pass `project_root` as an absolute directory. The result is compact JSON: file counts and paths, never diffs.
