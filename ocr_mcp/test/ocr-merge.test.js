const test = require("node:test");
const assert = require("node:assert/strict");

const { mergeOcrSegments } = require("../ocr-merge.js");

test("mergeOcrSegments orders text top to bottom", () => {
  const result = mergeOcrSegments([
    { index: 1, startY: 1100, text: "Bottom" },
    { index: 0, startY: 0, text: "Top" },
  ]);

  assert.equal(result.text, "Top\n\nBottom");
  assert.equal(result.diagnostics, undefined);
});

test("mergeOcrSegments can include diagnostics", () => {
  const result = mergeOcrSegments(
    [
      { index: 1, startY: 1100, text: "Bottom" },
      { index: 0, startY: 0, text: "Top" },
    ],
    { includeDiagnostics: true }
  );

  assert.equal(result.text, "Top\n\nBottom");
  assert.deepEqual(result.diagnostics, [
    { index: 0, startY: 0 },
    { index: 1, startY: 1100 },
  ]);
});
