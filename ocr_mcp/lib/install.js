"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const {
  configFile,
  loadUserConfig,
  saveUserConfig,
  applyUserConfigToProcessEnv,
} = require("./user-config.js");

const SERVER_NAME = "ocr-vlm";
const SKILL_NAME = "media-ocr-router";

function parseArgs(argv) {
  const result = {
    command: null,
    yes: false,
    client: "all",
    forceEnv: false,
    purge: false,
  };
  const rest = [...argv];
  if (rest[0] && !rest[0].startsWith("-")) {
    const cmd = rest.shift();
    if (!["setup", "doctor", "uninstall"].includes(cmd)) {
      throw new Error(`未知命令: ${cmd}`);
    }
    result.command = cmd;
  }
  while (rest.length) {
    const arg = rest.shift();
    if (arg === "--yes" || arg === "-y") {
      result.yes = true;
    } else if (arg === "--force-env") {
      result.forceEnv = true;
    } else if (arg === "--purge") {
      result.purge = true;
    } else if (arg === "--client") {
      const value = rest.shift();
      if (!["claude", "opencode", "all"].includes(value)) {
        throw new Error(`无效的 --client: ${value}`);
      }
      result.client = value;
    } else {
      throw new Error(`未知参数: ${arg}`);
    }
  }
  return result;
}

function assertNodeVersion() {
  const major = Number.parseInt(process.versions.node.split(".")[0], 10);
  if (!Number.isFinite(major) || major < 18) {
    throw new Error(`需要 Node.js 18+，当前为 ${process.versions.node}`);
  }
}

function ensureDependencies(packageRoot) {
  const marker = path.join(packageRoot, "node_modules", "@modelcontextprotocol");
  if (fs.existsSync(marker)) return;
  const result = spawnSync("npm", ["install"], {
    cwd: packageRoot,
    encoding: "utf8",
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error("npm install 失败");
  }
}

function findCommand(name, env) {
  const result = spawnSync("which", [name], { env, encoding: "utf8" });
  if (result.status === 0) {
    const found = (result.stdout || "").trim();
    if (found) return found;
  }
  return null;
}

function wantsClient(client, name) {
  return client === "all" || client === name;
}

function wrapperArgs(packageRoot) {
  return [process.execPath, path.join(packageRoot, "bin", "ocr-vlm-mcp.js")];
}

function skillSourceDir(packageRoot) {
  return path.join(packageRoot, "skills", SKILL_NAME);
}

function claudeSkillDir(home) {
  return path.join(home, ".claude", "skills", SKILL_NAME);
}

function opencodeSkillDir(home) {
  return path.join(home, ".config", "opencode", "skills", SKILL_NAME);
}

function copySkill(srcDir, destDir) {
  if (!fs.existsSync(srcDir)) {
    throw new Error(`未找到配套 skill: ${srcDir}`);
  }
  fs.mkdirSync(destDir, { recursive: true });
  for (const file of fs.readdirSync(srcDir)) {
    if (file.startsWith(".")) continue;
    const src = path.join(srcDir, file);
    if (!fs.statSync(src).isFile()) continue;
    fs.copyFileSync(src, path.join(destDir, file));
  }
}

function runCaptured(command, args, env) {
  return spawnSync(command, args, { env, encoding: "utf8" });
}

async function defaultPrompt(question) {
  const readline = require("readline/promises");
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stderr,
  });
  try {
    return (await rl.question(question)).trim();
  } finally {
    rl.close();
  }
}

async function resolveEnvValues({ home, env, yes, forceEnv, prompt }) {
  const ask = prompt || defaultPrompt;
  const existing = forceEnv ? {} : loadUserConfig(home);
  const pick = (key) => {
    const fromProc = String(env[key] || "").trim();
    const fromFile = String(existing[key] || "").trim();
    return fromProc || fromFile;
  };
  const values = {
    VISION_API_KEY: pick("VISION_API_KEY"),
    VISION_MODEL: pick("VISION_MODEL"),
    VISION_BASE_URL: pick("VISION_BASE_URL"),
  };

  if (!values.VISION_API_KEY) {
    if (yes) {
      throw new Error("缺少 VISION_API_KEY。请先 export，或去掉 --yes 后交互输入。");
    }
    values.VISION_API_KEY = await ask("VISION_API_KEY: ");
  }
  if (!values.VISION_MODEL) {
    if (yes) {
      throw new Error("缺少 VISION_MODEL。请先 export，或去掉 --yes 后交互输入。");
    }
    values.VISION_MODEL = await ask("VISION_MODEL（如 qwen-vl-plus）: ");
  }
  if (!values.VISION_API_KEY || !values.VISION_MODEL) {
    throw new Error("VISION_API_KEY 与 VISION_MODEL 为必填项。");
  }
  if (!values.VISION_BASE_URL && !yes && !existing.VISION_BASE_URL && !String(env.VISION_BASE_URL || "").trim()) {
    values.VISION_BASE_URL = await ask("VISION_BASE_URL（可空，直接回车跳过）: ");
  }
  return values;
}

