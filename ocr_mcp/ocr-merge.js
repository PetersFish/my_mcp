"use strict";

function mergeOcrSegments(segments, options = {}) {
  const ordered = [...segments].sort((a, b) => a.startY - b.startY);
  const text = ordered
    .map((segment) => (segment.text || "").trim())
    .filter(Boolean)
    .join("\n\n");

  if (options.includeDiagnostics) {
    return {
      text,
      diagnostics: ordered.map((segment) => ({
        index: segment.index,
        startY: segment.startY,
      })),
    };
  }

  return { text };
}

module.exports = {
  mergeOcrSegments,
};
