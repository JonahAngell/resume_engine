#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import process from "node:process";

function parseArgs(args) {
  const options = {};
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    if (!["--staged", "--unstaged", "--output"].includes(key) || !value) {
      throw new Error(
        "Usage: check-partially-staged.mjs --staged <nul-file> --unstaged <nul-file> --output <text-file>",
      );
    }
    options[key.slice(2)] = value;
  }
  if (!options.staged || !options.unstaged || !options.output) {
    throw new Error("Missing required staged, unstaged, or output path.");
  }
  return options;
}

function parseNul(buffer) {
  return buffer.toString("utf8").split("\0").filter(Boolean);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const staged = new Set(parseNul(await readFile(options.staged)));
  const unstaged = new Set(parseNul(await readFile(options.unstaged)));
  const partial = [...staged]
    .filter((file) => unstaged.has(file))
    .sort((a, b) => a.localeCompare(b));
  await writeFile(
    options.output,
    partial.length ? `${partial.join("\n")}\n` : "",
    "utf8",
  );
}

main().catch((error) => {
  console.error(`Partial-stage check failed: ${error.message}`);
  process.exitCode = 1;
});
