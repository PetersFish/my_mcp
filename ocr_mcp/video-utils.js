"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const VIDEO_MIME_BY_EXT = {
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".avi": "video/x-msvideo",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".m4v": "video/x-m4v",
};

function validateVideoPath(videoPath) {
  const trimmed = videoPath.trim();
  if (!trimmed) {
    throw new Error("video_path 不能为空");
  }

  const absPath = path.isAbsolute(trimmed)
    ? path.normalize(trimmed)
    : path.resolve(process.cwd(), trimmed);

  if (!fs.existsSync(absPath)) {
    throw new Error(`视频不存在: ${absPath}`);
  }

  const stat = fs.statSync(absPath);
  if (!stat.isFile()) {
    throw new Error(`路径不是文件: ${absPath}`);
  }

  const ext = path.extname(absPath).toLowerCase();
  const mimeType = VIDEO_MIME_BY_EXT[ext];
  if (!mimeType) {
    throw new Error(`不支持的视频格式（请使用 ${Object.keys(VIDEO_MIME_BY_EXT).join(", ")}）`);
  }

  return { absPath, mimeType, size: stat.size };
}

function loadVideoContent(videoPath) {
  const { absPath, mimeType, size } = validateVideoPath(videoPath);
  const blob = fs.readFileSync(absPath).toString("base64");

  return {
    absPath,
    size,
    content: {
      type: "resource",
      resource: {
        uri: pathToFileURL(absPath).href,
        mimeType,
        blob,
      },
    },
  };
}

module.exports = {
  VIDEO_MIME_BY_EXT,
  loadVideoContent,
  validateVideoPath,
};
