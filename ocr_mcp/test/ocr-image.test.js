const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { extractImageText } = require("../ocr-image.js");

test("extractImageText sends plain OCR instructions", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-image-"));
  const imagePath = path.join(tmpDir, "sample.png");
  fs.writeFileSync(
    imagePath,
    Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
      "base64"
    )
  );

  let captured = null;
  const client = {
    chat: {
      completions: {
        create: async (payload) => {
          captured = payload;
          return {
            choices: [{ message: { content: "line 1\nline 2" } }],
          };
        },
      },
    },
  };

  const result = await extractImageText(imagePath, { outputFormat: "plain" }, { client });

  assert.equal(result, "line 1\nline 2");
  assert.match(captured.messages[0].content, /OCR转录助手/);
  assert.match(captured.messages[1].content[0].text, /plain/);
  assert.equal(captured.max_tokens, 8192);
});

test("extractImageText sends markdown OCR instructions", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ocr-mcp-image-"));
  const imagePath = path.join(tmpDir, "sample.png");
  fs.writeFileSync(
    imagePath,
    Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XH0sAAAAASUVORK5CYII=",
      "base64"
    )
  );

  let captured = null;
  const client = {
    chat: {
      completions: {
        create: async (payload) => {
          captured = payload;
          return {
            choices: [{ message: { content: "# title\nbody" } }],
          };
        },
      },
    },
  };

  const result = await extractImageText(imagePath, { outputFormat: "markdown" }, { client });

  assert.equal(result, "# title\nbody");
  assert.match(captured.messages[1].content[0].text, /markdown/);
});
