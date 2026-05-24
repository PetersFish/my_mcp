const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  parseMarkdownMediaReferences,
  listMarkdownMedia,
  loadMarkdownMedia,
} = require("../markdown-media-utils.js");

test("parseMarkdownMediaReferences returns local image and video metadata", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-media-"));
  const imageDir = path.join(tmpDir, "images");
  const videoDir = path.join(tmpDir, "videos");
  fs.mkdirSync(imageDir);
  fs.mkdirSync(videoDir);

  const imagePath = path.join(imageDir, "example.png");
  const videoPath = path.join(videoDir, "demo.mp4");
  fs.writeFileSync(
    imagePath,
    Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
      "base64"
    )
  );
  fs.writeFileSync(videoPath, Buffer.from("video-data"));

  const markdownPath = path.join(tmpDir, "note.md");
  fs.writeFileSync(
    markdownPath,
    [
      "# Note",
      "",
      "![Example image](images/example.png)",
      "",
      "[Demo video](videos/demo.mp4)",
      "",
      "![Missing](images/missing.png)",
    ].join("\n")
  );

  const results = parseMarkdownMediaReferences(markdownPath);

  assert.equal(results.length, 3);
  assert.deepEqual(results[0], {
    lineNumber: 3,
    rawReference: "![Example image](images/example.png)",
    labelText: "Example image",
    resolvedPath: imagePath,
    exists: true,
    mediaType: "image",
    mimeType: "image/png",
  });
  assert.deepEqual(results[1], {
    lineNumber: 5,
    rawReference: "[Demo video](videos/demo.mp4)",
    labelText: "Demo video",
    resolvedPath: videoPath,
    exists: true,
    mediaType: "video",
    mimeType: "video/mp4",
  });
  assert.deepEqual(results[2], {
    lineNumber: 7,
    rawReference: "![Missing](images/missing.png)",
    labelText: "Missing",
    resolvedPath: path.join(imageDir, "missing.png"),
    exists: false,
    mediaType: "image",
    mimeType: "image/png",
  });
});

test("listMarkdownMedia filters by media type", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-media-"));
  const markdownPath = path.join(tmpDir, "note.md");
  fs.writeFileSync(markdownPath, "![Example image](images/example.png)\n[Demo video](videos/demo.mp4)\n");

  const results = listMarkdownMedia(markdownPath, { mediaTypes: ["video"] });

  assert.equal(results.length, 1);
  assert.equal(results[0].mediaType, "video");
});

test("loadMarkdownMedia returns media content and resource entries", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-media-"));
  const imageDir = path.join(tmpDir, "images");
  const videoDir = path.join(tmpDir, "videos");
  fs.mkdirSync(imageDir);
  fs.mkdirSync(videoDir);

  const imagePath = path.join(imageDir, "example.png");
  const videoPath = path.join(videoDir, "demo.mp4");
  const imageBytes = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
    "base64"
  );
  fs.writeFileSync(imagePath, imageBytes);
  fs.writeFileSync(videoPath, Buffer.from("video-data"));

  const markdownPath = path.join(tmpDir, "note.md");
  fs.writeFileSync(
    markdownPath,
    [
      "![Example image](images/example.png)",
      "[Demo video](videos/demo.mp4)",
      "![Missing](images/missing.png)",
    ].join("\n")
  );

  const results = loadMarkdownMedia(markdownPath, { lineNumbers: [1, 2, 3] });

  assert.equal(results.length, 3);
  assert.equal(results[0].status, "loaded");
  assert.equal(results[0].content.type, "image");
  assert.equal(results[0].content.mimeType, "image/png");
  assert.equal(results[0].content.data, imageBytes.toString("base64"));
  assert.equal(results[1].status, "loaded");
  assert.equal(results[1].content.type, "resource");
  assert.equal(results[1].content.resource.mimeType, "video/mp4");
  assert.equal(results[1].content.resource.blob, Buffer.from("video-data").toString("base64"));
  assert.equal(results[2].status, "error");
  assert.match(results[2].error, /图片不存在|媒体不存在/);
});
