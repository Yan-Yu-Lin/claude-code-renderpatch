// Prove that one-shot preload variables do not propagate to a child Claude process.
const child = Bun.spawnSync({
  cmd: [process.execPath, "--version"],
  env: process.env,
  stdout: "pipe",
  stderr: "pipe",
})

console.log(
  "CHILD_ENV",
  JSON.stringify({
    exitCode: child.exitCode,
    bunOptionsPresent: "BUN_OPTIONS" in process.env,
    activePresent: "CLAUDE_RENDERPATCH_ACTIVE" in process.env,
    targetPresent: "CLAUDE_RENDERPATCH_TARGET" in process.env,
    childStdout: child.stdout.toString().trim(),
    childStderr: child.stderr.toString().trim(),
  }),
)
