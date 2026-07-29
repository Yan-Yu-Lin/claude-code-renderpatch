#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify the zero-patch Bun preload launcher against stock Claude Code candidates.

The harness never edits an installed Claude binary or settings file. It exercises latest
numeric selection, pre-CLI execution, shared-global interception, Bun/Node APIs, registry
failure handling, environment cleanup, trust rejection, and the safe bypass path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WRAPPER = REPO_ROOT / "preload" / "claude-preload-lab"
EXAMPLES = REPO_ROOT / "preload" / "examples"
SCRUB_ENV = {
    "BUN_OPTIONS",
    "CLAUDE_RENDERPATCH_ACTIVE",
    "CLAUDE_RENDERPATCH_MODULE",
    "CLAUDE_RENDERPATCH_TARGET",
    "CLAUDE_PRELOAD_BOOTSTRAP",
    "CLAUDE_PRELOAD_INSTALL_DIR",
    "CLAUDE_PRELOAD_LINK",
    "CLAUDE_PRELOAD_TARGET",
    "CLAUDE_PRELOAD_VERSIONS_DIR",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", type=Path, default=DEFAULT_WRAPPER)
    parser.add_argument(
        "--versions-dir",
        type=Path,
        default=Path.home() / ".local/share/claude/versions",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def require(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(str(message))


def numeric_version(name: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+(?:\.\d+)*", name):
        return None
    return tuple(int(part) for part in name.split("."))


def newest_installed(versions_dir: Path) -> Path:
    candidates: list[tuple[tuple[int, ...], Path]] = []
    for path in versions_dir.expanduser().resolve().iterdir():
        version = numeric_version(path.name)
        if (
            version is None
            or path.is_symlink()
            or not path.is_file()
            or not os.access(path, os.X_OK)
        ):
            continue
        candidates.append((version, path))
    if not candidates:
        raise RuntimeError(f"No executable numeric versions found in {versions_dir}")
    return max(candidates)[1]


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float,
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


def require_success(label: str, result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode != 0:
        raise AssertionError(
            f"{label} failed with exit {result.returncode}:\n{result.stdout}"
        )
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


def write_fake_version(path: Path, version: str) -> None:
    path.write_text(f'#!/bin/sh\nprintf "%s\\n" "{version} (Claude Code)"\n')
    path.chmod(0o700)


def main() -> int:
    args = parse_args()
    wrapper = args.wrapper.expanduser().resolve()
    versions_dir = args.versions_dir.expanduser().resolve()
    expected_target = newest_installed(versions_dir)
    base_env = {"CLAUDE_PRELOAD_VERSIONS_DIR": str(versions_dir)}
    tests: list[tuple[str, str]] = []

    help_output = require_success(
        "help without an installation",
        run(
            [str(wrapper), "--renderpatch-help"],
            env={"CLAUDE_PRELOAD_VERSIONS_DIR": "/nonexistent/claude-versions"},
            timeout=args.timeout,
        ),
    )
    require("Usage:" in help_output, help_output)
    tests.append(("help independent of Claude install", "ok"))

    with tempfile.TemporaryDirectory(
        prefix="claude-preload-resolution-", dir=Path.home()
    ) as temporary:
        fixture = Path(temporary)
        write_fake_version(fixture / "2.1.9", "2.1.9")
        write_fake_version(fixture / "2.1.10", "2.1.10")
        write_fake_version(fixture / "not-a-version", "99.0.0")
        write_fake_version(fixture / "9.9.9-real", "9.9.9")
        (fixture / "9.9.9").symlink_to(fixture / "9.9.9-real")
        (fixture / "3.0.0").write_text("not executable\n")
        fixture_status = require_success(
            "synthetic numeric resolution",
            run(
                [str(wrapper), "--renderpatch-status"],
                env={"CLAUDE_PRELOAD_VERSIONS_DIR": str(fixture)},
                timeout=args.timeout,
            ),
        )
        selected_fixture = status_values(fixture_status)["target"]
        require(Path(selected_fixture).name == "2.1.10", fixture_status)
    tests.append(("independent numeric resolution fixture", "2.1.10"))

    status = require_success(
        "status",
        run([str(wrapper), "--renderpatch-status"], env=base_env, timeout=args.timeout),
    )
    status_data = status_values(status)
    actual_target = Path(status_data.get("target", "")).resolve()
    require(actual_target == expected_target, status)
    clean_version = status_data.get("reported_version", "")
    require(expected_target.name in clean_version, status)
    tests.append(("latest installed candidate", str(actual_target)))

    hostile_status = require_success(
        "status ignores ambient preload",
        run(
            [str(wrapper), "--renderpatch-status"],
            env={
                **base_env,
                "BUN_OPTIONS": f"--preload={EXAMPLES / 'console-prefix.mjs'}",
            },
            timeout=args.timeout,
        ),
    )
    require("PRELOAD_LAB" not in hostile_status, hostile_status)
    require(status_values(hostile_status)["reported_version"] == clean_version, hostile_status)
    tests.append(("status scrubs ambient preload", clean_version))

    clean_output = require_success(
        "quiet bootstrap",
        run([str(wrapper), "--version"], env=base_env, timeout=args.timeout),
    ).strip()
    require(clean_output == clean_version, clean_output)
    tests.append(("quiet bootstrap", clean_output))

    console_output = require_success(
        "shared global console interception",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "console-prefix.mjs"),
            },
            timeout=args.timeout,
        ),
    ).strip()
    require(console_output == f"PRELOAD_LAB {clean_version}", console_output)
    tests.append(("shared global interception", console_output))

    argv_output = require_success(
        "pre-parse argv mutation",
        run(
            [str(wrapper)],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "argv-version.mjs"),
            },
            timeout=args.timeout,
        ),
    ).strip()
    require(argv_output == clean_version, argv_output)
    tests.append(("runs before CLI parsing", argv_output))

    api_output = require_success(
        "Bun and Node API probe",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "api-probe.mjs"),
            },
            timeout=args.timeout,
        ),
    )
    api = json_line(api_output, "PRELOAD_API ")
    for field in ("bunFile", "require", "nodeFs", "nodePath"):
        require(api[field] == "function", api)
    require(api["importMetaUrl"] == "string", api)
    require(api["bunOptionsPresent"] is False, api)
    require(api["activePresent"] is False, api)
    require(api["targetPresent"] is False, api)
    require(api["runtimeApiVersion"] == 1, api)
    require(Path(str(api["execPath"])).resolve() == expected_target, api)
    tests.append(("Bun/Node APIs and one-shot env cleanup", json.dumps(api)))

    registry_output = require_success(
        "registry semantics",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "registry-probe.mjs"),
            },
            timeout=args.timeout,
        ),
    )
    registry = json_line(registry_output, "REGISTRY_API ")
    require(registry["replacement"] == 2, registry)
    require(registry["staleDisposer"] is False, registry)
    require(registry["afterStaleDisposer"] == 2, registry)
    require(registry["syncError"] is None, registry)
    require(registry["asyncError"] is None, registry)
    require(registry["runtimeFrozen"] is True, registry)
    require(registry["processMetadataFrozen"] is True, registry)
    require(registry["apiVersion"] == 1, registry)
    require("intentional sync hook error" in registry_output, registry_output)
    require("intentional async hook error" in registry_output, registry_output)
    tests.append(("registry replacement/freeze/sync+async failure", json.dumps(registry)))

    child_output = require_success(
        "child environment cleanup",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "child-env-probe.mjs"),
            },
            timeout=args.timeout,
        ),
    )
    child = json_line(child_output, "CHILD_ENV ")
    require(child["exitCode"] == 0, child)
    require(child["bunOptionsPresent"] is False, child)
    require(child["activePresent"] is False, child)
    require(child["targetPresent"] is False, child)
    require(child["childStdout"] == clean_version, child)
    require(child["childStderr"] == "", child)
    tests.append(("real child process has no preload state", json.dumps(child)))

    throwing_output = require_success(
        "throwing extension fails open",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "throwing.mjs"),
            },
            timeout=args.timeout,
        ),
    )
    require(clean_version in throwing_output, throwing_output)
    require("intentional preload extension failure" in throwing_output, throwing_output)
    tests.append(("thrown/rejected extension import fails open", clean_version))

    with tempfile.TemporaryDirectory(
        prefix="claude-preload-untrusted-", dir="/private/tmp"
    ) as temporary:
        untrusted = Path(temporary) / "untrusted.mjs"
        untrusted.write_text('console.log("UNTRUSTED_MODULE_RAN")\n', encoding="utf-8")
        untrusted_output = require_success(
            "untrusted extension rejected",
            run(
                [str(wrapper), "--version"],
                env={
                    **base_env,
                    "CLAUDE_RENDERPATCH_MODULE": str(untrusted),
                },
                timeout=args.timeout,
            ),
        )
    require("UNTRUSTED_MODULE_RAN" not in untrusted_output, untrusted_output)
    require("must live under the current user's home" in untrusted_output, untrusted_output)
    require(clean_version in untrusted_output, untrusted_output)
    tests.append(("outside-home external module rejected", str(untrusted)))

    with tempfile.TemporaryDirectory(
        prefix="claude-preload-symlink-", dir=Path.home()
    ) as temporary:
        symlink_fixture = Path(temporary)
        real_dir = symlink_fixture / "real"
        alias_dir = symlink_fixture / "alias"
        real_dir.mkdir()
        alias_dir.symlink_to(real_dir, target_is_directory=True)

        module = real_dir / "probe.mjs"
        module.write_text('console.log("PARENT_SYMLINK_MODULE_RAN")\n', encoding="utf-8")
        module_output = require_success(
            "external module parent symlink rejected",
            run(
                [str(wrapper), "--version"],
                env={
                    **base_env,
                    "CLAUDE_RENDERPATCH_MODULE": str(alias_dir / module.name),
                },
                timeout=args.timeout,
            ),
        )
        require("PARENT_SYMLINK_MODULE_RAN" not in module_output, module_output)
        require("path component must not be a symlink" in module_output, module_output)
        require(clean_version in module_output, module_output)

        bootstrap = real_dir / "bootstrap.mjs"
        bootstrap.write_text(
            (REPO_ROOT / "preload/bootstrap.mjs").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        bootstrap_result = run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_PRELOAD_BOOTSTRAP": str(alias_dir / bootstrap.name),
            },
            timeout=args.timeout,
        )
        require(bootstrap_result.returncode != 0, bootstrap_result.stdout)
        require(
            "path component must not be a symlink" in bootstrap_result.stdout,
            bootstrap_result.stdout,
        )
    tests.append(("parent symlinks rejected", "bootstrap and external module"))

    inherited_options = run(
        [str(wrapper), "--version"],
        env={**base_env, "BUN_OPTIONS": "--smol"},
        timeout=args.timeout,
    )
    require(inherited_options.returncode != 0, inherited_options.stdout)
    require("Refusing inherited BUN_OPTIONS" in inherited_options.stdout, inherited_options.stdout)
    tests.append(("inherited BUN_OPTIONS rejected", "before Claude launch"))

    safe_output = require_success(
        "safe bypass",
        run(
            [str(wrapper), "--renderpatch-safe", "--version"],
            env={
                **base_env,
                "BUN_OPTIONS": "--smol",
                "CLAUDE_PRELOAD_BOOTSTRAP": "/nonexistent/renderpatch-bootstrap.mjs",
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "console-prefix.mjs"),
            },
            timeout=args.timeout,
        ),
    ).strip()
    require(safe_output == clean_version, safe_output)
    tests.append(("safe bypass survives missing bootstrap", safe_output))

    print(f"wrapper: {wrapper}")
    print(f"versions: {versions_dir}")
    print(f"selected: {expected_target}\n")
    for label, detail in tests:
        print(f"PASS {label}: {detail}")
    print("\nAll preload launcher checks passed without modifying installed Claude files.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
