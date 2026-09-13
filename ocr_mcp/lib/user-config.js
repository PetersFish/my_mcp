"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const ENV_KEYS = [
  "VISION_API_KEY",
  "VISION_MODEL",
  "VISION_BASE_URL",
  "VISION_MAX_TOKENS",
  "VISION_OCR_MAX_TOKENS",
];

function resolveHome(env = process.env) {
  return env.HOME || env.USERPROFILE || os.homedir();
}

function configDir(home = resolveHome()) {
  return path.join(home, ".config", "ocr-vlm");
}

function configFile(home = resolveHome()) {
  return path.join(configDir(home), "config.env");
}

function parseEnvFile(content) {
  const out = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

function serializeEnv(values) {
  const lines = [];
  for (const key of ENV_KEYS) {
    if (values[key] == null || values[key] === "") continue;
    lines.push(`${key}=${values[key]}`);
  }
  return `${lines.join("\n")}\n`;
}

function loadUserConfig(home = resolveHome()) {
  const file = configFile(home);
  if (!fs.existsSync(file)) return {};
  return parseEnvFile(fs.readFileSync(file, "utf8"));
}

function saveUserConfig(home, values) {
  const dir = configDir(home);
  fs.mkdirSync(dir, { recursive: true });
  const file = configFile(home);
  fs.writeFileSync(file, serializeEnv(values), { mode: 0o600 });
  try {
    fs.chmodSync(file, 0o600);
  } catch {
    // NTFS does not honor Unix permission bits.
  }
  return file;
}

function applyUserConfigToProcessEnv(home = resolveHome()) {
  const loaded = loadUserConfig(home);
  for (const [key, value] of Object.entries(loaded)) {
    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

module.exports = {
  ENV_KEYS,
  resolveHome,
  configDir,
  configFile,
  parseEnvFile,
  serializeEnv,
  loadUserConfig,
  saveUserConfig,
  applyUserConfigToProcessEnv,
};
