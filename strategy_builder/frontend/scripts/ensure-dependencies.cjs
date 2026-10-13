/** Synchronize stale node_modules after pulling dependency changes; preserve the lockfile. */
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const cwd = path.resolve(__dirname, "..");
const command = process.env.npm_execpath ? process.execPath : "npm";
const prefix = process.env.npm_execpath ? [process.env.npm_execpath] : [];

function npm(args, stdio) {
  return spawnSync(command, [...prefix, ...args], { cwd, stdio });
}

const check = npm(["ls", "--depth=0", "--include=dev"], "ignore");
if (check.error) {
  console.error(`[Dependencies] Could not run npm: ${check.error.message}`);
  process.exit(1);
}
if (check.status === 0) process.exit(0);

console.log("[Dependencies] Missing or incompatible packages detected; running npm ci...");
const install = npm(["ci", "--include=dev"], "inherit");
if (install.error || install.status !== 0) {
  console.error("[Dependencies] Installation failed. Check npm registry access and package-lock.json.");
  process.exit(1);
}
const verified = npm(["ls", "--depth=0", "--include=dev"], "ignore");
process.exit(verified.error || verified.status !== 0 ? 1 : 0);
