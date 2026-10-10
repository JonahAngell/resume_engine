#!/usr/bin/env node
import { readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const OUTPUT = "PROJECT_TREE.txt";
const EXCLUDED_NAMES = new Set([
  ".git",
  ".venv",
  "node_modules",
  "dist",
  "__pycache__",
  ".pytest_cache",
  "playwright-report",
  "test-results",
  "htmlcov",
  ".coverage",
  ".env",
  "REVIEW_BUNDLE.txt",
  OUTPUT,
]);

async function entries(directory) {
  return (await readdir(directory, { withFileTypes: true }))
    .filter(
      (entry) =>
        !EXCLUDED_NAMES.has(entry.name) && !entry.name.endsWith(".zip"),
    )
    .sort((left, right) => {
      if (left.isDirectory() !== right.isDirectory())
        return left.isDirectory() ? -1 : 1;
      return left.name.localeCompare(right.name);
    });
}

async function build(directory, prefix = "") {
  const children = await entries(directory);
  const lines = [];
  for (let index = 0; index < children.length; index += 1) {
    const child = children[index];
    const last = index === children.length - 1;
    lines.push(`${prefix}${last ? "└── " : "├── "}${child.name}`);
    if (child.isDirectory()) {
      lines.push(
        ...(await build(
          path.join(directory, child.name),
          `${prefix}${last ? "    " : "│   "}`,
        )),
      );
    }
  }
  return lines;
}

await writeFile(OUTPUT, `${[".", ...(await build("."))].join("\n")}\n`, "utf8");
console.log(`Updated ${OUTPUT}`);
