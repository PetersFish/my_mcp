"use strict";

function resolveOcrMaxTokens(detail) {
  const override = parseInt(process.env.VISION_OCR_MAX_TOKENS || "", 10);
  if (Number.isFinite(override) && override > 0) {
    return override;
  }

  return detail === "brief" ? 4096 : 8192;
}

module.exports = {
  resolveOcrMaxTokens,
};
