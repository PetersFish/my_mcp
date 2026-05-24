"use strict";

function planVerticalSlices(height, options = {}) {
  const threshold = options.threshold ?? 1600;
  const sliceHeight = options.sliceHeight ?? 1200;
  const overlap = options.overlap ?? 100;

  if (height <= threshold) {
    return [{ index: 0, startY: 0, endY: height }];
  }

  const slices = [];
  let startY = 0;
  let index = 0;

  while (startY < height) {
    const endY = Math.min(height, startY + sliceHeight);
    slices.push({ index, startY, endY });
    if (endY >= height) {
      break;
    }
    startY = Math.max(0, endY - overlap);
    index += 1;
  }

  return slices;
}

module.exports = {
  planVerticalSlices,
};
