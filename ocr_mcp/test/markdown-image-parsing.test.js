const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  listMarkdownImages,
  parseMarkdownImageReferences,
} = require("../markdown-image-utils.js");

test("parseMarkdownImageReferences returns local image metadata", () => {
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
      "# Note",
      "",
      "![Example image](images/example.png)",
      "",
      "![Missing image](images/missing.png)",
    ].join("\n")
  );

  const results = parseMarkdownImageReferences(markdownPath);

  assert.equal(results.length, 2);
  assert.deepEqual(results[0], {
    lineNumber: 3,
    rawReference: "![Example image](images/example.png)",
    altText: "Example image",
    resolvedPath: imagePath,
    exists: true,
  });
  assert.deepEqual(results[1], {
    lineNumber: 5,
    rawReference: "![Missing image](images/missing.png)",
    altText: "Missing image",
    resolvedPath: path.join(imageDir, "missing.png"),
    exists: false,
  });
});

test("listMarkdownImages returns local image metadata", () => {
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
  fs.writeFileSync(markdownPath, "![Example image](images/example.png)\n");

  const results = listMarkdownImages(markdownPath);

  assert.deepEqual(results, [
    {
      lineNumber: 1,
      rawReference: "![Example image](images/example.png)",
      altText: "Example image",
      resolvedPath: imagePath,
      exists: true,
    },
  ]);
});
