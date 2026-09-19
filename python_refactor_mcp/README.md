# python-refactor-mcp

基于 **Rope** 的确定性 Python 结构重构 stdio MCP。Agent 只提交重构意图（移动/重命名模块或符号）；工具改文件并返回 compact JSON 摘要，不把 diff 或文件内容灌回 context。

V1 支持 4 个 operation：`move_module`、`rename_module`、`rename_symbol`、`move_symbol`。

## 接入

前置：Python 3.11+ 与 [uv](https://docs.astral.sh/uv/)。

**Agent 在用户电脑上安装**（非交互，一条命令即可）：

```bash
cd <path-to>/python_refactor_mcp
python -m python_refactor_mcp setup --client all --yes
python -m python_refactor_mcp doctor
```

`setup --yes` 会改这些**用户级**文件（不改任意 git 仓库里的项目 `CLAUDE.md`）：

- MCP：`~/.cursor/mcp.json`、`~/.claude.json`（`mcpServers`）、`~/.config/opencode/opencode.json`
- Skill 目录：`~/.cursor/skills/python-refactor/`、`~/.claude/skills/python-refactor/`、`~/.config/opencode/skills/python-refactor/`
- 始终加载的指令（带 `<!-- python-refactor-mcp:start -->` 标记，可重复 setup）：`~/.claude/CLAUDE.md`、`~/.config/opencode/AGENTS.md`

有 `claude` / `opencode` CLI 时优先 `mcp add`；没有 CLI 或 add 失败则直接写 JSON。

只装某一端：

```bash
python -m python_refactor_mcp setup --client cursor --yes
python -m python_refactor_mcp setup --client claude --yes
python -m python_refactor_mcp setup --client opencode --yes
```

验证：

```bash
python -m python_refactor_mcp doctor
```

卸载：

```bash
python -m python_refactor_mcp uninstall
python -m python_refactor_mcp uninstall --purge   # 同时删除 skill 目录和指令标记块
```

无 API key。客户端配置里不要写密钥。

手工兜底：

**macOS / Linux** — Cursor `~/.cursor/mcp.json` 与 Claude Code `~/.claude.json`（user scope，只合并 `mcpServers`）：

```json
{
  "mcpServers": {
    "python-refactor": {
      "command": "/absolute/path/to/python_refactor_mcp/.venv/bin/python",
      "args": ["-m", "python_refactor_mcp"],
      "cwd": "/absolute/path/to/python_refactor_mcp"
    }
  }
}
```

**Windows 10** — 使用 venv 的 `Scripts\python.exe`（正斜杠或反斜杠均可）：

```json
{
  "mcpServers": {
    "python-refactor": {
      "command": "C:/absolute/path/to/python_refactor_mcp/.venv/Scripts/python.exe",
      "args": ["-m", "python_refactor_mcp"],
      "cwd": "C:/absolute/path/to/python_refactor_mcp"
    }
  }
}
```

OpenCode `~/.config/opencode/opencode.json`（`mcp.<name>` 直挂，不要写 `mcp.servers`）：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "python-refactor": {
      "type": "local",
      "enabled": true,
      "command": [
        "/absolute/path/to/python_refactor_mcp/.venv/bin/python",
        "-m",
        "python_refactor_mcp"
      ]
    }
  }
}
```

Windows 上把上面的 `command` 换成 `.venv\\Scripts\\python.exe` 的绝对路径即可。

**Windows 安装注意：** 仓库里的 `python_refactor_mcp → src` 是给 macOS/Linux 可编辑开发用的符号链接。Windows 若 Git 未启用 symlink，请用官方路径安装：`uv sync` / `uv sync --extra dev` 后走 hatch editable，再 `python -m python_refactor_mcp setup`；不要依赖把 symlink checkout 成文本文件。`project_root` 在两端都必须是目标项目的绝对路径。

## 工具

四个工具：`python_refactor`（Rope mutation）、`inspect_symbol`（语义查询）、`apply_codemod`（注册制 LibCST）、`verify_refactor`（只跑验证）。`project_root` 必须是**目标 Python 项目**的绝对路径（MCP 进程 cwd 不是那个项目）。

### python_refactor

| operation | 必填字段 |
| --- | --- |
| `move_module` | `source`, `target`（dotted path） |
| `rename_module` | `source`, `new_name`（`new_name` 只能是最后一段标识符） |
| `rename_symbol` | `module`, `symbol`, `new_name`（`symbol` 为 `Name` 或 `Class.method`） |
| `move_symbol` | `module`, `symbol`, `target`（目标模块 dotted path） |

常用可选字段：`dry_run`（默认 false）、`verify`（默认等价 `["residual"]`，还可加 `ruff` / `pyright` / `pytest`）、`verification_mode`（`fast` / `standard` / `full`）、`source_root`、`pytest_args`、`semantic_mode`（`best_effort` 默认 / `required`）。

显式传入 `verify` 时以 `verify` 为准；只传 `verification_mode` 时按模式展开步骤：`fast` = LSP diagnostics + ruff；`standard` = residual + ruff + pyright + targeted pytest；`full` = 同上但 pytest 跑全量。

`rename_symbol` / `move_symbol` 会先走 Pyright semantic preflight（definition + references）；Pyright 不可用时默认 `best_effort` 继续 Rope，`required` 则中止。模块操作不做重 preflight，apply 后做 typed LSP refresh + diagnostics。`verify=["pyright"]` 会经与 LSP 相同的 runtime fallback（含 MCP 自带 CLI）。

结果是 compact JSON：`files_changed`、路径列表、`leftover_samples`、`leftover_replace_from` / `leftover_replace_to`、`next_action`、`empty_packages`，以及可选的 `summary` / `metrics`（含 `duration_ms` / `result_chars`）/ `warnings` / `details` / `semantic_status`。没有 unified diff，也没有文件全文。`leftover_samples` 就是 residual 搜索结果；按 `next_action` 定点改，不要再全仓搜索。

### inspect_symbol

在改代码前用这个代替 grep/read 循环。`line` / `character` 是 **1-based**。

| 字段 | 说明 |
| --- | --- |
| `file` | 相对 `project_root` 或绝对路径 |
| `line`, `character` | 1-based 位置 |
| `include_definition` / `include_references` / `include_type` | 默认 true |
| `max_references` | 默认 50，超出则截断并设 `references_truncated` |

返回 compact JSON：`symbol`、`definition`（`path:line:col`）、`reference_count`、截断后的 `references`、`type`。没有源码，没有 diff。

### apply_codemod

对注册的内置 LibCST codemod 做 preview/apply。默认 `dry_run=true`（先预览）。不接受任意 transformer 源码。

| 字段 | 说明 |
| --- | --- |
| `codemod` | `replace_qualified_name` / `replace_call_keyword` / `replace_decorator` |
| `params` | 各 codemod 参数（如 `old`/`new`，或 `function`/`old`/`new`） |
| `paths` | 相对 `project_root` 的扫描路径，默认 `["."]` |
| `dry_run` | 默认 true；false 时 hash 校验后原子写盘并 LSP refresh |

返回 compact：`files_scanned` / `files_matched` / `files_changed` / `transform_count` / `metrics`；无 diff/源码。parse 失败或并发修改会整批中止（零半写）。

### verify_refactor

只跑验证、不改文件。`verification_mode` 默认 `standard`；也可显式传 `verify` 步骤列表（与 `python_refactor` 相同锁定规则）。

调试（不经 MCP）：

```bash
python -m python_refactor_mcp.cli \
  --operation move_module \
  --project-root /abs/path/to/project \
  --source app.services.report \
  --target app.reporting.application.report_service \
  --dry-run
