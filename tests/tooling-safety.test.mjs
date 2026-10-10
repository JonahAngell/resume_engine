import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const tools = path.resolve("tools");
const run = (root, tool, args = []) =>
  spawnSync(process.execPath, [path.join(tools, tool), ...args], {
    cwd: root,
    encoding: "utf8",
  });

test("partial-stage checker reports only intersecting paths", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "resume-stage-"));
  try {
    await writeFile(path.join(root, "staged"), Buffer.from("a.ts\0b.ts\0"));
    await writeFile(path.join(root, "unstaged"), Buffer.from("b.ts\0c.ts\0"));
    const result = run(root, "check-partially-staged.mjs", [
      "--staged",
      "staged",
      "--unstaged",
      "unstaged",
      "--output",
      "partial",
    ]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(await readFile(path.join(root, "partial"), "utf8"), "b.ts\n");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("review bundle rejects repository escape", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "resume-bundle-"));
  try {
    const result = run(root, "create-review-bundle.mjs", ["../outside.txt"]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /escapes repository/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("review bundle rejects sensitive paths and binaries", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "resume-bundle-"));
  try {
    await writeFile(path.join(root, ".env"), "SECRET=x\n");
    let result = run(root, "create-review-bundle.mjs", [".env"]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /not allowed/);
    await writeFile(path.join(root, "binary.bin"), Buffer.from([0, 1, 2, 3]));
    result = run(root, "create-review-bundle.mjs", ["binary.bin"]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Binary content/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("review bundle includes safe text with fingerprint", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "resume-bundle-"));
  try {
    await writeFile(path.join(root, "safe.txt"), "hello\n");
    const result = run(root, "create-review-bundle.mjs", [
      "--output",
      "bundle.txt",
      "safe.txt",
    ]);
    assert.equal(result.status, 0, result.stderr);
    const text = await readFile(path.join(root, "bundle.txt"), "utf8");
    assert.match(text, /BEGIN FILE: safe.txt/);
    assert.match(text, /[a-f0-9]{64}  safe\.txt/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
