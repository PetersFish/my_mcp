# ocr-vlm MCP

基于 **OpenAI 兼容** Chat Completions 多模态接口的 stdio MCP：

- 优先用 `load_image` / `load_video` / `load_markdown_images` / `load_markdown_media` 直接返回媒体内容给支持多模态输入的客户端
- `describe_image` / `compare_images` / `describe_video` / `extract_image_text` / `extract_markdown_image_text` 是服务器侧 VLM/OCR fallback
- `load_image`：把本地图片作为 MCP image content 直接返回给客户端
- `load_video`：把本地视频作为 MCP resource content 直接返回给客户端
- `describe_image`：读取本地图片并返回结构化 Markdown
- `list_markdown_images` / `load_markdown_images`：解析 Markdown 中的本地图片引用
- `list_markdown_media` / `load_markdown_media`：解析 Markdown 中的本地图片和视频引用
- `extract_image_text` / `extract_markdown_image_text`：做完整 OCR 转录

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `VISION_API_KEY` | 是 | 云厂商 API Key |
| `VISION_MODEL` | 是 | 支持图像的模型 id |
| `VISION_BASE_URL` | 否 | 留空则走 OpenAI 官方默认；DashScope 等需填写兼容端点 |
| `VISION_MAX_TOKENS` | 否 | 覆盖默认输出长度上限 |
| `VISION_OCR_MAX_TOKENS` | 否 | 覆盖 OCR 专用输出长度上限 |

参见 [.env.example](.env.example)。

## 本地调试

```bash
 cd /Users/yuping/Documents/workspace/my_mcp/ocr_mcp
export VISION_API_KEY=...
export VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export VISION_MODEL=qwen-vl-plus
# 需另用 MCP Inspector 或直接在 Claude Code 里连 stdio
node index.js
```

## Claude Code 注册示例

在 Claude Code 的 MCP 配置中增加（路径与 Key 按你本机修改）：

```json
{
  "mcpServers": {
    "ocr-vlm": {
      "command": "node",
      "args": ["/Users/yuping/Documents/workspace/my_mcp/ocr_mcp/index.js"],
      "env": {
        "VISION_API_KEY": "${env:VISION_API_KEY}",
        "VISION_BASE_URL": "${env:VISION_BASE_URL}",
        "VISION_MODEL": "${env:VISION_MODEL}"
      }
    }
  }
}
```

若客户端不支持 `${env:...}` 插值，请直接写具体值或确保启动 Claude Code 前已在 shell 中 `export` 上述变量，并在配置里省略 `env`（取决于 Claude Code 是否继承环境）。

## 工具说明

- **load_image**
  - 直接返回 MCP image content，适合支持多模态输入的客户端。
- **list_markdown_images**
  - 解析 Markdown 文件中的本地图片引用，返回行号、路径和存在状态。
- **load_markdown_images**
  - 在 `list_markdown_images` 基础上加载实际图片，并逐项报告失败。
- **extract_image_text**
  - 对单张图片做 OCR，输出 `plain` 或 `markdown` 文本。
- **extract_markdown_image_text**
  - 对 Markdown 文件中的图片逐个 OCR，失败项会单独返回。
- **describe_image**
  - `image_path`：绝对路径或相对**当前进程工作目录**的路径。
  - `detail`：`brief` | `full`（可选，默认 `full`）。

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
