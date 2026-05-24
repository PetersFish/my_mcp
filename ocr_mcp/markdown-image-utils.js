"use strict";

const fs = require("fs");
const path = require("path");

const { loadImageContent } = require("./image-utils.js");

const IMAGE_REF_RE = /!\[([^\]]*)\]\(([^)]+)\)/g;

function normalizeTarget(rawTarget) {
  const trimmed = rawTarget.trim();
  if (trimmed.startsWith("<") && trimmed.endsWith(">")) {
    return trimmed.slice(1, -1).trim();
  }
  const spaceIndex = trimmed.indexOf(" ");
  return spaceIndex === -1 ? trimmed : trimmed.slice(0, spaceIndex).trim();
}

function parseMarkdownImageReferences(markdownPath) {
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
    IMAGE_REF_RE.lastIndex = 0;
    let match;
    while ((match = IMAGE_REF_RE.exec(line))) {
      const altText = match[1];
      const target = normalizeTarget(match[2]);
      if (/^[a-z]+:\/\//i.test(target)) {
        continue;
      }

      const resolvedPath = path.isAbsolute(target)
        ? path.normalize(target)
        : path.resolve(baseDir, target);

      results.push({
        lineNumber: index + 1,
        rawReference: match[0],
        altText,
        resolvedPath,
        exists: fs.existsSync(resolvedPath),
      });
    }
  }

  return results;
}

function listMarkdownImages(markdownPath) {
  return parseMarkdownImageReferences(markdownPath);
}

function loadMarkdownImages(markdownPath, options = {}) {
  const lineNumbers = Array.isArray(options.lineNumbers)
    ? new Set(options.lineNumbers.map(Number))
    : null;

  const images = listMarkdownImages(markdownPath);
  const selected = lineNumbers
    ? images.filter((image) => lineNumbers.has(image.lineNumber))
    : images;

  return selected.map((image) => {
    if (!image.exists) {
      return {
        ...image,
        status: "error",
        error: `图片不存在: ${image.resolvedPath}`,
      };
    }

    try {
      const loaded = loadImageContent(image.resolvedPath);
      return {
        ...image,
        status: "loaded",
        content: loaded.content,
      };
    } catch (error) {
      return {
        ...image,
        status: "error",
        error: error instanceof Error ? error.message : String(error),
      };
    }
  });
}

module.exports = {
  loadMarkdownImages,
  listMarkdownImages,
  parseMarkdownImageReferences,
};
