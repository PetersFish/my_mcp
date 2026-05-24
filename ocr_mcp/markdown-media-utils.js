"use strict";

const fs = require("fs");
const path = require("path");

const { loadImageContent, MIME_BY_EXT } = require("./image-utils.js");
const { loadVideoContent, VIDEO_MIME_BY_EXT } = require("./video-utils.js");

const IMAGE_REF_RE = /!\[([^\]]*)\]\(([^)]+)\)/g;
const LINK_REF_RE = /(?<!!)(?:\[([^\]]*)\]\(([^)]+)\))/g;

function normalizeTarget(rawTarget) {
  const trimmed = rawTarget.trim();
  if (trimmed.startsWith("<") && trimmed.endsWith(">")) {
    return trimmed.slice(1, -1).trim();
  }
  const spaceIndex = trimmed.indexOf(" ");
  return spaceIndex === -1 ? trimmed : trimmed.slice(0, spaceIndex).trim();
}

function resolveMediaType(ext, isImage) {
  if (isImage) {
    return { mediaType: "image", mimeType: MIME_BY_EXT[ext] || null };
  }
  const mimeType = VIDEO_MIME_BY_EXT[ext] || null;
  return mimeType ? { mediaType: "video", mimeType } : null;
}

function pushImageMatches(line, index, baseDir, results) {
  IMAGE_REF_RE.lastIndex = 0;
  let match;
  while ((match = IMAGE_REF_RE.exec(line))) {
    const labelText = match[1];
    const target = normalizeTarget(match[2]);
    if (/^[a-z]+:\/\//i.test(target)) continue;

    const resolvedPath = path.isAbsolute(target)
      ? path.normalize(target)
      : path.resolve(baseDir, target);
    const ext = path.extname(resolvedPath).toLowerCase();
    const media = resolveMediaType(ext, true);
    if (!media) continue;

    results.push({
      lineNumber: index + 1,
      rawReference: match[0],
      labelText,
      resolvedPath,
      exists: fs.existsSync(resolvedPath),
      mediaType: media.mediaType,
      mimeType: media.mimeType,
    });
  }
}

function pushLinkMatches(line, index, baseDir, results) {
  LINK_REF_RE.lastIndex = 0;
  let match;
  while ((match = LINK_REF_RE.exec(line))) {
    const labelText = match[1];
    const target = normalizeTarget(match[2]);
    if (/^[a-z]+:\/\//i.test(target)) continue;

    const resolvedPath = path.isAbsolute(target)
      ? path.normalize(target)
      : path.resolve(baseDir, target);
    const ext = path.extname(resolvedPath).toLowerCase();
    const media = resolveMediaType(ext, false);
    if (!media) continue;

    results.push({
      lineNumber: index + 1,
      rawReference: match[0],
      labelText,
      resolvedPath,
      exists: fs.existsSync(resolvedPath),
      mediaType: media.mediaType,
      mimeType: media.mimeType,
    });
  }
}

function parseMarkdownMediaReferences(markdownPath) {
  const absMarkdownPath = path.isAbsolute(markdownPath)
    ? path.normalize(markdownPath)
    : path.resolve(process.cwd(), markdownPath);

  if (!fs.existsSync(absMarkdownPath)) {
    throw new Error(`Markdown 文件不存在: ${absMarkdownPath}`);
  }

  const markdown = fs.readFileSync(absMarkdownPath, "utf8");
  const baseDir = path.dirname(absMarkdownPath);
  const results = [];

  for (const [index, line] of markdown.split(/\r?\n/).entries()) {
    pushImageMatches(line, index, baseDir, results);
    pushLinkMatches(line, index, baseDir, results);
  }

  return results;
}

function listMarkdownMedia(markdownPath, options = {}) {
  const mediaTypes = Array.isArray(options.mediaTypes)
    ? new Set(options.mediaTypes.map(String))
    : null;

  const refs = parseMarkdownMediaReferences(markdownPath);
  return mediaTypes ? refs.filter((ref) => mediaTypes.has(ref.mediaType)) : refs;
}

function loadMarkdownMedia(markdownPath, options = {}) {
  const lineNumbers = Array.isArray(options.lineNumbers)
    ? new Set(options.lineNumbers.map(Number))
    : null;
  const mediaTypes = Array.isArray(options.mediaTypes)
    ? new Set(options.mediaTypes.map(String))
    : null;

  const refs = listMarkdownMedia(markdownPath, { mediaTypes: mediaTypes ? [...mediaTypes] : null });
  const selected = lineNumbers
    ? refs.filter((ref) => lineNumbers.has(ref.lineNumber))
    : refs;

  return selected.map((ref) => {
    if (!ref.exists) {
      return {
        ...ref,
        status: "error",
        error: `媒体不存在: ${ref.resolvedPath}`,
      };
    }

    try {
      if (ref.mediaType === "image") {
        const loaded = loadImageContent(ref.resolvedPath);
        return {
          ...ref,
          status: "loaded",
          content: loaded.content,
        };
      }

      const loaded = loadVideoContent(ref.resolvedPath);
      return {
        ...ref,
        status: "loaded",
        content: loaded.content,
      };
    } catch (error) {
      return {
        ...ref,
        status: "error",
        error: error instanceof Error ? error.message : String(error),
      };
    }
  });
}

module.exports = {
  listMarkdownMedia,
  loadMarkdownMedia,
  parseMarkdownMediaReferences,
};
