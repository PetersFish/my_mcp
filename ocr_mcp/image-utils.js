"use strict";

const fs = require("fs");
const path = require("path");

const MIME_BY_EXT = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".bmp": "image/bmp",
};

function validateImagePath(imagePath) {
  const trimmed = imagePath.trim();
  if (!trimmed) {
    throw new Error("image_path 不能为空");
  }

  const absPath = path.isAbsolute(trimmed)
    ? path.normalize(trimmed)
    : path.resolve(process.cwd(), trimmed);

  if (!fs.existsSync(absPath)) {
    throw new Error(`图片不存在: ${absPath}`);
  }

  const stat = fs.statSync(absPath);
  if (!stat.isFile()) {
    throw new Error(`路径不是文件: ${absPath}`);
  }

  const ext = path.extname(absPath).toLowerCase();
  const mime = MIME_BY_EXT[ext];
  if (!mime) {
    throw new Error(`不支持的扩展名（请使用 ${Object.keys(MIME_BY_EXT).join(", ")}）`);
  }

  return { absPath, mime, size: stat.size };
}

function loadImageContent(imagePath) {
  const { absPath, mime, size } = validateImagePath(imagePath);
  const data = fs.readFileSync(absPath).toString("base64");
  return {
    absPath,
    size,
    content: {
      type: "image",
      data,
      mimeType: mime,
    },
  };
}

module.exports = {
  MIME_BY_EXT,
  loadImageContent,
  validateImagePath,
};
