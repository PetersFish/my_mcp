"use strict";

/**
 * Vision VLM MCP (stdio): OpenAI-compatible chat vision → Markdown text.
 * Env: VISION_API_KEY, VISION_MODEL, optional VISION_BASE_URL, VISION_MAX_TOKENS
 * Do not write to stdout except MCP protocol (logs → stderr only).
 */

const fs = require("fs");
const path = require("path");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const OpenAI = require("openai");

const SYSTEM_PROMPT = `你是专业的读图助手。根据用户提供的图片，用中文输出 Markdown，并严格使用以下小节标题（即使某节无内容也要保留标题，无内容时写「未发现」或「无」）：

## 概览
## 用户标注（红框、箭头等）
## 实体与文字
## 关系与结构（节点、边、方向、层级）
## 不确定项

要求：
1. 必须关注并描述**红色高亮、红框、红色箭头**等用户标注及其指向的对象。
2. 对架构图、算法图、流程图：说明**节点名称**、**连线/箭头方向**、**分组或层级**、若有数据流则写清流向。
3. 对 UI 截图：说明主要控件、区域与可读文字。
4. 看不清或可能误判的内容写入「不确定项」，不要编造细节。`;

const BRIEF_EXTRA = "\n\n【本次为简要模式】各小节尽量精炼，总字数控制在约 800 字以内。";

const MIME_BY_EXT = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".bmp": "image/bmp",
};

function getMimeType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return MIME_BY_EXT[ext] || null;
}

function resolveImagePath(imagePath) {
  const trimmed = imagePath.trim();
  if (!trimmed) {
    throw new Error("image_path 不能为空");
  }
  const abs = path.isAbsolute(trimmed)
    ? path.normalize(trimmed)
    : path.resolve(process.cwd(), trimmed);
  if (!fs.existsSync(abs)) {
    throw new Error(`图片不存在: ${abs}`);
  }
  const st = fs.statSync(abs);
  if (!st.isFile()) {
    throw new Error(`路径不是文件: ${abs}`);
  }
  const mime = getMimeType(abs);
  if (!mime) {
    throw new Error(
      `不支持的扩展名（请使用 ${Object.keys(MIME_BY_EXT).join(", ")}）`
    );
  }
  return { absPath: abs, mime };
}

function ensureVisionConfig() {
  const apiKey = process.env.VISION_API_KEY?.trim();
  const model = process.env.VISION_MODEL?.trim();
  if (!apiKey) {
    throw new Error(
      "缺少环境变量 VISION_API_KEY。请在 shell 或 MCP 配置的 env 中设置。"
    );
  }
  if (!model) {
    throw new Error(
      "缺少环境变量 VISION_MODEL（须为支持图像的模型 id）。"
    );
  }
  const baseURL = process.env.VISION_BASE_URL?.trim() || undefined;
  const maxTokens = parseInt(process.env.VISION_MAX_TOKENS || "", 10);
  return {
    apiKey,
    model,
    baseURL,
    maxTokens: Number.isFinite(maxTokens) && maxTokens > 0 ? maxTokens : null,
  };
}

async function describeImageWithVlm(absPath, mime, detail) {
  const cfg = ensureVisionConfig();
  const client = new OpenAI({
    apiKey: cfg.apiKey,
    baseURL: cfg.baseURL,
  });

  const buf = fs.readFileSync(absPath);
  const b64 = buf.toString("base64");
  const dataUrl = `data:${mime};base64,${b64}`;

  const userText =
    detail === "brief"
      ? "请按系统要求分析这张图片。" + BRIEF_EXTRA
      : "请按系统要求完整分析这张图片。";

  const defaultMax = detail === "brief" ? 2048 : 4096;
  const maxTokens = cfg.maxTokens ?? defaultMax;

  const userContent = [
    { type: "text", text: userText },
    {
      type: "image_url",
      // 仅传 url，避免部分 OpenAI 兼容网关不支持 detail 字段
      image_url: { url: dataUrl },
    },
  ];

  const completion = await client.chat.completions.create({
    model: cfg.model,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userContent },
    ],
    max_tokens: maxTokens,
  });

  const text = completion.choices?.[0]?.message?.content;
  if (!text || typeof text !== "string") {
    throw new Error("模型未返回文本内容（vision 可能未开通或模型不支持图像）");
  }
  return text.trim();
}

const mcpServer = new McpServer({
  name: "ocr-vlm",
  version: "1.0.0",
});

mcpServer.registerTool(
  "describe_image",
  {
    description:
      "读取本地图片路径，调用云端多模态模型，返回结构化 Markdown（红框/箭头、节点关系等）。需配置 VISION_API_KEY、VISION_MODEL。",
    inputSchema: {
      image_path: z
        .string()
        .describe("图片路径：绝对路径，或相对当前工作目录的相对路径"),
      detail: z
        .enum(["brief", "full"])
        .optional()
        .describe("brief=更短输出；full=默认更完整"),
    },
  },
  async ({ image_path, detail }) => {
    try {
      const d = detail ?? "full";
      const { absPath, mime } = resolveImagePath(image_path);
      const markdown = await describeImageWithVlm(absPath, mime, d);
      const header = `<!-- source: ${absPath} | detail: ${d} -->\n\n`;
      return {
        content: [{ type: "text", text: header + markdown }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [
          {
            type: "text",
            text: `读图失败：${msg}`,
          },
        ],
        isError: true,
      };
    }
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await mcpServer.connect(transport);
}

main().catch((error) => {
  console.error("[ocr-vlm]", error);
  process.exit(1);
});
