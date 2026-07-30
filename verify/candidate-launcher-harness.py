#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify the immutable single-command SDK candidate installation and launcher."""

from __future__ import annotations

import hashlib
import json
import os
import pty
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "candidate" / "install.sh"
RELEASE_ID = "2.1.220-internal-sdk-2.1.220.1-97dfb182"
TARGET_SHA256 = "97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157"
LAUNCHER_SHA256 = "bde3b01a00995a830dc313dc4ad06aed222a2c976a9fabaea49427b6c9911223"
RELEASE_MANIFEST_SHA256 = (
    "c3623177141eff845f2f264281c84efb9db513ffbc7dd3d631c50a0f64f7c192"
)
SCRUB_ENV = {
    "BUN_OPTIONS",
    "CLAUDE_PRELOAD_BOOTSTRAP",
    "CLAUDE_PRELOAD_TARGET",
    "CLAUDE_PRELOAD_VERSIONS_DIR",
    "CLAUDE_RENDERPATCH_ACTIVE",
    "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
    "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
    "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
    "CLAUDE_RENDERPATCH_MODULE",
    "CLAUDE_RENDERPATCH_RELEASE_DIR",
    "CLAUDE_RENDERPATCH_LINK",
    "CLAUDE_RENDERPATCH_TARGET",
    "CLAUDE_RENDERPATCH_USER_MODULE",
}
PRESERVED_PATHS = (
    Path.home() / ".local/bin/claude",
    Path.home() / ".local/bin/claude-mix",
    Path.home() / ".local/bin/claude-preload-lab",
    Path.home() / ".cli-proxy-api/.local-api-key",
    Path.home() / ".claude/settings.json",
    Path.home() / ".claude/claude-mix-settings.json",
)


def require(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(str(message))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(path: Path) -> tuple[object, ...]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return ("absent",)
    if stat.S_ISLNK(info.st_mode):
        return ("symlink", os.readlink(path), stat.S_IMODE(info.st_mode))
    if stat.S_ISREG(info.st_mode):
        return ("file", info.st_size, stat.S_IMODE(info.st_mode), sha256(path))
    return ("other", info.st_size, stat.S_IMODE(info.st_mode))


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    for name in SCRUB_ENV:
        merged_env.pop(name, None)
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=merged_env,
        timeout=timeout,
        check=False,
    )


