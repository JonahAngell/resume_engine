import assert from "node:assert/strict";
import { cp, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
const tool = path.resolve("tools/sync-app-version.mjs");
async function fixture(version) {
  const root = await mkdtemp(path.join(tmpdir(), "resume-version-"));
  await mkdir(path.join(root, "frontend/src"), { recursive: true });
  await writeFile(
    path.join(root, "frontend/src/app-version.ts"),
    `export const RESUME_ENGINE_VERSION = "${version}";\n`,
  );
  await writeFile(
    path.join(root, "PROJECT_CONTEXT.md"),
    `<!-- RESUME-ENGINE-VERSION:PROJECT-CONTEXT:BEGIN -->\n**Current version:** ${version}\n<!-- RESUME-ENGINE-VERSION:PROJECT-CONTEXT:END -->\n`,
  );
  return root;
}
function run(root, ...args) {
  return spawnSync(process.execPath, [tool, ...args], {
    cwd: root,
    encoding: "utf8",
  });
}
for (const [from, to] of [
  ["v0.1.0", "v0.1.1"],
  ["v2.0.9", "v2.0.10"],
  ["v2.10.99", "v2.10.100"],
])
  test(`${from} bumps to ${to}`, async () => {
    const root = await fixture(from);
    try {
      assert.equal(run(root, "--bump").status, 0);
      assert.match(
        await readFile(path.join(root, "frontend/src/app-version.ts"), "utf8"),
        new RegExp(to.replaceAll(".", "\\.")),
      );
      assert.equal(run(root, "--check").status, 0);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
for (const bad of ["0.1.0", "v1", "v1.2", "v1.2.3-beta"])
  test(`rejects ${bad}`, async () => {
    const root = await fixture(bad);
    try {
      assert.equal(run(root, "--bump").status, 1);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
