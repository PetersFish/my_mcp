const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { loadMarkdownImages } = require("../markdown-image-utils.js");

test("loadMarkdownImages filters by line number and reports per-image results", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-md-"));
  const imageDir = path.join(tmpDir, "images");
  fs.mkdirSync(imageDir);
  const imagePath = path.join(imageDir, "example.png");
  fs.writeFileSync(
    imagePath,
    Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
      "base64"
    )
  );

  const markdownPath = path.join(tmpDir, "note.md");
  fs.writeFileSync(
    markdownPath,
    [
      "![Keep](images/example.png)",
      "",
      "![Missing](images/missing.png)",
    ].join("\n")
  );

  const results = loadMarkdownImages(markdownPath, { lineNumbers: [1, 3] });

  assert.equal(results.length, 2);
  assert.equal(results[0].lineNumber, 1);
  assert.equal(results[0].status, "loaded");
  assert.equal(results[0].content.type, "image");
  assert.equal(results[0].content.mimeType, "image/png");
  assert.equal(results[1].lineNumber, 3);
  assert.equal(results[1].status, "error");
  assert.match(results[1].error, /图片不存在/);
});
