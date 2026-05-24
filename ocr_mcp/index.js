"use strict";

/**
 * Vision VLM MCP (stdio): OpenAI-compatible chat vision → Markdown text.
 * Tools: load_image, load_video, list_markdown_images, list_markdown_media,
 *        load_markdown_images, load_markdown_media, describe_image,
 *        compare_images, describe_video, extract_image_text,
 *        extract_markdown_image_text
 * Env: VISION_API_KEY, VISION_MODEL, optional VISION_BASE_URL, VISION_MAX_TOKENS, VISION_NATIVE_VIDEO
 * Do not write to stdout except MCP protocol (logs → stderr only).
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFile } = require("child_process");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const OpenAI = require("openai");
const { extractImageText } = require("./ocr-image.js");
const { extractMarkdownImageText } = require("./markdown-image-ocr.js");
const { listMarkdownImages, loadMarkdownImages } = require("./markdown-image-utils.js");
const { listMarkdownMedia, loadMarkdownMedia } = require("./markdown-media-utils.js");
const { loadImageContent, validateImagePath } = require("./image-utils.js");
const { loadVideoContent, validateVideoPath } = require("./video-utils.js");

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

const COMPARE_SYSTEM_PROMPT = `你是专业的UI对比分析助手。根据用户提供的两张图片（图A为当前截图/问题截图，图B为参考截图/正例截图），用中文输出Markdown，严格使用以下小节标题：

## 概览
## 用户标注（红框、箭头等）
## 差异对比
## 前端样式差异推导
## 修复建议
## 不确定项

要求：
1. **用户标注（图A）**：关注图A中的红框、箭头、高亮标记，精确描述标注位置和指向的对象。
2. **差异对比**：逐区域对比图A和图B的差异，按"图A有，图B无"和"图B有，图A无"组织。指出布局、颜色、间距、字体、组件形态的具体差异。
3. **前端样式差异推导**：基于差异推导CSS属性变化，包括但不限于：
   - 颜色：色值变化（如 #333 → #666）
   - 间距：margin/padding 差异
   - 字体：字号、字重、行高变化
   - 布局：flex/grid、对齐方式、元素位置偏移
   - 组件：按钮样式、卡片圆角、阴影等
4. **修复建议**：给出可操作的修复方案，优先提供CSS代码片段。
5. 看不清或可能误判的内容写入「不确定项」，不要编造细节。`;

const VIDEO_SYSTEM_PROMPT = `你是专业的视频/动画分析助手。根据用户提供的视频关键帧序列，用中文输出Markdown，严格使用以下小节标题：

## 视频概览
## 操作步骤/阶段演替
## 动画与过渡效果
## UI元素变化
## CSS/前端实现推导
## 不确定项

要求：
1. **视频概览**：根据帧序列推断视频总时长、主要内容和目的。
2. **操作步骤/阶段演替**：按帧序列列出每个操作阶段（如"点击按钮 → 弹窗出现 → 填写表单 → 提交"）。标注每阶段的起始帧。
3. **动画与过渡效果**：识别帧间的动画类型（fade, slide, scale, rotate 等）、方向、时长估计、缓动曲线推测。
4. **UI元素变化**：记录帧间新增、消失、移动、状态变化的UI元素。
5. **CSS/前端实现推导**：输出核心元素的CSS动画关键帧代码（@keyframes）或 transition 属性，用于前端功能复现。
6. 看不清或无法确定的内容写入「不确定项」，不要编造细节。`;

const NATIVE_VIDEO_SYSTEM_PROMPT = `你是专业的视频/动画分析助手。根据用户提供的视频，用中文输出Markdown，严格使用以下小节标题：

## 视频概览
## 操作步骤/阶段演替
## 动画与过渡效果
## UI元素变化
## CSS/前端实现推导
## 不确定项

要求：
1. **视频概览**：简述视频时长、节奏、主要内容和目的。
2. **操作步骤/阶段演替**：按时间线列出每个操作阶段（如"点击按钮 → 弹窗出现 → 填写表单 → 提交"）。标注每阶段的大致时间点（如 0:00-0:03）。
3. **动画与过渡效果**：识别动画类型（fade, slide, scale, rotate 等）、方向、大致时长、缓动曲线推测。
4. **UI元素变化**：记录视频中新出现、消失、移动、状态变化的UI元素。
5. **CSS/前端实现推导**：输出核心元素的CSS动画关键帧代码（@keyframes）或 transition 属性，用于前端功能复现。
6. 看不清或无法确定的内容写入「不确定项」，不要编造细节。`;

const VIDEO_MIME_BY_EXT = {
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".avi": "video/x-msvideo",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".m4v": "video/x-m4v",
};

function execFileAsync(file, args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile(file, args, { maxBuffer: 10 * 1024 * 1024, ...options }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(`${file} 执行失败: ${error.message}. stderr: ${stderr}`));
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
}

function selectFrames(frames, maxCount) {
  if (frames.length <= maxCount) return frames;
  const step = frames.length / maxCount;
  const result = [];
  for (let i = 0; i < maxCount; i++) {
    result.push(frames[Math.round(i * step)]);
  }
  return result;
}

async function extractVideoFrames(videoPath, fps) {
  const { stdout: probeJson } = await execFileAsync("ffprobe", [
    "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", videoPath,
  ]);

  let meta;
  try {
    meta = JSON.parse(probeJson);
  } catch (_) {
    throw new Error(`ffprobe 解析失败，返回内容非 JSON`);
  }

  const videoStream = meta.streams.find(s => s.codec_type === "video");
  if (!videoStream) {
    throw new Error("视频文件中未找到视频流");
  }

  const width = videoStream.width || 1920;
  const height = videoStream.height || 1080;
  const outDir = path.join(os.tmpdir(), `ocr-vlm-frames-${Date.now()}`);
  fs.mkdirSync(outDir, { recursive: true });

  const effectiveFps = fps ?? 2;
  const totalBlocks = Math.ceil(width / 64) * Math.ceil(height / 64);
  const hi = Math.max(64, Math.round(totalBlocks * 0.2));

  const vfFilter = `fps=${effectiveFps},mpdecimate=hi=64*${hi}:lo=64*5:frac=1`;

  await execFileAsync("ffmpeg", [
    "-i", videoPath,
    "-vf", vfFilter,
    "-fps_mode", "vfr",
    path.join(outDir, "frame_%04d.png"),
  ]);

  const files = fs.readdirSync(outDir)
    .filter(f => f.endsWith(".png") || f.endsWith(".jpg"))
    .sort();

  if (files.length < 5) {
    fs.rmSync(outDir, { recursive: true, force: true });
    throw new Error(
      `仅抽到 ${files.length} 个关键帧，视频变化过少或不支持该编码格式。` +
      ` 可尝试调高 fps（如 fps=5）获取更细粒度分析。`
    );
  }

  const frames = [];
  for (const f of files) {
    const absPath = path.join(outDir, f);
    const buf = fs.readFileSync(absPath);
    const mime = f.endsWith(".png") ? "image/png" : "image/jpeg";
    frames.push({
      name: f,
      absPath,
      b64: buf.toString("base64"),
      mime,
    });
  }

  return {
    outDir,
    frames,
    meta: {
      duration: meta.format.duration,
      bitRate: meta.format.bit_rate,
      width,
      height,
      frameRate: videoStream.r_frame_rate,
      codec: videoStream.codec_name,
    },
  };
}

async function describeVideoWithVlm(frames, meta, detail) {
  const MAX_FRAMES = 30;
  const selected = selectFrames(frames, MAX_FRAMES);

  const cfg = ensureVisionConfig();
  const client = new OpenAI({
    apiKey: cfg.apiKey,
    baseURL: cfg.baseURL,
  });

  const defaultMax = detail === "brief" ? 4096 : 8192;
  const maxTokens = cfg.maxTokens ?? defaultMax;

  const userContent = [];
  userContent.push({
    type: "text",
    text:
      `视频元信息：时长 ${meta.duration}s, 分辨率 ${meta.width}x${meta.height}, 帧率 ${meta.frameRate}, 编码 ${meta.codec}。` +
      `共抽取 ${frames.length} 个关键帧，均匀采样 ${selected.length} 帧展示如下：`,
  });

  for (let i = 0; i < selected.length; i++) {
    userContent.push(
      { type: "text", text: `--- 关键帧 ${i + 1}/${selected.length} (${selected[i].name}) ---` },
      { type: "image_url", image_url: { url: `data:${selected[i].mime};base64,${selected[i].b64}` } },
    );
  }

  userContent.push({
    type: "text",
    text:
      detail === "brief"
        ? "请按系统要求分析这段视频的关键帧序列。" + BRIEF_EXTRA
        : "请按系统要求分析这段视频的关键帧序列，识别操作步骤、动画效果并推导前端实现方案。",
  });

  const completion = await client.chat.completions.create({
    model: cfg.model,
    messages: [
      { role: "system", content: VIDEO_SYSTEM_PROMPT },
      { role: "user", content: userContent },
    ],
    max_tokens: maxTokens,
  });

  const text = extractContent(completion);
  if (!text) {
    throw new Error("模型未返回文本内容");
  }
  return text;
}

function isVideoNativeEnabled() {
  const val = process.env.VISION_NATIVE_VIDEO?.trim().toLowerCase();
  if (!val) return true;
  return val !== "0" && val !== "false" && val !== "no";
}

function extractContent(completion) {
  const message = completion.choices?.[0]?.message;
  if (!message) return null;
  const text = message.content ?? message.reasoning;
  return text && typeof text === "string" ? text.trim() : null;
}

async function describeVideoNative(absPath, detail) {
  const ext = path.extname(absPath).toLowerCase();
  const mime = VIDEO_MIME_BY_EXT[ext] || "video/mp4";

  const stat = fs.statSync(absPath);
  const fileSizeMB = stat.size / (1024 * 1024);
  console.error(`[ocr-vlm] Native video mode: ${absPath} (${fileSizeMB.toFixed(1)} MB)`);

  const buf = fs.readFileSync(absPath);
  const b64 = buf.toString("base64");
  const dataUrl = `data:${mime};base64,${b64}`;

  const cfg = ensureVisionConfig();
  const client = new OpenAI({
    apiKey: cfg.apiKey,
    baseURL: cfg.baseURL,
  });

  const defaultMax = detail === "brief" ? 4096 : 8192;
  const maxTokens = cfg.maxTokens ?? defaultMax;

  const userContent = [
    {
      type: "text",
      text: detail === "brief"
        ? "请按系统要求分析这段视频。" + BRIEF_EXTRA
        : "请按系统要求完整分析这段视频，识别操作步骤、动画效果并推导前端实现方案。",
    },
    { type: "video_url", video_url: { url: dataUrl } },
  ];

  const completion = await client.chat.completions.create({
    model: cfg.model,
    messages: [
      { role: "system", content: NATIVE_VIDEO_SYSTEM_PROMPT },
      { role: "user", content: userContent },
    ],
    max_tokens: maxTokens,
  });

  const text = extractContent(completion);
  if (!text) {
    throw new Error("模型未返回文本内容");
  }
  return text;
}

function resolveImagePath(imagePath) {
  const { absPath, mime, size } = validateImagePath(imagePath);
  return { absPath, mime, size };
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

  const text = extractContent(completion);
  if (!text) {
    throw new Error("模型未返回文本内容（vision 可能未开通或模型不支持图像）");
  }
  return text;
}

async function compareImagesWithVlm(absPathA, mimeA, absPathB, mimeB, detail) {
  const cfg = ensureVisionConfig();
  const client = new OpenAI({
    apiKey: cfg.apiKey,
    baseURL: cfg.baseURL,
  });

  const bufA = fs.readFileSync(absPathA);
  const b64A = bufA.toString("base64");
  const dataUrlA = `data:${mimeA};base64,${b64A}`;

  const bufB = fs.readFileSync(absPathB);
  const b64B = bufB.toString("base64");
  const dataUrlB = `data:${mimeB};base64,${b64B}`;

  const userText =
    detail === "brief"
      ? "请对比分析图A（问题截图）和图B（参考截图）的差异。" + BRIEF_EXTRA
      : "请按系统要求对比分析图A（问题截图）和图B（参考截图）的差异，并推导前端样式修复方案。";

  const defaultMax = detail === "brief" ? 4096 : 8192;
  const maxTokens = cfg.maxTokens ?? defaultMax;

  const userContent = [
    { type: "text", text: "【图A - 问题截图 / 当前截图】" },
    { type: "image_url", image_url: { url: dataUrlA } },
    { type: "text", text: "【图B - 参考截图 / 正例截图】" },
    { type: "image_url", image_url: { url: dataUrlB } },
    { type: "text", text: userText },
  ];

  const completion = await client.chat.completions.create({
    model: cfg.model,
    messages: [
      { role: "system", content: COMPARE_SYSTEM_PROMPT },
      { role: "user", content: userContent },
    ],
    max_tokens: maxTokens,
  });

  const text = extractContent(completion);
  if (!text) {
    throw new Error("模型未返回文本内容");
  }
  return text;
}

const mcpServer = new McpServer({
  name: "ocr-vlm",
  version: "1.2.0",
});

mcpServer.registerTool(
  "extract_image_text",
  {
    description:
      "对本地图片执行 OCR，完整转录图片中可见文字，不做总结、翻译或改写；这是服务器侧 OCR fallback，不是直接媒体加载。支持 plain 和 markdown 输出模式。",
    inputSchema: {
      image_path: z
        .string()
        .describe("图片路径：绝对路径，或相对当前工作目录的相对路径；会把图片发送给 OCR 模型做完整转录"),
      output_format: z
        .enum(["plain", "markdown"])
        .optional()
        .describe("plain=纯文本输出，更适合直接阅读；markdown=适合直接插入 Markdown 的输出"),
    },
  },
  async ({ image_path, output_format }) => {
    try {
      const format = output_format ?? "plain";
      const text = await extractImageText(image_path, { outputFormat: format });
      const header = `<!-- source: ${validateImagePath(image_path).absPath} | output_format: ${format} -->\n\n`;
      return {
        content: [{ type: "text", text: header + text }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `OCR 失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "extract_markdown_image_text",
  {
    description:
      "对 Markdown 文件中的本地图片引用逐个执行 OCR，并保留原始行号；这是服务器侧 OCR fallback，不是直接媒体加载。失败项会单独报告且不会中断其他图片。",
    inputSchema: {
      markdown_path: z
        .string()
        .describe("Markdown 文件路径：绝对路径，或相对当前工作目录的相对路径；仅解析本地图片引用并发送给 OCR 模型"),
      line_numbers: z
        .array(z.number().int().positive())
        .optional()
        .describe("可选，只处理这些行号上的图片引用；省略则处理全部可解析图片"),
      output_format: z
        .enum(["plain", "markdown"])
        .optional()
        .describe("plain=纯文本输出，更适合直接阅读；markdown=适合直接插入 Markdown 的输出"),
    },
  },
  async ({ markdown_path, line_numbers, output_format }) => {
    try {
      const results = await extractMarkdownImageText(markdown_path, {
        lineNumbers: line_numbers,
        outputFormat: output_format,
      });
      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `Markdown OCR 失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "load_markdown_images",
  {
    description:
      "读取 Markdown 文件并加载其中的本地图片引用，直接返回 MCP image content 给支持多模态输入的客户端；按行号筛选时只处理匹配项，失败项会单独报告。",
    inputSchema: {
      markdown_path: z
        .string()
        .describe("Markdown 文件路径：绝对路径，或相对当前工作目录的相对路径；仅解析本地图片引用，不调用 OCR/VLM 模型"),
      line_numbers: z
        .array(z.number().int().positive())
        .optional()
        .describe("可选，只处理这些行号上的图片引用；省略则加载全部可解析图片"),
    },
  },
  async ({ markdown_path, line_numbers }) => {
    try {
      const results = loadMarkdownImages(markdown_path, {
        lineNumbers: line_numbers,
      });
      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `Markdown 图片加载失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "list_markdown_images",
  {
    description:
      "读取 Markdown 文件并列出其中所有本地图片引用，保留行号、原始引用、alt 文本、解析后的绝对路径和存在状态；只做本地解析，不调用任何模型。",
    inputSchema: {
      markdown_path: z
        .string()
        .describe("Markdown 文件路径：绝对路径，或相对当前工作目录的相对路径；只做本地解析，不会调用 OCR/VLM 模型"),
    },
  },
  async ({ markdown_path }) => {
    try {
      const results = listMarkdownImages(markdown_path);
      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `Markdown 图片列表失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "load_image",
  {
    description:
      "读取本地图片路径并返回 MCP image content，供支持多模态输入的客户端直接消费，不做 OCR 或视觉总结。",
    inputSchema: {
      image_path: z
        .string()
        .describe("图片路径：绝对路径，或相对当前工作目录的相对路径；会直接读取并返回图像数据给支持多模态输入的客户端"),
    },
  },
  async ({ image_path }) => {
    try {
      const { absPath, size, content } = loadImageContent(image_path);
      return {
        content: [content],
        metadata: {
          source: absPath,
          size,
        },
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `图片加载失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "load_video",
  {
    description:
      "读取本地视频路径并返回 MCP resource content，供支持多模态输入的客户端直接消费，不做 OCR、抽帧或视频分析模型调用。",
    inputSchema: {
      video_path: z
        .string()
        .describe("视频路径：绝对路径，或相对当前工作目录的相对路径；会直接读取并返回视频数据给支持多模态输入的客户端"),
    },
  },
  async ({ video_path }) => {
    try {
      const { absPath, size, content } = loadVideoContent(video_path);
      return {
        content: [content],
        metadata: {
          source: absPath,
          size,
        },
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `视频加载失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "list_markdown_media",
  {
    description:
      "读取 Markdown 文件并列出其中所有本地图片/视频引用，保留行号、原始引用、标签文本、解析后的绝对路径、MIME 类型、媒体类型和存在状态；仅解析本地引用，不调用任何模型。",
    inputSchema: {
      markdown_path: z
        .string()
        .describe("Markdown 文件路径：绝对路径，或相对当前工作目录的相对路径；只做本地解析，不会调用 OCR/VLM 模型"),
      media_types: z
        .array(z.enum(["image", "video"]))
        .optional()
        .describe("可选，仅返回这些媒体类型；省略则返回图片和视频引用"),
    },
  },
  async ({ markdown_path, media_types }) => {
    try {
      const results = listMarkdownMedia(markdown_path, { mediaTypes: media_types });
      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `Markdown 媒体列表失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "load_markdown_media",
  {
    description:
      "读取 Markdown 文件并加载其中选中的或全部本地图片/视频引用；图片返回 MCP image content，视频返回 MCP resource content，失败项单独报告且不会中断其他媒体。",
    inputSchema: {
      markdown_path: z
        .string()
        .describe("Markdown 文件路径：绝对路径，或相对当前工作目录的相对路径；仅解析本地媒体引用"),
      line_numbers: z
        .array(z.number().int().positive())
        .optional()
        .describe("可选，只处理这些行号上的媒体引用；省略则处理全部可解析引用"),
      media_types: z
        .array(z.enum(["image", "video"]))
        .optional()
        .describe("可选，仅加载这些媒体类型；省略则同时加载图片和视频"),
    },
  },
  async ({ markdown_path, line_numbers, media_types }) => {
    try {
      const results = loadMarkdownMedia(markdown_path, {
        lineNumbers: line_numbers,
        mediaTypes: media_types,
      });
      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `Markdown 媒体加载失败：${msg}` }],
        isError: true,
      };
    }
  }
);

mcpServer.registerTool(
  "describe_image",
  {
    description:
      "读取本地图片路径并调用云端多模态模型生成结构化 Markdown；这是服务器侧 VLM fallback，不是直接媒体加载。需配置 VISION_API_KEY、VISION_MODEL。",
    inputSchema: {
      image_path: z
        .string()
        .describe("图片路径：绝对路径，或相对当前工作目录的相对路径；会把图片发送给云端多模态模型做语义分析"),
      detail: z
        .enum(["brief", "full"])
        .optional()
        .describe("brief=更短输出，减少结果长度；full=默认更完整，适合需要更多图像分析细节的场景"),
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

mcpServer.registerTool(
  "compare_images",
  {
    description:
      "对比两张图片（问题截图 vs 参考截图），调用云端多模态模型返回差异分析和前端样式修复建议；这是服务器侧 VLM fallback，不是直接媒体加载。",
    inputSchema: {
      image_path_a: z
        .string()
        .describe("问题截图路径（图A），可含用户标注（红框/箭头）；会被发送给云端多模态模型"),
      image_path_b: z
        .string()
        .describe("参考/正例截图路径（图B）；会被发送给云端多模态模型"),
      detail: z
        .enum(["brief", "full"])
        .optional()
        .describe("brief=更短输出，减少分析结果长度；full=默认更完整，适合样式对比细节分析"),
    },
  },
  async ({ image_path_a, image_path_b, detail }) => {
    try {
      const d = detail ?? "full";
      const { absPath: absA, mime: mimeA } = resolveImagePath(image_path_a);
      const { absPath: absB, mime: mimeB } = resolveImagePath(image_path_b);
      const markdown = await compareImagesWithVlm(absA, mimeA, absB, mimeB, d);
      const header = `<!-- source_a: ${absA} | source_b: ${absB} | detail: ${d} -->\n\n`;
      return {
        content: [{ type: "text", text: header + markdown }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `对比失败：${msg}` }],
        isError: true,
      };
    }
  }
);

function resolveVideoPath(videoPath) {
  return validateVideoPath(videoPath).absPath;
}

mcpServer.registerTool(
  "describe_video",
  {
    description:
      "读取本地视频文件并调用云端多模态模型分析视频内容；这是服务器侧 VLM fallback，不是直接媒体加载。返回操作步骤、动画效果描述和前端实现推导。" +
      " 默认原生视频模式（视频直接发送给模型，无需 ffmpeg）；" +
      " 设置 VISION_NATIVE_VIDEO=false 可切换为 ffmpeg 抽帧分析（需安装 ffmpeg）。",
    inputSchema: {
      video_path: z
        .string()
        .describe("视频文件路径（支持 .mp4 .mov .avi .webm .mkv .m4v）；会被发送给云端多模态模型或抽帧分析流程"),
      fps: z
        .number()
        .min(0.1)
        .max(60)
        .optional()
        .describe("抽帧率（帧/秒）。默认 2，即每秒抽 2 帧后智能去重；调大可获得更细粒度的视频分析，调小可减少帧数量"),
      detail: z
        .enum(["brief", "full"])
        .optional()
        .describe("brief=更短输出，减少分析结果长度；full=默认更完整，适合更详细的视频分析"),
    },
  },
  async ({ video_path, fps, detail }) => {
    let outDir = null;
    try {
      const d = detail ?? "full";
      const absPath = resolveVideoPath(video_path);

      if (isVideoNativeEnabled()) {
        const markdown = await describeVideoNative(absPath, d);
        const stat = fs.statSync(absPath);
        const header =
          `<!-- source: ${absPath} | size: ${(stat.size / (1024 * 1024)).toFixed(1)}MB | ` +
          `mode: native | detail: ${d} -->\n\n`;
        return {
          content: [{ type: "text", text: header + markdown }],
        };
      }

      const result = await extractVideoFrames(absPath, fps ?? null);
      outDir = result.outDir;

      const markdown = await describeVideoWithVlm(result.frames, result.meta, d);
      const header =
        `<!-- source: ${absPath} | duration: ${result.meta.duration}s | ` +
        `resolution: ${result.meta.width}x${result.meta.height} | ` +
        `frames: ${result.frames.length} | detail: ${d} -->\n\n`;

      return {
        content: [{ type: "text", text: header + markdown }],
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `视频分析失败：${msg}` }],
        isError: true,
      };
    } finally {
      if (outDir) {
        try { fs.rmSync(outDir, { recursive: true, force: true }); } catch (_) { /* 清理失败不抛出 */ }
      }
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