function registerClaude({ env, packageRoot, messages }) {
  const claude = findCommand("claude", env);
  if (!claude) {
    messages.push(
      "未找到 claude CLI，已跳过 Claude Code 注册。安装后可再运行 npm run setup。"
    );
    return;
  }
  runCaptured(claude, ["mcp", "remove", "--scope", "user", SERVER_NAME], env);
  const result = runCaptured(
    claude,
    ["mcp", "add", "--scope", "user", "--transport", "stdio", SERVER_NAME, "--", ...wrapperArgs(packageRoot)],
    env
  );
  if (result.status !== 0) {
    throw new Error(
      `claude mcp add 失败: ${(result.stderr || result.stdout || "").trim()}`
    );
  }
  messages.push("已注册 Claude Code MCP（user scope）: ocr-vlm");
}

function registerOpencode({ env, packageRoot, messages }) {
  const opencode = findCommand("opencode", env);
  if (!opencode) {
    messages.push(
      "未找到 opencode CLI，已跳过 OpenCode 注册。安装后可再运行 npm run setup。"
    );
    return;
  }
  const addArgs = ["mcp", "add", "--global", SERVER_NAME, "--", ...wrapperArgs(packageRoot)];
  let result = runCaptured(opencode, addArgs, env);
  if (result.status !== 0) {
    result = runCaptured(opencode, ["mcp", "add", "--global", "--force", SERVER_NAME, "--", ...wrapperArgs(packageRoot)], env);
  }
  if (result.status !== 0) {
    throw new Error(
      `opencode mcp add 失败: ${(result.stderr || result.stdout || "").trim()}`
    );
  }
  messages.push("已注册 OpenCode MCP（global）: ocr-vlm");
}

function removeOpencodeJsonServer(home) {
  const candidates = [
    path.join(home, ".config", "opencode", "opencode.json"),
    path.join(home, ".config", "opencode", "opencode.jsonc"),
  ];
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    let data;
    try {
      data = JSON.parse(fs.readFileSync(file, "utf8"));
    } catch {
      continue;
    }
    let changed = false;
    if (data.mcp && data.mcp.servers && data.mcp.servers[SERVER_NAME]) {
      delete data.mcp.servers[SERVER_NAME];
      changed = true;
    }
    if (data.mcp && data.mcp[SERVER_NAME]) {
      delete data.mcp[SERVER_NAME];
      changed = true;
    }
    if (changed) {
      fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
    }
  }
}

function unregisterClaude({ env, messages }) {
  const claude = findCommand("claude", env);
  if (!claude) {
    messages.push("未找到 claude CLI，已跳过 Claude Code 卸载。");
    return;
  }
  runCaptured(claude, ["mcp", "remove", "--scope", "user", SERVER_NAME], env);
  messages.push("已从 Claude Code 移除 ocr-vlm");
}

function unregisterOpencode({ home, env, messages }) {
  const opencode = findCommand("opencode", env);
  if (opencode) {
    runCaptured(opencode, ["mcp", "remove", "--global", SERVER_NAME], env);
    runCaptured(opencode, ["mcp", "remove", SERVER_NAME], env);
  } else {
    messages.push("未找到 opencode CLI，改为尝试编辑全局配置。");
  }
  removeOpencodeJsonServer(home);
  messages.push("已从 OpenCode 配置移除 ocr-vlm（若存在）");
}

function checkListed(bin, env, issues, messages) {
  const command = findCommand(bin, env);
  if (!command) {
    messages.push(`未找到 ${bin}，跳过 mcp list 检查`);
    return;
  }
  const result = runCaptured(command, ["mcp", "list"], env);
  const text = `${result.stdout || ""}\n${result.stderr || ""}`;
  if (!new RegExp(SERVER_NAME).test(text)) {
    issues.push(`${bin} mcp list 未看到 ${SERVER_NAME}`);
  } else {
    messages.push(`${bin}: ${SERVER_NAME} 已注册`);
  }
}

