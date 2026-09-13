"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  parseArgs,
  setup,
  doctor,
  uninstall,
  loadUserConfig,
  findCommand,
  spawnOptions,
} = require("../lib/install.js");
const { resolveHome } = require("../lib/user-config.js");

const PACKAGE_ROOT = path.join(__dirname, "..");

function makeTempHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "ocr-vlm-home-"));
}

function writeMockCli(binDir, name) {
  const file = path.join(binDir, name);
  fs.writeFileSync(
    file,
    `#!/usr/bin/env node
const fs = require("fs");
const argv = process.argv.slice(2);
const logPath = process.env.FAKE_CLI_LOG;
const statePath = process.env.FAKE_CLI_STATE;
const bin = ${JSON.stringify(name)};
fs.appendFileSync(logPath, JSON.stringify({ bin, argv }) + "\\n");

function readState() {
  try {
    return JSON.parse(fs.readFileSync(statePath, "utf8"));
  } catch {
    return { claude: [], opencode: [] };
  }
}
function writeState(state) {
  fs.writeFileSync(statePath, JSON.stringify(state));
}
function flagsWithValues() {
  return new Set(["--scope", "--transport", "--client", "--url"]);
}
function serverNameFromAdd(args) {
  const flags = flagsWithValues();
  const names = [];
  for (let i = 2; i < args.length; i += 1) {
    if (args[i] === "--") break;
    if (flags.has(args[i])) {
      i += 1;
      continue;
    }
    if (args[i].startsWith("-")) continue;
    names.push(args[i]);
  }
  return names[0] || "ocr-vlm";
}
function serverNameFromRemove(args) {
  const flags = flagsWithValues();
  const names = [];
  for (let i = 2; i < args.length; i += 1) {
    if (args[i] === "--") break;
    if (flags.has(args[i])) {
      i += 1;
      continue;
    }
    if (args[i].startsWith("-")) continue;
    names.push(args[i]);
  }
  return names[0] || "ocr-vlm";
}

if (argv[0] === "mcp" && argv[1] === "add") {
  const state = readState();
  const key = bin === "claude" ? "claude" : "opencode";
  const server = serverNameFromAdd(argv);
  if (!state[key].includes(server)) state[key].push(server);
  writeState(state);
  process.exit(0);
}
if (argv[0] === "mcp" && argv[1] === "remove") {
  const state = readState();
  const key = bin === "claude" ? "claude" : "opencode";
  const server = serverNameFromRemove(argv);
  state[key] = (state[key] || []).filter((item) => item !== server);
  writeState(state);
  process.exit(0);
}
if (argv[0] === "mcp" && argv[1] === "list") {
  const state = readState();
  const key = bin === "claude" ? "claude" : "opencode";
  console.log((state[key] || []).join("\\n"));
  process.exit(0);
}
process.exit(0);
`
  );
  fs.chmodSync(file, 0o755);
  if (process.platform === "win32") {
    fs.writeFileSync(
      path.join(binDir, `${name}.cmd`),
      `@echo off\r\nnode "${file}" %*\r\n`
    );
  }
}

