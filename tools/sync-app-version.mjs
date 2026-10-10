import { readFile, rename, unlink, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const VERSION_SOURCE = "frontend/src/app-version.ts";
const VERSION_FILES = [VERSION_SOURCE, "PROJECT_CONTEXT.md"];
const VERSION_PATTERN = /^v(\d+)\.(\d+)\.(\d+)$/;
const SOURCE_PATTERN = /^export const RESUME_ENGINE_VERSION = "([^"]+)";$/gm;
const TARGET = {
  file: "PROJECT_CONTEXT.md",
  id: "PROJECT-CONTEXT",
  render: (version) => `**Current version:** ${version}`,
};

function fail(message) {
  throw new Error(message);
}
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function readAuthoritativeVersion(source) {
  const matches = [...source.matchAll(SOURCE_PATTERN)];
  if (matches.length !== 1)
    fail(
      `${VERSION_SOURCE}: expected exactly one RESUME_ENGINE_VERSION declaration; found ${matches.length}.`,
    );
  if (!VERSION_PATTERN.test(matches[0][1]))
    fail(
      `${VERSION_SOURCE}: invalid RESUME_ENGINE_VERSION "${matches[0][1]}".`,
    );
  return matches[0][1];
}
function nextVersion(version) {
  const match = version.match(VERSION_PATTERN);
  if (!match)
    fail(
      `${VERSION_SOURCE}: ${version} cannot be bumped; expected vMAJOR.MINOR.PATCH.`,
    );
  return `v${match[1]}.${match[2]}.${Number(match[3]) + 1}`;
}
function replaceSourceVersion(source, version) {
  const matches = [...source.matchAll(SOURCE_PATTERN)];
  if (matches.length !== 1)
    fail(
      `${VERSION_SOURCE}: expected exactly one declaration; found ${matches.length}.`,
    );
  return source.replace(
    SOURCE_PATTERN,
    `export const RESUME_ENGINE_VERSION = "${version}";`,
  );
}
function replaceManagedRegion(content, version) {
  const begin = `<!-- RESUME-ENGINE-VERSION:${TARGET.id}:BEGIN -->`;
  const end = `<!-- RESUME-ENGINE-VERSION:${TARGET.id}:END -->`;
  const pattern = new RegExp(
    `${escapeRegExp(begin)}\\r?\\n([\\s\\S]*?)\\r?\\n${escapeRegExp(end)}`,
    "g",
  );
  const matches = [...content.matchAll(pattern)];
  if (matches.length !== 1)
    fail(
      `${TARGET.file}: expected exactly one managed region ${TARGET.id}; found ${matches.length}.`,
    );
  const expected = TARGET.render(version);
  return {
    content: content.replace(pattern, `${begin}\n${expected}\n${end}`),
    current: matches[0][1],
    expected,
  };
}
async function atomicWrite(file, content) {
  const temporary = `${file}.resume-version-${process.pid}.tmp`;
  try {
    await writeFile(temporary, content, "utf8");
    await rename(temporary, file);
  } catch (error) {
    await unlink(temporary).catch(() => {});
    throw error;
  }
}
function git(root, args, { allowFailure = false } = {}) {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
  if (result.status !== 0 && !allowFailure)
    fail(
      `git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim()}`,
    );
  return result;
}
function gitPath(root, name) {
  return path.resolve(
    root,
    git(root, ["rev-parse", "--git-path", name]).stdout.trim(),
  );
}
async function exists(file) {
  try {
    await readFile(file);
    return true;
  } catch {
    return false;
  }
}
async function inProgressOperation(root) {
  for (const name of [
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "rebase-merge",
    "rebase-apply",
  ])
    if (await exists(gitPath(root, name))) return name;
  return null;
}
async function readVersionFromHead(root) {
  const result = git(root, ["show", `HEAD:${VERSION_SOURCE}`], {
    allowFailure: true,
  });
  return result.status === 0 ? readAuthoritativeVersion(result.stdout) : null;
}
async function loadPlan(root, version, { replaceSource = false } = {}) {
  const originals = new Map();
  for (const file of VERSION_FILES)
    originals.set(file, await readFile(path.join(root, file), "utf8"));
  const outputs = new Map(originals);
  if (replaceSource)
    outputs.set(
      VERSION_SOURCE,
      replaceSourceVersion(outputs.get(VERSION_SOURCE), version),
    );
  const region = replaceManagedRegion(outputs.get(TARGET.file), version);
  outputs.set(TARGET.file, region.content);
  return {
    originals,
    outputs,
    drift:
      region.current === region.expected
        ? []
        : [`${TARGET.file} (${TARGET.id})`],
  };
}
async function writePlan(root, plan) {
  for (const [file, content] of plan.outputs)
    if (content !== plan.originals.get(file))
      await atomicWrite(path.join(root, file), content);
}
function stagedNonVersionFiles(root) {
  const result = git(root, [
    "diff",
    "--cached",
    "--name-only",
    "--diff-filter=ACMR",
  ]);
  const managed = new Set(VERSION_FILES);
  return result.stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .filter((file) => !managed.has(file) && file !== "PROJECT_TREE.txt");
}
async function hookMode(root) {
  const operation = await inProgressOperation(root);
  if (operation) {
    console.log(
      `Skipping automatic application-version bump during ${operation}.`,
    );
    return;
  }
  if (/amend/i.test(process.env.GIT_REFLOG_ACTION || "")) {
    console.log("Skipping automatic application-version bump during amend.");
    return;
  }
  if (stagedNonVersionFiles(root).length === 0) {
    console.log(
      "Skipping automatic application-version bump because no eligible non-version change is staged.",
    );
    return;
  }
  const source = await readFile(path.join(root, VERSION_SOURCE), "utf8");
  const current = readAuthoritativeVersion(source);
  const head = await readVersionFromHead(root);
  if (!head) fail("Cannot determine the application version from HEAD.");
  const expected = nextVersion(head);
  if (current !== head && current !== expected)
    fail(
      `Working version ${current} is not HEAD ${head} or its next version ${expected}; review manually.`,
    );
  const target = current === head ? expected : current;
  const plan = await loadPlan(root, target, {
    replaceSource: current === head,
  });
  await writePlan(root, plan);
  const check = await loadPlan(root, target);
  if (check.drift.length)
    fail(`Version remains out of sync: ${check.drift.join(", ")}.`);
  git(root, ["add", "--", ...VERSION_FILES]);
  console.log(
    current === head
      ? `Prepared and staged application version ${target}.`
      : `Reused and staged prepared application version ${target}.`,
  );
}
async function main() {
  const args = process.argv.slice(2);
  const root = process.cwd();
  const modes = [
    args.includes("--check"),
    args.includes("--bump"),
    args.includes("--hook"),
  ].filter(Boolean).length;
  if (
    modes > 1 ||
    args.some((arg) => !["--check", "--bump", "--hook"].includes(arg))
  )
    fail("Usage: node tools/sync-app-version.mjs [--check|--bump|--hook]");
  if (args.includes("--hook")) return hookMode(root);
  const source = await readFile(path.join(root, VERSION_SOURCE), "utf8");
  const current = readAuthoritativeVersion(source);
  const version = args.includes("--bump") ? nextVersion(current) : current;
  const plan = await loadPlan(root, version, {
    replaceSource: args.includes("--bump"),
  });
  if (args.includes("--check")) {
    if (plan.drift.length)
      fail(
        `Application version ${version} is out of sync in: ${plan.drift.join(", ")}. Run npm run version:sync.`,
      );
    console.log(`Application version ${version} is synchronized.`);
    return;
  }
  await writePlan(root, plan);
  console.log(
    args.includes("--bump")
      ? `Bumped and synchronized application version ${current} -> ${version}.`
      : `Application version ${version} synchronized.`,
  );
}
main().catch((error) => {
  console.error(`Version synchronization failed: ${error.message}`);
  process.exitCode = 1;
});
