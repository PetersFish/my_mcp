const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const indexJs = fs.readFileSync(path.join(__dirname, "..", "index.js"), "utf8");
const readme = fs.readFileSync(path.join(__dirname, "..", "README.md"), "utf8");

test("README documents native multimodal first routing", () => {
  assert.match(readme, /优先用 `load_image` \/ `load_video`/);
  assert.match(readme, /load_image/);
  assert.match(readme, /load_markdown_images/);
  assert.match(readme, /describe_image/);
  assert.match(readme, /extract_image_text/);
});

test("index.js tool descriptions separate direct media loading from fallback tools", () => {
  assert.match(indexJs, /load_image[\s\S]*不做 OCR 或视觉总结/);
  assert.match(indexJs, /load_video[\s\S]*不做 OCR、抽帧或视频分析模型调用/);
  assert.match(indexJs, /load_markdown_images[\s\S]*多模态输入/);
  assert.match(indexJs, /load_markdown_media[\s\S]*图片\/视频引用/);
  assert.match(indexJs, /describe_image[\s\S]*云端多模态模型/);
  assert.match(indexJs, /extract_image_text[\s\S]*完整转录/);
  assert.match(indexJs, /video_path[\s\S]*支持 \.mp4 \.mov \.avi \.webm \.mkv \.m4v/);
  assert.match(indexJs, /media_types[\s\S]*image[\s\S]*video/);
});
