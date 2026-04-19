# ocr-vlm MCP

基于 **OpenAI 兼容** Chat Completions 多模态接口的 stdio MCP：工具 `describe_image` 读本地图片，返回结构化 Markdown（便于纯文本编码模型继续任务）。

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `VISION_API_KEY` | 是 | 云厂商 API Key |
| `VISION_MODEL` | 是 | 支持图像的模型 id |
| `VISION_BASE_URL` | 否 | 留空则走 OpenAI 官方默认；DashScope 等需填写兼容端点 |
| `VISION_MAX_TOKENS` | 否 | 覆盖默认输出长度上限 |

参见 [.env.example](.env.example)。

## 本地调试

```bash
cd /Users/yuping/Documents/workspace/mcp/ocr_mcp
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
      "args": ["/Users/yuping/Documents/workspace/mcp/ocr_mcp/index.js"],
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

- **describe_image**
  - `image_path`：绝对路径或相对**当前进程工作目录**的路径。
  - `detail`：`brief` | `full`（可选，默认 `full`）。
