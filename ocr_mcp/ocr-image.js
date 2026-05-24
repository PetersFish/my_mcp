"use strict";

const OpenAI = require("openai");

const { validateImagePath } = require("./image-utils.js");
const { OCR_IMAGE_SYSTEM_PROMPT } = require("./ocr-prompts.js");
const { resolveOcrMaxTokens } = require("./ocr-config.js");

function ensureVisionConfig() {
  const apiKey = process.env.VISION_API_KEY?.trim();
  const model = process.env.VISION_MODEL?.trim();
  if (!apiKey) {
    throw new Error("缺少环境变量 VISION_API_KEY。请在 shell 或 MCP 配置的 env 中设置。");
  }
  if (!model) {
    throw new Error("缺少环境变量 VISION_MODEL（须为支持图像的模型 id）。");
  }
  const baseURL = process.env.VISION_BASE_URL?.trim() || undefined;
  return { apiKey, model, baseURL };
}

function buildOcrUserPrompt(outputFormat) {
  return outputFormat === "markdown"
    ? "请将这张图片中的所有可见文字完整转录为 markdown 可直接插入的文本。"
    : "请将这张图片中的所有可见文字完整转录为 plain 文本。";
}

async function extractImageText(imagePath, options = {}, deps = {}) {
  const outputFormat = options.outputFormat === "markdown" ? "markdown" : "plain";
  const { absPath, mime } = validateImagePath(imagePath);
  const buf = require("fs").readFileSync(absPath);
  const dataUrl = `data:${mime};base64,${buf.toString("base64")}`;

  const cfg = deps.config || ensureVisionConfig();
  const client = deps.client || new OpenAI({ apiKey: cfg.apiKey, baseURL: cfg.baseURL });
  const maxTokens = deps.maxTokens ?? resolveOcrMaxTokens(options.detail || "full");

  const completion = await client.chat.completions.create({
    model: cfg.model,
    messages: [
      { role: "system", content: OCR_IMAGE_SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text", text: buildOcrUserPrompt(outputFormat) },
          { type: "image_url", image_url: { url: dataUrl } },
        ],
      },
    ],
    max_tokens: maxTokens,
  });

  const text = completion.choices?.[0]?.message?.content;
  if (typeof text !== "string" || !text.trim()) {
    throw new Error("模型未返回文本内容");
  }
  return text.trim();
}

module.exports = {
  buildOcrUserPrompt,
  extractImageText,
};