def run_pty(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    seconds: float = 8.0,
) -> str:
    merged_env = os.environ.copy()
    for name in SCRUB_ENV:
        merged_env.pop(name, None)
    if env:
        merged_env.update(env)
    merged_env.setdefault("TERM", "xterm-256color")
    master, slave = pty.openpty()
    process = subprocess.Popen(
        command,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=merged_env,
        start_new_session=True,
    )
    os.close(slave)
    output = bytearray()
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline and process.poll() is None:
            ready, _, _ = select.select([master], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
            if b"REAL_SAFE_FACADES " in output:
                break
        if process.poll() is None:
            os.write(master, b"\x03\x03")
            time.sleep(0.2)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    finally:
        os.close(master)
    return output.decode("utf-8", errors="replace")


def success(label: str, result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode != 0:
        raise AssertionError(f"{label} failed with exit {result.returncode}:\n{result.stdout}")
    return result.stdout


def status_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def json_line(output: str, prefix: str) -> dict[str, object]:
    line = next((line for line in output.splitlines() if line.startswith(prefix)), None)
    require(line is not None, output)
    return json.loads(line.removeprefix(prefix))


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def make_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        try:
            mode = stat.S_IMODE(path.lstat().st_mode)
            if not path.is_symlink():
                path.chmod(mode | stat.S_IWUSR)
        except FileNotFoundError:
            pass


def main() -> int:
    before = {str(path): snapshot(path) for path in PRESERVED_PATHS}
    for sensitive in (
        Path.home() / ".cli-proxy-api/.local-api-key",
        Path.home() / ".claude/claude-mix-settings.json",
    ):
        require(sensitive.is_file() and not sensitive.is_symlink(), sensitive)
        require(stat.S_IMODE(sensitive.stat().st_mode) == 0o600, sensitive)
    fixture = Path(tempfile.mkdtemp(prefix="claude-renderpatch-candidate-", dir=Path.home()))
    release = fixture / "releases" / RELEASE_ID
    link = fixture / "bin" / "claude-renderpatch-candidate"
    install_env = {
        "CLAUDE_RENDERPATCH_RELEASE_DIR": str(release),
        "CLAUDE_RENDERPATCH_LINK": str(link),
    }
    user_module = fixture / "user-extension.mjs"
    user_module.write_text(
        """export function activate(runtime) {
  console.log("USER_EXTENSION", JSON.stringify({
    ran: true,
    runtimeApiVersion: runtime.runtimeApiVersion,
    defaultPolicy: globalThis.__rp.q(0, 0, "transcript"),
    argvHasOption: process.argv.includes("--renderpatch-extension"),
    argvHasModulePath: process.argv.includes(import.meta.path),
    userEnvPresent: "CLAUDE_RENDERPATCH_USER_MODULE" in process.env,
  }))
}
export default activate
""",
        encoding="utf-8",
    )
    live_facade_log = fixture / "live-safe-facades.jsonl"
    live_facade_module = fixture / "live-safe-facades.mjs"
    live_facade_module.write_text(
        """import {appendFileSync} from "node:fs"

export function activate(runtime) {
  let emitted = false
  const report = () => {
    if (emitted) return
    const captures = [0, 1, 2, 3, 4, 5].map((id) => runtime.read.captureMetadata(id))
    if (!captures.every((capture) => capture.available)) return
    emitted = true
    const generations = Object.fromEntries(captures.map((capture) => [capture.id, capture.generation]))
    const repl = runtime.read.repl.state(generations[4])
    const result = {
      mc: runtime.read.mc.canonicalize("claude-opus-5", generations[0]).available,
      sr: runtime.read.sr.preview("opus", "claude-opus-5", generations[0]).available,
      msg: runtime.read.msg.counts(generations[3])?.counts?.rendered !== null,
      repl: repl?.currentView?.type === "object",
      replCurrentViewIsString: typeof repl?.currentView === "string",
      app: runtime.read.app.metadata(generations[2]).available,
      ink: runtime.read.ink.frame(generations[1]).available,
      key: runtime.read.key.catalog(generations[5]).available,
      diag: runtime.read.diag.status(generations[1]).available,
      msgExport: runtime.actions.msg.export({generation: generations[3], limit: 5}).available,
      statusContainsRaw: JSON.stringify(runtime.read.status()).includes("prompt"),
    }
    appendFileSync(process.env.LIVE_SAFE_LOG, JSON.stringify(result) + "\\n")
  }
  const disposers = [0, 1, 2, 3, 4, 5].map((id) => runtime.read.observe(id, report))
  report()
  return () => disposers.forEach((dispose) => dispose())
}
export default activate
""",
        encoding="utf-8",
    )
    throwing_module = fixture / "throwing-user-extension.mjs"
    throwing_module.write_text(
        """export function activate() {
  console.log("THROWING_USER_DEFAULT", globalThis.__rp.q(0, 0, "transcript"))
  throw new Error("intentional user extension failure")
}
export default activate
""",
        encoding="utf-8",
    )
    symlink_module = fixture / "user-extension-symlink.mjs"
    symlink_module.symlink_to(user_module)
    wrong_mode_file = fixture / "wrong-mode-sensitive.txt"
    wrong_mode_file.write_text("sensitive fixture\n", encoding="utf-8")
    wrong_mode_file.chmod(0o644)
    wrong_owner_file = Path.home() / ".local/bin/reach-mac-agent"
    require(wrong_owner_file.is_file(), wrong_owner_file)
    require(wrong_owner_file.stat().st_uid != os.getuid(), wrong_owner_file)
    outside_descriptor, outside_name = tempfile.mkstemp(
        prefix="claude-renderpatch-user-", suffix=".mjs", dir="/private/tmp"
    )
    os.close(outside_descriptor)
    outside_module = Path(outside_name)
    outside_module.write_text('console.log("OUTSIDE_USER_RAN")\n', encoding="utf-8")

    mock_bin = fixture / "mock-bin"
    mock_bin.mkdir()
    mock_log = fixture / "mock-children.log"
    mock_state = fixture / "mock-listener-state"
    leak_check = """for name in BUN_OPTIONS CLAUDE_RENDERPATCH_ACTIVE CLAUDE_RENDERPATCH_MODULE CLAUDE_RENDERPATCH_USER_MODULE CLAUDE_RENDERPATCH_TARGET CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256 CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION; do
  if [[ -v "$name" ]]; then printf 'LEAK %s %s\\n' "${0##*/}" "$name" >>"$RP_MOCK_LOG"; fi
done
"""
    write_executable(
        mock_bin / "lsof",
        f"""#!/usr/bin/env bash
{leak_check}state="$(cat "$RP_MOCK_STATE" 2>/dev/null || printf absent)"
if [[ "$*" == *-tiTCP:* ]]; then
  [[ "$state" != absent ]] || exit 1
  printf '4242\\n'
  exit 0
fi
case "$state" in
  trusted) command_name=cliproxyapi; listener_uid="$UID" ;;
  wronguid) command_name=cliproxyapi; listener_uid="$((UID + 1))" ;;
  *) command_name=unexpected-listener; listener_uid="$UID" ;;
esac
printf 'p4242\\nc%s\\nu%s\\n' "$command_name" "$listener_uid"
""",
    )
    write_executable(
        mock_bin / "ps",
        f"""#!/usr/bin/env bash
{leak_check}printf '%s --mock\\n' "$RP_MOCK_BIN/cliproxyapi"
""",
    )
    write_executable(
        mock_bin / "curl",
        f"""#!/usr/bin/env bash
{leak_check}printf '%s\\n' "$*" >>"$RP_MOCK_CURL_ARGV"
input="$(cat)"
printf '%s\\n' "$input" >"$RP_MOCK_CURL_STDIN"
printf '{{"object":"list"}}\\n'
""",
    )
    write_executable(
        mock_bin / "brew",
        f"""#!/usr/bin/env bash
{leak_check}printf 'brew %s\\n' "$*" >>"$RP_MOCK_LOG"
printf trusted >"$RP_MOCK_STATE"
""",
    )
    write_executable(mock_bin / "cliproxyapi", "#!/usr/bin/env bash\nexit 0\n")
    tests: list[tuple[str, str]] = []

    try:
        install_output = success(
            "candidate install",
            run([str(INSTALLER)], env=install_env, timeout=600.0),
        )
        require("Installed immutable Claude renderpatch candidate" in install_output, install_output)
        require(link.is_symlink(), link)
        require(link.resolve() == release / "claude-renderpatch-candidate", link)
        tests.append(("immutable staged install", str(release)))

        verify_output = success(
            "candidate verify",
            run([str(INSTALLER), "--verify"], env=install_env, timeout=300.0),
        )
        require("Verified immutable Claude renderpatch candidate" in verify_output, verify_output)

        release_manifest_path = release / "release-manifest.json"
        release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
        require(sha256(release_manifest_path) == RELEASE_MANIFEST_SHA256, release_manifest)
        require(release_manifest["signedArtifactSha256"] == TARGET_SHA256, release_manifest)
        for relative, metadata in release_manifest["assets"].items():
            path = release / relative
            require(path.is_file() and not path.is_symlink(), path)
            require(sha256(path) == metadata["sha256"], path)
            require(stat.S_IMODE(path.stat().st_mode) == int(metadata["mode"], 8), path)
        launcher = release / "claude-renderpatch-candidate"
        require(sha256(launcher) == LAUNCHER_SHA256, launcher)
        require(stat.S_IMODE(launcher.stat().st_mode) == 0o555, launcher)
        require(stat.S_IMODE(release.stat().st_mode) == 0o555, release)
        tests.append(("release hashes and modes", "manifest, target, runtime, launcher"))

        trust_helper = release / "helpers/trust-file.py"
        success(
            "trusted proxy key",
            run(
                [
                    "python3",
                    str(trust_helper),
                    "Proxy API key",
                    str(Path.home() / ".cli-proxy-api/.local-api-key"),
                    "0600",
                ]
            ),
        )
        success(
            "trusted settings overlay",
            run(
                [
                    "python3",
                    str(trust_helper),
                    "Settings overlay",
                    str(Path.home() / ".claude/claude-mix-settings.json"),
                    "0600",
                ]
            ),
        )
        trust_rejections = (
            (wrong_mode_file, "mode must be 0o600"),
            (symlink_module, "must not be a symlink"),
            (wrong_owner_file, "is not user-owned"),
        )
        for untrusted_path, expected_error in trust_rejections:
            rejected_trust = run(
                [
                    "python3",
                    str(trust_helper),
                    "Sensitive fixture",
                    str(untrusted_path),
                    "0600",
                ]
            )
            require(rejected_trust.returncode != 0, rejected_trust.stdout)
            require(expected_error in rejected_trust.stdout, rejected_trust.stdout)
        tests.append(("proxy key/overlay trust validator", "mode, symlink, owner"))

        idempotent_output = success(
            "idempotent reinstall",
            run([str(INSTALLER)], env=install_env, timeout=600.0),
        )
        require("Installed immutable Claude renderpatch candidate" in idempotent_output, idempotent_output)
        tests.append(("idempotent reinstall", "ok"))

        status_output = success(
            "candidate status",
            run([str(link), "--renderpatch-status"], timeout=300.0),
        )
        status_data = status_values(status_output)
        require(status_data["release_id"] == RELEASE_ID, status_data)
        require(status_data["reported_version"] == "2.1.220 (Claude Code)", status_data)
        require(status_data["target_sha256"] == TARGET_SHA256, status_data)
        require(status_data["bridge_build_id"] == "internal-sdk-2.1.220.1", status_data)
        require(status_data["policy_domains"] == "0,1,2,3,4", status_data)
        require(status_data["capture_domains"] == "0,1,2,3,4,5", status_data)
        require(status_data["user_extension"] == "<none>", status_data)
        require(status_data["mode"] == "multi-provider", status_data)
        require(
            status_data["proxy_listener"] == "trusted-current-user-cliproxyapi",
            status_data,
        )
        require(status_data["verification"] == "ok", status_data)
        tests.append(("metadata-only candidate status", json.dumps(status_data)))

        extension_status_output = success(
            "candidate status with user extension metadata",
            run(
                [
                    str(link),
                    "--renderpatch-extension",
                    str(user_module),
                    "--renderpatch-status",
                ],
                timeout=300.0,
            ),
        )
        extension_status = status_values(extension_status_output)
        require(extension_status["user_extension"] == user_module.name, extension_status)
        require("USER_EXTENSION" not in extension_status_output, extension_status_output)
        tests.append(("status reports user extension basename only", user_module.name))

        normal_output = success(
            "candidate normal version",
            run([str(link), "--version"], timeout=300.0),
        ).strip()
        require(normal_output == "2.1.220 (Claude Code)", normal_output)
        tests.append(("normal multi-provider launch", normal_output))

        mock_curl_argv = fixture / "mock-curl.argv"
        mock_curl_stdin = fixture / "mock-curl.stdin"
        mock_env = {
            "PATH": f"{mock_bin}:{os.environ['PATH']}",
            "RP_MOCK_BIN": str(mock_bin),
            "RP_MOCK_LOG": str(mock_log),
            "RP_MOCK_STATE": str(mock_state),
            "RP_MOCK_CURL_ARGV": str(mock_curl_argv),
            "RP_MOCK_CURL_STDIN": str(mock_curl_stdin),
        }
        mock_log.write_text("", encoding="utf-8")
        if mock_state.exists():
            success("trash stale mock state", run(["trash", str(mock_state)]))
        mocked_start_output = success(
            "mocked proxy startup",
            run([str(link), "--version"], env=mock_env, timeout=300.0),
        )
        require("starting cliproxyapi via brew services" in mocked_start_output, mocked_start_output)
        require("2.1.220 (Claude Code)" in mocked_start_output, mocked_start_output)
        child_log = mock_log.read_text(encoding="utf-8")
        require("LEAK" not in child_log, child_log)
        require("brew services start cliproxyapi" in child_log, child_log)
        curl_argv = mock_curl_argv.read_text(encoding="utf-8")
        proxy_token = (Path.home() / ".cli-proxy-api/.local-api-key").read_text(
            encoding="utf-8"
        ).strip()
        require(proxy_token not in curl_argv, "proxy token appeared in curl argv")
        require("-H @-" in curl_argv, curl_argv)
        curl_stdin = mock_curl_stdin.read_text(encoding="utf-8").strip()
        require(curl_stdin == f"Authorization: Bearer {proxy_token}", "header stdin mismatch")
        tests.append(("pre-target children clean and token off argv", "mocked startup"))

        for listener_state, expected_error in (
            ("untrusted", "unexpected TCP 8317 listener"),
            ("wronguid", "unexpected TCP 8317 listener"),
        ):
            mock_state.write_text(listener_state, encoding="utf-8")
            mock_log.write_text("", encoding="utf-8")
            untrusted_listener = run(
                [str(link), "--version"], env=mock_env, timeout=60.0
            )
            require(untrusted_listener.returncode != 0, untrusted_listener.stdout)
            require(expected_error in untrusted_listener.stdout, untrusted_listener.stdout)
            require("2.1.220 (Claude Code)" not in untrusted_listener.stdout, untrusted_listener.stdout)
            require("brew services start" not in mock_log.read_text(encoding="utf-8"), mock_log)
        tests.append(("untrusted proxy listeners fail closed", "identity and UID"))

        user_output = success(
            "trusted user extension",
            run(
                [
                    str(link),
                    "--renderpatch-extension",
                    str(user_module),
                    "--version",
                ],
                timeout=300.0,
            ),
        )
        user_result = json_line(user_output, "USER_EXTENSION ")
        require(user_result["ran"] is True, user_result)
        require(user_result["runtimeApiVersion"] == 2, user_result)
        require(user_result["defaultPolicy"] == 3, user_result)
        require(user_result["argvHasOption"] is False, user_result)
        require(user_result["argvHasModulePath"] is False, user_result)
        require(user_result["userEnvPresent"] is False, user_result)
        require("2.1.220 (Claude Code)" in user_output, user_output)
        tests.append(("trusted user extension after defaults", json.dumps(user_result)))

        live_output = run_pty(
            [str(release / "claude-2.1.220-internal-sdk")],
            env={
                "BUN_OPTIONS": f"--preload={release / 'bootstrap.mjs'}",
                "CLAUDE_RENDERPATCH_ACTIVE": "1",
                "CLAUDE_RENDERPATCH_MODULE": str(release / "extensions/default.mjs"),
                "CLAUDE_RENDERPATCH_USER_MODULE": str(live_facade_module),
                "CLAUDE_RENDERPATCH_TARGET": str(
                    release / "claude-2.1.220-internal-sdk"
                ),
                "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID": "internal-sdk-2.1.220.1",
                "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256": TARGET_SHA256,
                "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION": "2.1.220",
                "LIVE_SAFE_LOG": str(live_facade_log),
            },
            seconds=10.0,
        )
        require(live_facade_log.is_file(), live_output[-4000:])
        live_lines = live_facade_log.read_text(encoding="utf-8").splitlines()
        require(live_lines, live_output[-4000:])
        live_facades = json.loads(live_lines[-1])
        for domain in ("mc", "sr", "msg", "repl", "app", "ink", "key", "diag"):
            require(live_facades[domain] is True, live_facades)
        require(live_facades["replCurrentViewIsString"] is False, live_facades)
        require(live_facades["msgExport"] is True, live_facades)
        require(live_facades["statusContainsRaw"] is False, live_facades)
        tests.append(("real signed-candidate safe facades d0-d5", json.dumps(live_facades)))

        for swallowed_mode in ("--renderpatch-safe", "--renderpatch-diagnose"):
            missing_operand = run(
                [
                    str(link),
                    "--renderpatch-extension",
                    swallowed_mode,
                    "--version",
                ],
                timeout=60.0,
            )
            require(missing_operand.returncode == 2, missing_operand.stdout)
            require("not another wrapper option" in missing_operand.stdout, missing_operand.stdout)
            require("2.1.220 (Claude Code)" not in missing_operand.stdout, missing_operand.stdout)
        delimiter_module = run(
            [
                str(link),
                "--version",
                "--",
                "--renderpatch-extension",
                str(user_module),
            ],
            timeout=300.0,
        )
        require("USER_EXTENSION" not in delimiter_module.stdout, delimiter_module.stdout)
        delimiter_safe = run(
            [str(link), "--", "--renderpatch-safe", "--version"],
            env={"BUN_OPTIONS": "--smol"},
            timeout=60.0,
        )
        require(delimiter_safe.returncode != 0, delimiter_safe.stdout)
        require("refusing inherited BUN_OPTIONS" in delimiter_safe.stdout, delimiter_safe.stdout)
        tests.append(("transactional wrapper parser and delimiter", "exact regressions"))

        hostile_env = {
            "BUN_OPTIONS": "--smol",
            "CLAUDE_RENDERPATCH_ACTIVE": "hostile",
            "CLAUDE_RENDERPATCH_MODULE": "/hostile.mjs",
            "CLAUDE_RENDERPATCH_TARGET": "/hostile",
            "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID": "hostile",
            "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256": "0" * 64,
            "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION": "0.0.0",
            "CLAUDE_RENDERPATCH_USER_MODULE": "/hostile-user.mjs",
        }
        safe_output = success(
            "candidate safe version",
            run(
                [
                    str(link),
                    "--renderpatch-extension",
                    str(user_module),
                    "--renderpatch-safe",
                    "--version",
                ],
                env=hostile_env,
                timeout=300.0,
            ),
        ).strip()
        require(safe_output == "2.1.220 (Claude Code)", safe_output)
        require("USER_EXTENSION" not in safe_output, safe_output)
        tests.append(("safe launch ignores user extension and hostile env", safe_output))

        for name in (
            "BUN_OPTIONS",
            "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
            "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
            "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
            "CLAUDE_RENDERPATCH_USER_MODULE",
        ):
            rejected = run(
                [str(link), "--version"],
                env={name: "hostile"},
                timeout=60.0,
            )
            require(rejected.returncode != 0, rejected.stdout)
            require(f"refusing inherited {name}" in rejected.stdout, rejected.stdout)
        tests.append(("ambient preload and bridge metadata rejected", "five variables"))

        diagnostic_output = success(
            "candidate diagnostic",
            run([str(link), "--renderpatch-diagnose"], timeout=300.0),
        )
        diagnostic = json_line(diagnostic_output, "RENDERPATCH_CANDIDATE_DIAGNOSTIC ")
        require(diagnostic["bridgeActive"] is True, diagnostic)
        require(diagnostic["verificationMode"] == "signed-bridge-artifact", diagnostic)
        require(diagnostic["artifactVerified"] is True, diagnostic)
        require(diagnostic["messageTranscript"] == 3, diagnostic)
        require(diagnostic["messageRepl"] == 2, diagnostic)
        require(diagnostic["resetClassic"] is True, diagnostic)
        require(diagnostic["toggleEnter"] is True, diagnostic)
        require(diagnostic["kimiWindow"] == 262144, diagnostic)
        require(diagnostic["otherWindow"] == 372000, diagnostic)
        require(diagnostic["claudeFallback"] == 123456, diagnostic)
        require(diagnostic["explicitShortcut"] is False, diagnostic)
        require(diagnostic["preloadEnvPresent"] is False, diagnostic)
        require(diagnostic["childExitCode"] == 0, diagnostic)
        require(diagnostic["childStdout"] == "2.1.220 (Claude Code)", diagnostic)
        require(diagnostic["childStderr"] == "", diagnostic)
        tests.append(("real default policies and child cleanup", json.dumps(diagnostic)))

        relative_user = run(
            [
                str(link),
                "--renderpatch-extension",
                "relative-user-extension.mjs",
                "--renderpatch-diagnose",
            ],
            timeout=60.0,
        )
        require(relative_user.returncode == 2, relative_user.stdout)
        require("requires an absolute path" in relative_user.stdout, relative_user.stdout)
        require("RENDERPATCH_CANDIDATE_DIAGNOSTIC" not in relative_user.stdout, relative_user.stdout)

        rejected_user_cases = (
            (
                "outside-home user extension",
                str(outside_module),
                "User module must live under the current user's home",
                "OUTSIDE_USER_RAN",
            ),
            (
                "symlink user extension",
                str(symlink_module),
                "User module path component must not be a symlink",
                "USER_EXTENSION",
            ),
            (
                "throwing user extension",
                str(throwing_module),
                "intentional user extension failure",
                None,
            ),
        )
        for label, module_path, expected_error, forbidden_output in rejected_user_cases:
            rejected_user_output = success(
                label,
                run(
                    [
                        str(link),
                        "--renderpatch-extension",
                        module_path,
                        "--renderpatch-diagnose",
                    ],
                    timeout=300.0,
                ),
            )
            rejected_diagnostic = json_line(
                rejected_user_output, "RENDERPATCH_CANDIDATE_DIAGNOSTIC "
            )
            require(rejected_diagnostic["messageTranscript"] == 3, rejected_diagnostic)
            require("user module was skipped" in rejected_user_output, rejected_user_output)
            require(expected_error in rejected_user_output, rejected_user_output)
            if forbidden_output is not None:
                require(forbidden_output not in rejected_user_output, rejected_user_output)
            if label == "throwing user extension":
                require("THROWING_USER_DEFAULT 3" in rejected_user_output, rejected_user_output)
        tests.append(("untrusted and throwing user extensions fail open", "four cases"))

        foreign_link = fixture / "foreign" / "claude-renderpatch-candidate"
        foreign_link.parent.mkdir()
        foreign_link.write_text("do not replace\n", encoding="utf-8")
        conflict_env = {**install_env, "CLAUDE_RENDERPATCH_LINK": str(foreign_link)}
        conflict = run([str(INSTALLER)], env=conflict_env, timeout=60.0)
        require(conflict.returncode != 0, conflict.stdout)
        require("refusing to replace non-symlink launcher" in conflict.stdout, conflict.stdout)
        require(foreign_link.read_text(encoding="utf-8") == "do not replace\n", foreign_link)
        tests.append(("foreign link conflict refusal", str(foreign_link)))

        release.chmod(0o755)
        release_manifest_path.chmod(0o644)
        release_manifest_path.write_text("{}\n", encoding="utf-8")
        release_manifest_path.chmod(0o444)
        release.chmod(0o555)
        bad_release = run([str(link), "--renderpatch-status"], timeout=60.0)
        require(bad_release.returncode != 0, bad_release.stdout)
        require("release manifest SHA-256 mismatch" in bad_release.stdout, bad_release.stdout)
        release.chmod(0o755)
        release_manifest_path.chmod(0o644)
        release_manifest_path.write_bytes(
            (REPO_ROOT / "candidate/release-manifest.json").read_bytes()
        )
        release_manifest_path.chmod(0o444)
        release.chmod(0o555)
        success(
            "release repair verification",
            run([str(INSTALLER), "--verify"], env=install_env, timeout=300.0),
        )
        tests.append(("wrong release manifest hash refused", "then repaired"))

        release.chmod(0o755)
        unmanaged = release / "unmanaged.txt"
        unmanaged.write_text("must block uninstall\n", encoding="utf-8")
        release.chmod(0o555)
        protected_uninstall = run(
            [str(INSTALLER), "--uninstall"], env=install_env, timeout=60.0
        )
        require(protected_uninstall.returncode != 0, protected_uninstall.stdout)
        require("unexpected entries" in protected_uninstall.stdout, protected_uninstall.stdout)
        require(unmanaged.exists(), unmanaged)
        require(link.is_symlink(), link)
        release.chmod(0o755)
        success("trash unmanaged fixture", run(["trash", str(unmanaged)]))
        release.chmod(0o555)
        tests.append(("unmanaged uninstall protection", "refused before cleanup"))

        uninstall_output = success(
            "managed uninstall",
            run([str(INSTALLER), "--uninstall"], env=install_env, timeout=300.0),
        )
        require("Removed immutable Claude renderpatch candidate" in uninstall_output, uninstall_output)
        require(not release.exists(), release)
        require(not link.exists() and not link.is_symlink(), link)
        tests.append(("managed trash uninstall", "ok"))

        after = {str(path): snapshot(path) for path in PRESERVED_PATHS}
        require(after == before, {"before": before, "after": after})
        tests.append(("existing Claude files preserved byte-for-byte", "ok"))

        print(f"installer: {INSTALLER}")
        print(f"fixture: {fixture}\n")
        for label, detail in tests:
            print(f"PASS {label}: {detail}")
        print("\nAll immutable candidate launcher checks passed.")
        return 0
    finally:
        if fixture.exists():
            make_writable(fixture)
            subprocess.run(["trash", str(fixture)], check=False)
        if outside_module.exists():
            subprocess.run(["trash", str(outside_module)], check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
