const test = require("node:test");
const assert = require("node:assert/strict");

const { OCR_IMAGE_SYSTEM_PROMPT } = require("../ocr-prompts.js");

test("OCR_IMAGE_SYSTEM_PROMPT forbids summarization and inference", () => {
  assert.match(OCR_IMAGE_SYSTEM_PROMPT, /完整转录/);
  assert.match(OCR_IMAGE_SYSTEM_PROMPT, /不要总结/);
  assert.match(OCR_IMAGE_SYSTEM_PROMPT, /不要翻译/);
  assert.match(OCR_IMAGE_SYSTEM_PROMPT, /不要改写/);
  assert.match(OCR_IMAGE_SYSTEM_PROMPT, /不要推断/);
});
