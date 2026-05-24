const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveOcrMaxTokens } = require("../ocr-config.js");

test("resolveOcrMaxTokens uses higher defaults than describe_image", () => {
  const original = process.env.VISION_OCR_MAX_TOKENS;
  delete process.env.VISION_OCR_MAX_TOKENS;

  assert.equal(resolveOcrMaxTokens("brief"), 4096);
  assert.equal(resolveOcrMaxTokens("full"), 8192);

  if (original === undefined) {
    delete process.env.VISION_OCR_MAX_TOKENS;
  } else {
    process.env.VISION_OCR_MAX_TOKENS = original;
  }
});

test("resolveOcrMaxTokens honors VISION_OCR_MAX_TOKENS", () => {
  const original = process.env.VISION_OCR_MAX_TOKENS;
  process.env.VISION_OCR_MAX_TOKENS = "12345";

  assert.equal(resolveOcrMaxTokens("brief"), 12345);
  assert.equal(resolveOcrMaxTokens("full"), 12345);

  if (original === undefined) {
    delete process.env.VISION_OCR_MAX_TOKENS;
  } else {
    process.env.VISION_OCR_MAX_TOKENS = original;
  }
});
