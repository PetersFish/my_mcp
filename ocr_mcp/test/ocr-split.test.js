const test = require("node:test");
const assert = require("node:assert/strict");

const { planVerticalSlices } = require("../ocr-split.js");

test("planVerticalSlices returns overlapping top-to-bottom slices", () => {
  const slices = planVerticalSlices(3000, {
    threshold: 1600,
    sliceHeight: 1200,
    overlap: 100,
  });

  assert.deepEqual(slices, [
    { index: 0, startY: 0, endY: 1200 },
    { index: 1, startY: 1100, endY: 2300 },
    { index: 2, startY: 2200, endY: 3000 },
  ]);
});

test("planVerticalSlices leaves short images unsplit", () => {
  const slices = planVerticalSlices(1200, {
    threshold: 1600,
    sliceHeight: 1200,
    overlap: 100,
  });

  assert.deepEqual(slices, [{ index: 0, startY: 0, endY: 1200 }]);
});
