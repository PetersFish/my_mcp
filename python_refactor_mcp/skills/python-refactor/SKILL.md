---
name: python-refactor
description: Prefer the python_refactor MCP tool for Python module/symbol moves and renames, inspect_symbol for definition/references/type, apply_codemod for registered LibCST rewrites, and verify_refactor for post-mutation checks. Use when the user asks to move or rename a Python package, module, class, or function, or when imports must be updated across files. Do not use for business-logic edits or unsupported dynamic string rewrites.
---

# Python Refactor Router

## Purpose

Use this skill to keep structural Python refactors off the agent's multi-file edit loop. Rope updates imports; registered LibCST codemods handle mechanical rewrites; you only handle leftovers the tool already listed.

## Tool names

This skill talks to the `python-refactor` MCP server. Use the name your host exposes:

| Capability | OpenCode / Cursor | Claude Code |
| --- | --- | --- |
| python refactor | `python_refactor` or `python-refactor_python_refactor` | `mcp__python-refactor__python_refactor` |
| inspect symbol | `inspect_symbol` or `python-refactor_inspect_symbol` | `mcp__python-refactor__inspect_symbol` |
| apply codemod | `apply_codemod` or `python-refactor_apply_codemod` | `mcp__python-refactor__apply_codemod` |
| verify refactor | `verify_refactor` or `python-refactor_verify_refactor` | `mcp__python-refactor__verify_refactor` |

In the steps below, tool names mean whichever host-specific name applies.

## When To Use

- Look up a symbol's definition, references, or type (`inspect_symbol`) instead of grep/read loops
- Move or rename a Python module or package
- Rename a top-level class, function, or `Class.method`
- Move a top-level class/function to another module
- Rewrite qualified names / call keywords / decorators via `apply_codemod`
- Re-run verification without mutating (`verify_refactor`)
- The user asks to reorganize package paths and update imports

## Do NOT Use When

- The change is business logic inside a function
- The user only wants docstring/comment edits
- The operation is extract method, change signature, or inline
- The references live only in JSON/YAML/Markdown/shell (report leftovers; do not expect Rope to edit them)
- You want to upload arbitrary LibCST transformer source (not allowed)

## Required Steps

1. Resolve the target Python project absolute path as `project_root`.
2. If you need definition/references/type first, call `inspect_symbol` with 1-based `line`/`character`. Do not grep the repo for that.
3. Prefer `dry_run=true` first when the blast radius is unclear.
4. Call `python_refactor` with one of: `move_module`, `rename_module`, `rename_symbol`, `move_symbol`.
   Symbol rename/move preflights via Pyright; if Pyright is down, default `semantic_mode=best_effort` still runs Rope. Use `required` only when you must abort without semantics.
   Do **not** pass `verification_mode=standard|full` (or `verify` containing `pyright`/`pytest`) on this mutate call unless the user explicitly asks for MCP-side heavy verify. Large renames + heavy verify often hit MCP host timeout (`-32001`). Default mutate verification is fast (`diagnostics` + `ruff`).
5. For mechanical rewrites (`normalize_imports` / `replace_qualified_name` / `replace_call_keyword` / `replace_decorator`), call `apply_codemod` with `dry_run=true` first, then `dry_run=false`.
6. Do **not** glob/read/edit many files just to rewrite imports when these tools can do it.
7. `import_issues` is a structured list of Rope/Pyright import diagnostics in
   `file:line:column: kind: message` form. Fix each listed location before broad
   verification; do not search the repo to rediscover them.
8. After success, `leftover_samples` is already the residual search. Edit only those `file:line` hits using `leftover_replace_from` -> `leftover_replace_to`. Follow `next_action`.
9. If `leftover_samples` is empty **and** `verification.residual` is `ok` or `failed`, skip leftover work. Do **not** glob or grep the repo to confirm.
10. A `dry_run` result never scans residual, so it says nothing about leftovers. Re-run without `dry_run` instead of searching.
11. `empty_packages` are local keep-or-delete decisions, not a search task.
12. Prefer **local/CI** for Ruff / Pyright / pytest after leftovers. Use a separate `verify_refactor` for a fast re-check (default) or opt-in heavier modes when local tooling is unavailable (see Verification). Do not block local/CI checks on leftover search finishing.

