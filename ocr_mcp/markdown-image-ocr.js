"use strict";

const { listMarkdownImages } = require("./markdown-image-utils.js");
const { extractImageText } = require("./ocr-image.js");

async function extractMarkdownImageText(markdownPath, options = {}, deps = {}) {
  const lineNumbers = Array.isArray(options.lineNumbers)
    ? new Set(options.lineNumbers.map(Number))
    : null;
  const outputFormat = options.outputFormat === "markdown" ? "markdown" : "plain";
  const images = listMarkdownImages(markdownPath);
  const selected = lineNumbers
    ? images.filter((image) => lineNumbers.has(image.lineNumber))
    : images;

  const ocrImageText = deps.ocrImageText || ((imagePath) => extractImageText(imagePath, { outputFormat }));

  const results = [];
  for (const image of selected) {
    if (!image.exists) {
      results.push({
        ...image,
        status: "error",
        error: `图片不存在: ${image.resolvedPath}`,
      });
      continue;
    }

    try {
      const text = await ocrImageText(image.resolvedPath, { outputFormat });
      results.push({
        ...image,
        status: "loaded",
        text,
      });
    } catch (error) {
      results.push({
        ...image,
        status: "error",
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return results;
}

module.exports = {
  extractMarkdownImageText,
};
