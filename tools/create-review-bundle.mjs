#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, realpath, stat, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

const DEFAULT_OUTPUT = "REVIEW_BUNDLE.txt";
const DEFAULT_TITLE = "RESUME ENGINE REVIEW BUNDLE";
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_BUNDLE_BYTES = 10 * 1024 * 1024;
const BLOCKED_NAMES = new Set([
  ".env",
  ".env.local",
  ".env.development",
  ".env.production",
  "id_rsa",
  "id_ed25519",
]);
const BLOCKED_PARTS = new Set([
  ".git",
  ".venv",
  "node_modules",
  "secret",
  "secrets",
  ".auth",
  "playwright-report",
  "test-results",
]);

function parseArgs(args) {
  const result = {
    manifest: null,
    output: DEFAULT_OUTPUT,
    title: DEFAULT_TITLE,
    files: [],
  };
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--files") result.manifest = args[++i];
    else if (arg === "--output") result.output = args[++i];
    else if (arg === "--title") result.title = args[++i];
    else if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: node tools/create-review-bundle.mjs [--files manifest] [--output file] [--title text] [file ...]",
      );
      process.exit(0);
    } else if (arg.startsWith("--")) throw new Error(`Unknown option: ${arg}`);
    else result.files.push(arg);
    if (
      (arg === "--files" || arg === "--output" || arg === "--title") &&
      !args[i]
    )
      throw new Error(`${arg} requires a value.`);
  }
  return result;
}

function git(args) {
  try {
    return execFileSync("git", args, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trimEnd();
  } catch {
    return null;
  }
}

function isBinary(buffer) {
  if (buffer.includes(0)) return true;
  const sample = buffer.subarray(0, Math.min(buffer.length, 8192));
  let suspicious = 0;
  for (const byte of sample)
    if (byte < 7 || (byte > 13 && byte < 32)) suspicious += 1;
  return sample.length > 0 && suspicious / sample.length > 0.03;
}

function relativePosix(root, absolute) {
  return path.relative(root, absolute).split(path.sep).join("/");
}

function assertSafeRelative(relative) {
  if (
    !relative ||
    relative === "." ||
    relative.startsWith("../") ||
    path.isAbsolute(relative)
  )
    throw new Error(`Path escapes repository: ${relative || "[empty]"}`);
  const parts = relative.split("/");
  if (
    parts.some((part) => BLOCKED_PARTS.has(part.toLowerCase())) ||
    BLOCKED_NAMES.has(parts.at(-1).toLowerCase()) ||
    parts.at(-1).toLowerCase().startsWith(".env.")
  ) {
    throw new Error(`Sensitive or generated path is not allowed: ${relative}`);
  }
}

async function manifestFiles(file, root) {
  const absolute = path.resolve(root, file);
  const relative = relativePosix(root, absolute);
  assertSafeRelative(relative);
  return (await readFile(absolute, "utf8"))
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));
}

async function collect(requested, root, outputAbsolute) {
  const results = [];
  let total = 0;
  for (const supplied of [...new Set(requested)]) {
    const absolute = path.resolve(root, supplied);
    const relative = relativePosix(root, absolute);
    assertSafeRelative(relative);
    if (absolute === outputAbsolute)
      throw new Error("The output file cannot also be an input.");
    let canonical;
    try {
      canonical = await realpath(absolute);
    } catch {
      throw new Error(`Requested file does not exist: ${relative}`);
    }
    const canonicalRelative = relativePosix(root, canonical);
    assertSafeRelative(canonicalRelative);
    if (
      canonicalRelative.startsWith("../") ||
      path.isAbsolute(canonicalRelative)
    )
      throw new Error(`Resolved path escapes repository: ${relative}`);
    const info = await stat(canonical);
    if (!info.isFile())
      throw new Error(`Requested path is not a regular file: ${relative}`);
    if (info.size > MAX_FILE_BYTES)
      throw new Error(`File exceeds ${MAX_FILE_BYTES} byte limit: ${relative}`);
    const buffer = await readFile(canonical);
    if (isBinary(buffer))
      throw new Error(`Binary content is not allowed: ${relative}`);
    total += buffer.length;
    if (total > MAX_BUNDLE_BYTES)
      throw new Error(`Bundle inputs exceed ${MAX_BUNDLE_BYTES} byte limit.`);
    results.push({
      relative,
      buffer,
      sha: createHash("sha256").update(buffer).digest("hex"),
    });
  }
  return results;
}

function divider() {
  return "=".repeat(80);
}
function build(title, files, root) {
  const d = divider();
  const commit = git(["rev-parse", "HEAD"]) || "[Unavailable]";
  const branch =
    git(["branch", "--show-current"]) || "[Detached HEAD or unavailable]";
  const status = git(["status", "--short"]) || "[Clean or unavailable]";
  const lines = [
    title,
    `Generated: ${new Date().toISOString()}`,
    `Project root: ${root}`,
    "",
    d,
    "REPOSITORY FINGERPRINT",
    d,
    `Commit: ${commit}`,
    `Branch: ${branch}`,
    "Working tree status:",
    status,
    "",
    d,
    "FILE INVENTORY AND SHA-256",
    d,
  ];
  for (const file of files) lines.push(`${file.sha}  ${file.relative}`);
  for (const file of files) {
    lines.push(
      "",
      d,
      `BEGIN FILE: ${file.relative}`,
      d,
      "",
      file.buffer.toString("utf8"),
    );
    if (file.buffer.length && !file.buffer.toString("utf8").endsWith("\n"))
      lines.push("");
    lines.push(d, `END FILE: ${file.relative}`, d);
  }
  return `${lines.join("\n")}\n`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const root = await realpath(process.cwd());
  const output = path.resolve(root, options.output);
  const outputRelative = relativePosix(root, output);
  assertSafeRelative(outputRelative);
  let requested = [...options.files];
  if (options.manifest)
    requested = [
      ...(await manifestFiles(options.manifest, root)),
      ...requested,
    ];
  if (!requested.length) throw new Error("No files requested.");
  const files = await collect(requested, root, output);
  const bundle = build(options.title, files, root);
  if (Buffer.byteLength(bundle) > MAX_BUNDLE_BYTES)
    throw new Error(`Generated bundle exceeds ${MAX_BUNDLE_BYTES} byte limit.`);
  await writeFile(output, bundle, "utf8");
  console.log(`Created ${outputRelative} with ${files.length} file(s).`);
}

main().catch((error) => {
  console.error(`Review bundle failed: ${error.message}`);
  process.exitCode = 1;
});
