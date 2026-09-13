#!/usr/bin/env node
"use strict";

const path = require("path");
const os = require("os");
const {
  parseArgs,
  setup,
  doctor,
  uninstall,
  applyUserConfigToProcessEnv,
} = require("../lib/install.js");

function printResult(result) {
  for (const msg of result.messages || []) {
    console.log(msg);
  }
  for (const issue of result.issues || []) {
    console.error(issue);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.command) {
    applyUserConfigToProcessEnv();
    require("../index.js");
    return;
  }

  const home = process.env.HOME || os.homedir();
  const packageRoot = path.join(__dirname, "..");
  const common = {
    home,
    env: process.env,
    packageRoot,
    yes: args.yes,
    client: args.client,
    forceEnv: args.forceEnv,
    purge: args.purge,
  };

  if (args.command === "setup") {
    const result = await setup(common);
    printResult(result);
    if (!result.ok) process.exit(1);
    return;
  }
  if (args.command === "doctor") {
    const result = await doctor(common);
    printResult(result);
    if (!result.ok) process.exit(1);
    return;
  }
  if (args.command === "uninstall") {
    const result = await uninstall(common);
    printResult(result);
    if (!result.ok) process.exit(1);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