function readLog(logPath) {
  if (!fs.existsSync(logPath)) return [];
  return fs
    .readFileSync(logPath, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function createHarness(t) {
  const home = makeTempHome();
  const binDir = path.join(home, "bin");
  fs.mkdirSync(binDir);
  writeMockCli(binDir, "claude");
  writeMockCli(binDir, "opencode");
  const logPath = path.join(home, "cli.log");
  const statePath = path.join(home, "cli-state.json");
  fs.writeFileSync(statePath, JSON.stringify({ claude: [], opencode: [] }));
  const pathDirs = [
    binDir,
    path.dirname(process.execPath),
    "/usr/bin",
    "/bin",
    "/usr/local/bin",
  ];
  if (process.platform === "win32" && process.env.SystemRoot) {
    pathDirs.push(path.join(process.env.SystemRoot, "System32"));
  }
  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    PATH: pathDirs.join(path.delimiter),
    FAKE_CLI_LOG: logPath,
    FAKE_CLI_STATE: statePath,
    VISION_API_KEY: "test-key",
    VISION_MODEL: "qwen-vl-plus",
    VISION_BASE_URL: "https://example.test/v1",
  };
  t.after(() => {
    fs.rmSync(home, { recursive: true, force: true });
  });
  return { home, binDir, logPath, env };
}

test("parseArgs reads setup flags", () => {
  assert.deepEqual(parseArgs(["setup", "--yes", "--client", "claude", "--force-env"]), {
    command: "setup",
    yes: true,
    client: "claude",
    forceEnv: true,
    purge: false,
  });
  assert.deepEqual(parseArgs(["uninstall", "--purge"]), {
    command: "uninstall",
    yes: false,
    client: "all",
    forceEnv: false,
    purge: true,
  });
  assert.deepEqual(parseArgs([]), {
    command: null,
    yes: false,
    client: "all",
    forceEnv: false,
    purge: false,
  });
});

test("first setup writes config.env with 600 and registers both CLIs", async (t) => {
  const { home, logPath, env } = createHarness(t);
  const result = await setup({
    home,
    env,
    yes: true,
    skipDoctor: true,
    packageRoot: PACKAGE_ROOT,
    prompt() {
      throw new Error("should not prompt when env is present");
    },
  });
  assert.equal(result.ok, true);

  const configPath = path.join(home, ".config", "ocr-vlm", "config.env");
  assert.equal(fs.existsSync(configPath), true);
  if (process.platform !== "win32") {
    const mode = fs.statSync(configPath).mode & 0o777;
    assert.equal(mode, 0o600);
  }
  const loaded = loadUserConfig(home);
  assert.equal(loaded.VISION_API_KEY, "test-key");
  assert.equal(loaded.VISION_MODEL, "qwen-vl-plus");
  assert.equal(loaded.VISION_BASE_URL, "https://example.test/v1");

  const log = readLog(logPath);
  const claudeAdd = log.find(
    (entry) => entry.bin === "claude" && entry.argv[0] === "mcp" && entry.argv[1] === "add"
  );
  const opencodeAdd = log.find(
    (entry) => entry.bin === "opencode" && entry.argv[0] === "mcp" && entry.argv[1] === "add"
  );
  assert.ok(claudeAdd, "expected claude mcp add");
  assert.ok(opencodeAdd, "expected opencode mcp add");
  assert.ok(claudeAdd.argv.includes("--scope"));
  assert.ok(claudeAdd.argv.includes("user"));
  assert.ok(opencodeAdd.argv.includes("--global"));
  assert.ok(
    fs.existsSync(path.join(home, ".claude", "skills", "media-ocr-router", "SKILL.md"))
  );
  assert.ok(
    fs.existsSync(
      path.join(home, ".config", "opencode", "skills", "media-ocr-router", "SKILL.md")
    )
  );
});

test("second setup is idempotent and does not prompt", async (t) => {
  const { home, env } = createHarness(t);
  await setup({ home, env, yes: true, skipDoctor: true, packageRoot: PACKAGE_ROOT });
  let prompted = false;
  const result = await setup({
    home,
    env: { ...env, VISION_API_KEY: "", VISION_MODEL: "" },
    yes: false,
    skipDoctor: true,
    packageRoot: PACKAGE_ROOT,
    prompt() {
      prompted = true;
      throw new Error("should not prompt when config.env already has values");
    },
  });
  assert.equal(result.ok, true);
  assert.equal(prompted, false);
});

test("--client claude does not invoke opencode", async (t) => {
  const { home, logPath, env } = createHarness(t);
  const result = await setup({
    home,
    env,
    yes: true,
    client: "claude",
    skipDoctor: true,
    packageRoot: PACKAGE_ROOT,
  });
  assert.equal(result.ok, true);
  const log = readLog(logPath);
  assert.equal(
    log.some((entry) => entry.bin === "opencode"),
    false
  );
  assert.equal(
    fs.existsSync(
      path.join(home, ".config", "opencode", "skills", "media-ocr-router", "SKILL.md")
    ),
    false
  );
  assert.ok(
    fs.existsSync(path.join(home, ".claude", "skills", "media-ocr-router", "SKILL.md"))
  );
});

test("setup skips a missing client CLI instead of failing", async (t) => {
  const { home, binDir, env } = createHarness(t);
  fs.rmSync(path.join(binDir, "opencode"), { force: true });
  fs.rmSync(path.join(binDir, "opencode.cmd"), { force: true });
  const result = await setup({
    home,
    env,
    yes: true,
    skipDoctor: true,
    packageRoot: PACKAGE_ROOT,
  });
  assert.equal(result.ok, true);
  assert.ok(result.messages.some((msg) => /opencode/i.test(msg)));
});

test("doctor exits non-ok when key is missing", async (t) => {
  const home = makeTempHome();
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const result = await doctor({
    home,
    env: { ...process.env, HOME: home, PATH: home },
    packageRoot: PACKAGE_ROOT,
    skipProbe: true,
  });
  assert.equal(result.ok, false);
  assert.ok(result.issues.some((issue) => /VISION_API_KEY/.test(issue)));
});

test("uninstall removes MCP entries and --purge deletes config.env", async (t) => {
  const { home, logPath, env } = createHarness(t);
  await setup({ home, env, yes: true, skipDoctor: true, packageRoot: PACKAGE_ROOT });
  const configPath = path.join(home, ".config", "ocr-vlm", "config.env");
  const skillPath = path.join(home, ".claude", "skills", "media-ocr-router", "SKILL.md");

  const removed = await uninstall({ home, env, packageRoot: PACKAGE_ROOT });
  assert.equal(removed.ok, true);
  assert.equal(fs.existsSync(configPath), true);
  assert.equal(fs.existsSync(skillPath), true);
  const afterRemove = readLog(logPath).filter(
    (entry) => entry.argv[0] === "mcp" && entry.argv[1] === "remove"
  );
  assert.ok(afterRemove.some((entry) => entry.bin === "claude"));

  const purged = await uninstall({
    home,
    env,
    packageRoot: PACKAGE_ROOT,
    purge: true,
  });
  assert.equal(purged.ok, true);
  assert.equal(fs.existsSync(configPath), false);
  assert.equal(fs.existsSync(skillPath), false);
  assert.equal(
    fs.existsSync(
      path.join(home, ".config", "opencode", "skills", "media-ocr-router", "SKILL.md")
    ),
    false
  );
});

test("findCommand uses where on Windows and prefers .cmd", () => {
  const calls = [];
  const found = findCommand("claude", {}, {
    platform: "win32",
    run(cmd, args, opts) {
      calls.push({ cmd, args, shell: opts.shell });
      return {
        status: 0,
        stdout: "C:\\Tools\\claude.exe\r\nC:\\Tools\\claude.cmd\r\n",
      };
    },
  });
  assert.equal(calls[0].cmd, "where");
  assert.equal(calls[0].args[0], "claude");
  assert.equal(calls[0].shell, true);
  assert.equal(found, "C:\\Tools\\claude.cmd");
});

test("findCommand uses which on Unix", () => {
  const calls = [];
  const found = findCommand("claude", {}, {
    platform: "darwin",
    run(cmd, args, opts) {
      calls.push({ cmd, args, shell: opts.shell });
      return { status: 0, stdout: "/usr/local/bin/claude\n" };
    },
  });
  assert.equal(calls[0].cmd, "which");
  assert.equal(calls[0].shell, undefined);
  assert.equal(found, "/usr/local/bin/claude");
});

test("spawnOptions enables shell on Windows", () => {
  const win = spawnOptions({ env: {} }, "win32");
  assert.equal(win.shell, true);
  assert.equal(win.windowsHide, true);
  const unix = spawnOptions({ env: {} }, "darwin");
  assert.equal(unix.shell, undefined);
});

test("resolveHome prefers USERPROFILE when HOME is unset", () => {
  assert.equal(
    resolveHome({ USERPROFILE: "C:\\Users\\dev" }),
    "C:\\Users\\dev"
  );
  assert.equal(
    resolveHome({ HOME: "/Users/dev", USERPROFILE: "C:\\Users\\dev" }),
    "/Users/dev"
  );
});