```

## 目标项目 AGENTS.md 片段

把下面片段粘到**被重构的 Python 仓库**（不是本 MCP 仓库）：

```markdown
## Python Refactoring

For structural Python refactoring, always prefer the
`python_refactor` tool over manual multi-file editing.
Use `inspect_symbol` for definition/references/type instead of grep/read loops.
Use `apply_codemod` for registered LibCST rewrites (preview-first).
Use `verify_refactor` to re-check without re-running Rope.

Use `python_refactor` for:

- module move
- module rename
- class/function rename
- class/function move

Do NOT manually rewrite imports across multiple files when
`python_refactor` can perform the operation.

After python_refactor succeeds:

1. leftover_samples is already the residual search. Edit only those file:line hits.
   Use leftover_replace_from -> leftover_replace_to. Follow next_action.
   Do NOT glob or grep the repo.
2. If leftover_samples is empty and verification.residual is ok/failed, skip leftover
   work. Do not search to confirm.
3. A dry_run result never scans residual. Re-run without dry_run instead of searching.
4. Only rg leftover_replace_from when it is a dotted module path. For symbol renames it
   is a bare identifier; edit the listed hits and let Ruff/Pyright find the rest.
5. empty_packages are local keep-or-delete decisions, not a search task.
6. Then run Ruff / Pyright / relevant pytest. Verification must not wait on leftover search.

Direct edits are allowed only for:
- business logic changes
- unsupported dynamic references
- leftover_samples the tool listed
```

## V1 明确不做

- 自动改 `importlib.import_module` / `getattr` 等动态字符串
- 自动改 JSON / YAML / Markdown / shell / 部署配置
- extract method / change signature / inline
- 工具内 LLM、自动 `git reset`
- 任意上传的 LibCST transformer（只允许注册的 builtin codemod）
- 默认跑全量 pytest（`verification_mode=full` 或 `verify=["pytest"]` + 全量参数才跑）

Rope 可能会为了解析路径而补空的 `__init__.py`，从而把 namespace package 变成 regular package。失败时工具不会 `git reset`；回滚交给 Git / 用户。

V3 metrics 在 V1 字段之外附加 `duration_ms` / `result_chars` 等；compact 结果仍不返回源码或 diff。

## 开发

```bash
cd python_refactor_mcp
uv pip install -e ".[dev]"
uv run pytest
```
