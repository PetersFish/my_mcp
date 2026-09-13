# ocr-vlm MCP

基于 **OpenAI 兼容** Chat Completions 多模态接口的 stdio MCP。团队接入走一条命令：注册 Claude Code / OpenCode，写入本机密钥，并安装配套 skill `media-ocr-router`。

优先用 `load_image` / `load_video` / `load_markdown_images` / `load_markdown_media` 把媒体交给支持多模态的客户端；`describe_image` / `compare_images` / `describe_video` / `extract_image_text` / `extract_markdown_image_text` 是服务器侧 VLM/OCR fallback。

## 团队接入

前置：Node.js 18+，以及 Claude Code 和/或 OpenCode CLI。

```bash
git clone https://github.com/PetersFish/my_mcp.git
cd my_mcp/ocr_mcp
npm install
npm run setup
```

`setup` 会：

- 交互补齐 `VISION_API_KEY`、`VISION_MODEL`（`VISION_BASE_URL` 可空）
- 把密钥写到 `~/.config/ocr-vlm/config.env`（权限 600），**不**写进 Claude / OpenCode 的 JSON
- 用官方 CLI 注册 user/global MCP：`claude mcp add --scope user`、`opencode mcp add --global`
- 安装配套 skill 到 `~/.claude/skills/media-ocr-router/` 与 `~/.config/opencode/skills/media-ocr-router/`
- 跑 `doctor` 做连通性检查

非交互：

```bash
VISION_API_KEY=... VISION_MODEL=qwen-vl-plus VISION_BASE_URL=... npm run setup -- --yes
```

只装某一端：

```bash
npm run setup -- --client claude
npm run setup -- --client opencode
```

找不到 `claude` / `opencode` 时会跳过并提示，不会整次失败。已有 `config.env` 时再次执行会复用密钥；`--force-env` 才会覆盖。

### 验证

```bash
npm run doctor
npm run doctor -- --client claude    # 只检查 Claude Code
```

Claude Code 里用 `/mcp`，OpenCode 里用 `/mcps`，应看到 `ocr-vlm` 已连接。配套 skill 出现后，看图任务会优先走 `load_image`（Claude Code 工具名为 `mcp__ocr-vlm__load_image`）。

### 卸载

```bash
npx ocr-vlm-mcp uninstall
npx ocr-vlm-mcp uninstall --purge   # 同时删除 config.env 与已安装 skill
```

## 环境变量

密钥由 wrapper 从 `~/.config/ocr-vlm/config.env` 加载。客户端配置里不要写 Key。

| 变量 | 必填 | 说明 |
|------|------|------|
| `VISION_API_KEY` | 是 | 云厂商 API Key |
| `VISION_MODEL` | 是 | 支持图像的模型 id |
| `VISION_BASE_URL` | 否 | 留空则走 OpenAI 官方默认；DashScope 等需填写兼容端点 |
| `VISION_MAX_TOKENS` | 否 | 覆盖默认输出长度上限 |
| `VISION_OCR_MAX_TOKENS` | 否 | 覆盖 OCR 专用输出长度上限 |

字段说明也可参考 [.env.example](.env.example)。不要把真实 Key 提交到 Git。

## 手工兜底

脚本失败时，把下面的 `command`/`args` 换成你机器上 `ocr_mcp/bin/ocr-vlm-mcp.js` 的绝对路径。密钥仍放在 `~/.config/ocr-vlm/config.env`。

Claude Code（`~/.claude.json` 的 user scope 等价物）：

```json
{
  "mcpServers": {
    "ocr-vlm": {
      "command": "node",
      "args": ["/absolute/path/to/ocr_mcp/bin/ocr-vlm-mcp.js"]
    }
  }
}
```

OpenCode（`~/.config/opencode/opencode.json`）：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "ocr-vlm": {
        "type": "local",
        "command": ["node", "/absolute/path/to/ocr_mcp/bin/ocr-vlm-mcp.js"]
      }
    }
  }
}
```

若你的 OpenCode 仍是旧格式，把 `ocr-vlm` 直接写在 `mcp` 下，而不是 `mcp.servers`。

## 本地调试

```bash
cd ocr_mcp
export VISION_API_KEY=...
export VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export VISION_MODEL=qwen-vl-plus
node bin/ocr-vlm-mcp.js
```

## 工具说明

- **load_image**：直接返回 MCP image content，适合支持多模态输入的客户端。
- **load_video**：直接返回 MCP resource content。
- **list_markdown_images**：解析 Markdown 中的本地图片引用，返回行号、路径和存在状态。
- **load_markdown_images**：在列表基础上加载实际图片，并逐项报告失败。
- **list_markdown_media** / **load_markdown_media**：解析并加载 Markdown 中的本地图片和视频。
- **extract_image_text**：对单张图片做 OCR，输出 `plain` 或 `markdown` 文本。
- **extract_markdown_image_text**：对 Markdown 中的图片逐个 OCR，失败项会单独返回。
- **describe_image**：`image_path` 为绝对路径或相对当前进程工作目录；`detail` 为 `brief` | `full`（默认 `full`）。
- **compare_images** / **describe_video**：服务器侧 VLM 对比分析与视频分析。

## 使用建议

| 场景 | 推荐工具 |
|------|----------|
| 客户端能直接消费图片 | `load_image` |
| 客户端能直接消费视频 | `load_video` |
| Markdown 中嵌了图片，且要批量处理 | `load_markdown_images` |
| Markdown 中嵌了图片或视频，且要批量处理 | `load_markdown_media` |
| 需要看图说明、架构图/界面分析 | `describe_image` |
| 需要逐字转录图片文字 | `extract_image_text` |
| 需要服务器侧 OCR 处理 Markdown 图片 | `extract_markdown_image_text` |