function probeMcpInitialize(packageRoot, home, env) {
  return new Promise((resolve, reject) => {
    const bin = path.join(packageRoot, "bin", "ocr-vlm-mcp.js");
    const child = spawn(process.execPath, [bin], {
      env: { ...env, HOME: home },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.kill("SIGTERM");
      if (err) reject(err);
      else resolve();
    };
    const timer = setTimeout(() => {
      finish(new Error(stderr.trim() || "MCP initialize 超时"));
    }, 15000);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      if (/"result"\s*:/.test(stdout) || /"id"\s*:\s*1/.test(stdout)) {
        finish();
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (err) => finish(err));
    child.on("exit", (code) => {
      if (!settled && code && code !== 0) {
        finish(new Error(stderr.trim() || `MCP 进程退出码 ${code}`));
      }
    });
    const req = `${JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "ocr-vlm-doctor", version: "1.0.0" },
      },
    })}\n`;
    child.stdin.write(req);
  });
}

async function setup(options) {
  const home = options.home || os.homedir();
  const env = options.env || process.env;
  const packageRoot = options.packageRoot;
  const client = options.client || "all";
  const messages = [];
  assertNodeVersion();
  if (!options.skipNpmInstall) {
    ensureDependencies(packageRoot);
  }
  const values = await resolveEnvValues({
    home,
    env,
    yes: Boolean(options.yes),
    forceEnv: Boolean(options.forceEnv),
    prompt: options.prompt,
  });
  saveUserConfig(home, values);
  messages.push(`已写入 ${configFile(home)}`);

  if (wantsClient(client, "claude")) {
    registerClaude({ env, packageRoot, messages });
    copySkill(skillSourceDir(packageRoot), claudeSkillDir(home));
    messages.push(`已安装 skill 到 ${claudeSkillDir(home)}`);
  }
  if (wantsClient(client, "opencode")) {
    registerOpencode({ env, packageRoot, messages });
    copySkill(skillSourceDir(packageRoot), opencodeSkillDir(home));
    messages.push(`已安装 skill 到 ${opencodeSkillDir(home)}`);
  }

  if (!options.skipDoctor) {
    const health = await doctor({
      home,
      env,
      packageRoot,
      client,
      skipProbe: options.skipProbe,
    });
    messages.push(...health.messages);
    return {
      ok: health.ok,
      messages,
      issues: health.issues,
    };
  }
  return { ok: true, messages, issues: [] };
}

async function doctor(options) {
  const home = options.home || os.homedir();
  const env = options.env || process.env;
  const packageRoot = options.packageRoot;
  const issues = [];
  const messages = [];
  const client = options.client || "all";
  const cfg = loadUserConfig(home);
  if (!cfg.VISION_API_KEY) {
    issues.push("缺少 VISION_API_KEY（~/.config/ocr-vlm/config.env）");
  }
  if (!cfg.VISION_MODEL) {
    issues.push("缺少 VISION_MODEL（~/.config/ocr-vlm/config.env）");
  }
  if (wantsClient(client, "claude")) {
    checkListed("claude", env, issues, messages);
  }
  if (wantsClient(client, "opencode")) {
    checkListed("opencode", env, issues, messages);
  }
  if (!options.skipProbe && cfg.VISION_API_KEY && cfg.VISION_MODEL) {
    try {
      await probeMcpInitialize(packageRoot, home, env);
      messages.push("MCP initialize 成功");
    } catch (err) {
      issues.push(`MCP initialize 失败: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  return { ok: issues.length === 0, issues, messages };
}

async function uninstall(options) {
  const home = options.home || os.homedir();
  const env = options.env || process.env;
  const client = options.client || "all";
  const messages = [];
  if (wantsClient(client, "claude")) {
    unregisterClaude({ env, messages });
  }
  if (wantsClient(client, "opencode")) {
    unregisterOpencode({ home, env, messages });
  }
  if (options.purge) {
    fs.rmSync(configFile(home), { force: true });
    fs.rmSync(claudeSkillDir(home), { recursive: true, force: true });
    fs.rmSync(opencodeSkillDir(home), { recursive: true, force: true });
    messages.push("已删除 ~/.config/ocr-vlm/config.env 与已安装 skill");
  }
  return { ok: true, messages, issues: [] };
}

module.exports = {
  SERVER_NAME,
  parseArgs,
  setup,
  doctor,
  uninstall,
  loadUserConfig,
  applyUserConfigToProcessEnv,
  findCommand,
};
