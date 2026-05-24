const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { validateImagePath, loadImageContent } = require("../image-utils.js");

test("validateImagePath returns abs path, mime type, and file size", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-image-"));
  const imagePath = path.join(tmpDir, "sample.png");
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
    "base64"
  );
  fs.writeFileSync(imagePath, png);

  const result = validateImagePath(imagePath);

  assert.equal(result.absPath, imagePath);
  assert.equal(result.mime, "image/png");
  assert.equal(result.size, png.length);
});

test("validateImagePath rejects missing image", () => {
  const missing = path.join(os.tmpdir(), `does-not-exist-${Date.now()}.png`);

  assert.throws(() => validateImagePath(missing), /图片不存在/);
});

test("loadImageContent returns MCP image content", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-image-"));
  const imagePath = path.join(tmpDir, "sample.png");
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
    "base64"
  );
  fs.writeFileSync(imagePath, png);

  const result = loadImageContent(imagePath);

  assert.equal(result.absPath, imagePath);
  assert.equal(result.content.type, "image");
  assert.equal(result.content.mimeType, "image/png");
  assert.equal(result.content.data, png.toString("base64"));
});
