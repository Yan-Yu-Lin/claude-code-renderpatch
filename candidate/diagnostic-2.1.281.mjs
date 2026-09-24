import { activate as activateDefault } from "./default.mjs"

export function activate(runtime) {
  const activation = activateDefault(runtime)
  const child = Bun.spawnSync({
    cmd: [process.execPath, "--version"],
    env: process.env,
    stdout: "pipe",
    stderr: "pipe",
  })
  const status = runtime.read.status()
  console.log(
    "RENDERPATCH_CANDIDATE_DIAGNOSTIC",
    JSON.stringify({
      bridgeActive: status.bridgeFacade.active,
      verificationMode: status.target.verificationMode,
      artifactVerified: status.target.artifactVerified,
      messageTranscript: globalThis.__rp.q(0, 0, "transcript"),
      messageRepl: globalThis.__rp.q(0, 0, "repl"),
      resetClassic: globalThis.__rp.q(1, false, "resize", false),
      toggleEnter: globalThis.__rp.q(2, false, true),
      providerWindowRetired: globalThis.__rp.q(3, 123456, "gpt-5.6") === 123456,
      explicitShortcut: globalThis.__rp.q(4, true, "opus", "claude-opus-5"),
      preloadEnvPresent: [
        "BUN_OPTIONS",
        "CLAUDE_RENDERPATCH_ACTIVE",
        "CLAUDE_RENDERPATCH_MODULE",
        "CLAUDE_RENDERPATCH_TARGET",
        "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
        "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
        "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
        "CLAUDE_RENDERPATCH_USER_MODULE",
      ].some((name) => name in process.env),
      childExitCode: child.exitCode,
      childStdout: child.stdout.toString().trim(),
      childStderr: child.stderr.toString().trim(),
    }),
  )
  return activation
}

export default activate