Direct edits remain allowed for business logic and for leftovers the tool cannot rewrite.

## Leftover anti-patterns

- Do NOT glob `**/*.{py,toml}` or similar wide patterns for leftovers.
- Do not run a full-repo Grep/rg in parallel with leftover edits.
- Do not block Ruff/Pyright/pytest on leftover search finishing.
- If `remaining_old_references` exceeds the sample list, run one exact search for `leftover_replace_from` **only when it is a dotted module path** (`move_module` / `rename_module`).
- For `rename_symbol` / `move_symbol` the needle is a bare identifier such as `save`. Never grep that repo-wide; edit the listed hits and let Ruff/Pyright surface the rest.

## Verification

Rule of thumb: **mutate = fast**; **verify_refactor = fast**; **local/CI = ruff/pyright/pytest**; use MCP `standard`/`full` only when local tooling is unavailable or the user explicitly asks. Always call `verify_refactor` as a **separate** request from mutate; pass `changed_files` and `needles` from the mutate result when useful.

| Mode | Steps | Use when | Avoid when |
| --- | --- | --- | --- |
| **default** (omit `verification_mode`) | LSP `diagnostics` + `ruff` | Quick default check after mutate / leftover edits. | — |
| **fast** | LSP `diagnostics` + `ruff` on `changed_files` | Local/CI not available; want a quick MCP lint signal. Separate call from mutate. | Prefer local ruff if available; large sets near MCP timeout |
| **standard** | `residual` + `ruff` + `pyright` + targeted `pytest` (≤10 test files) | Cannot rely on local/CI and need an MCP gate; medium blast radius. Separate call. | Same request as mutate; large renames (`-32001`); when local/CI will run the same tools |
| **full** | same as standard but full pytest suite | Rare: need full suite inside MCP and no local pytest. | Default workflows; prefer local/CI `pytest` |

### How to judge local/CI has ruff / pyright / pytest

Treat tools **independently**. Bias toward deferring to local/CI. Do not deep-scrape CI logs or install tools just to probe.

Any one positive ⇒ that tool is “available locally” (config/CI alone counts even if the binary is not installed yet):

1. **PATH / venv** from `project_root`: `command -v ruff`, `command -v pyright`, `command -v pytest`
2. **Project declared tooling**: ruff → `[tool.ruff]` / `ruff.toml` / `.ruff.toml`; pyright → `[tool.pyright]` / `pyrightconfig.json` / `[tool.basedpyright]`; pytest → `[tool.pytest]` / `pytest.ini` / tests `conftest.py` / pytest in deps
3. **CI / hooks** mention the tool: `.github/workflows/*`, `.pre-commit-config.yaml`, etc.

The default MCP check is `fast`; use local/CI for authoritative Ruff / Pyright / pytest results. Use MCP `standard` only if PATH probe fails **and** config/CI/hooks are empty **and** the user did not say they will run local/CI. If unsure and the repo looks like a normal app (`pyproject.toml` + tests): **default to defer** heavier checks.

## Arguments

- `move_module`: `source` + `target` (dotted paths)
- `rename_module`: `source` + `new_name` (new_name is a single identifier; changing package requires `move_module`)
- `rename_symbol`: `module` + `symbol` + `new_name` (`symbol` is `Name` or `Class.method`)
- `move_symbol`: `module` + `symbol` + `target` (destination module dotted path)
- Optional `semantic_mode`: `best_effort` (default) or `required`
- Optional `verification_mode` on mutate: prefer omit (fast). Use `standard` / `full` only when explicitly needed (explicit `verify` list wins when provided)
- `verify_refactor`: default fast; see Verification table for `fast` / `standard` / `full`
- `apply_codemod`: `codemod` + `params` + optional `paths` (default `dry_run=true`)

Always pass `project_root` as an absolute directory (macOS and Windows). The result is compact JSON: file counts, leftover samples, and `next_action`; never diffs.

`inspect_symbol` uses 1-based `line`/`character` and returns a truncated reference list plus `reference_count`. Do not grep to confirm.
