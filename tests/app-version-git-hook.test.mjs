import assert from "node:assert/strict";
import { cp, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
const source = process.cwd();
function git(root, ...args) {
  return spawnSync("git", args, { cwd: root, encoding: "utf8" });
}
async function repo() {
  const root = await mkdtemp(path.join(tmpdir(), "resume-hook-"));
  for (const file of [
    "frontend/src/app-version.ts",
    "PROJECT_CONTEXT.md",
    "tools/sync-app-version.mjs",
  ]) {
    const directory = path.dirname(file);
    if (directory !== ".")
      await mkdir(path.join(root, directory), { recursive: true });
    await cp(path.join(source, file), path.join(root, file));
  }
  git(root, "init");
  git(root, "config", "user.email", "test@example.test");
  git(root, "config", "user.name", "Test");
  git(root, "add", ".");
  git(root, "commit", "-m", "baseline", "--no-verify");
  return root;
}
test("normal hook mode bumps once and stages managed files", async () => {
  const root = await repo();
  try {
    await writeFile(path.join(root, "change.txt"), "one\n");
    git(root, "add", "change.txt");
    const result = spawnSync(
      process.execPath,
      [path.join(root, "tools/sync-app-version.mjs"), "--hook"],
      { cwd: root, encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    assert.match(
      await readFile(path.join(root, "frontend/src/app-version.ts"), "utf8"),
      /v0\.1\.1/,
    );
    const staged = git(root, "diff", "--cached", "--name-only").stdout;
    assert.match(staged, /frontend\/src\/app-version\.ts/);
    assert.match(staged, /PROJECT_CONTEXT\.md/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
test("hook retry reuses prepared version", async () => {
  const root = await repo();
  try {
    await writeFile(path.join(root, "change.txt"), "one\n");
    git(root, "add", "change.txt");
    for (let index = 0; index < 2; index += 1) {
      const result = spawnSync(
        process.execPath,
        [path.join(root, "tools/sync-app-version.mjs"), "--hook"],
        { cwd: root, encoding: "utf8" },
      );
      assert.equal(result.status, 0, result.stderr);
    }
    assert.match(
      await readFile(path.join(root, "frontend/src/app-version.ts"), "utf8"),
      /v0\.1\.1/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
