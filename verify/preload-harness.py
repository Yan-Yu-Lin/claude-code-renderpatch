#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify the zero-patch Bun preload launcher against stock Claude Code candidates.

The harness never edits an installed Claude binary or settings file. It exercises latest
numeric selection, pre-CLI execution, shared-global interception, Bun/Node APIs, registry and SDK v2 semantics, environment cleanup, trust rejection, and the safe bypass
path.
"""

from __future__ import annotations

import argparse
import hashlib
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
PATCHED_PROTOTYPE = REPO_ROOT / "patched" / "claude-2.1.220-semantic-bridge-prototype"
PATCHED_PROTOTYPE_SHA256 = (
    "6b2198dba56913004ea8d12bdfe9cd753c3b9a079681ff136285d6e2fa7c5a49"
)
BRIDGE_BUILD_ID = "internal-sdk-2.1.220.1"
SCRUB_ENV = {
    "BUN_OPTIONS",
    "CLAUDE_RENDERPATCH_ACTIVE",
    "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
    "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
    "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
    "CLAUDE_RENDERPATCH_MODULE",
    "CLAUDE_RENDERPATCH_TARGET",
    "CLAUDE_RENDERPATCH_USER_MODULE",
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


def installed_versions(versions_dir: Path) -> list[Path]:
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
    return [path for _, path in sorted(candidates)]


def newest_installed(versions_dir: Path) -> Path:
    candidates = installed_versions(versions_dir)
    if not candidates:
        raise RuntimeError(f"No executable numeric versions found in {versions_dir}")
    return candidates[-1]


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


def write_env_fake_version(path: Path, version: str) -> None:
    names = (
        "BUN_OPTIONS",
        "CLAUDE_RENDERPATCH_ACTIVE",
        "CLAUDE_RENDERPATCH_MODULE",
        "CLAUDE_RENDERPATCH_USER_MODULE",
        "CLAUDE_RENDERPATCH_TARGET",
        "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
        "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
        "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
    )
    checks = "\n".join(
        f'if [ "${{{name}+present}}" = present ]; then printf "FAKE_ENV {name}\\n"; fi'
        for name in names
    )
    path.write_text(
        f'#!/bin/sh\n{checks}\nprintf "%s\\n" "{version} (Claude Code)"\n'
    )
    path.chmod(0o700)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    wrapper = args.wrapper.expanduser().resolve()
    versions_dir = args.versions_dir.expanduser().resolve()
    expected_target = newest_installed(versions_dir)
    base_env = {"CLAUDE_PRELOAD_VERSIONS_DIR": str(versions_dir)}
    require(PATCHED_PROTOTYPE.is_file(), f"Missing patched prototype: {PATCHED_PROTOTYPE}")
    require(os.access(PATCHED_PROTOTYPE, os.X_OK), "Patched prototype is not executable")
    require(sha256(PATCHED_PROTOTYPE) == PATCHED_PROTOTYPE_SHA256, "Patched prototype SHA mismatch")
    signed_preload_env = {
        "BUN_OPTIONS": f"--preload={REPO_ROOT / 'preload/bootstrap.mjs'}",
        "CLAUDE_RENDERPATCH_ACTIVE": "1",
        "CLAUDE_RENDERPATCH_TARGET": str(PATCHED_PROTOTYPE),
        "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID": BRIDGE_BUILD_ID,
        "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256": PATCHED_PROTOTYPE_SHA256,
        "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION": "2.1.220",
    }
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

    with tempfile.TemporaryDirectory(
        prefix="claude-preload-env-target-", dir=Path.home()
    ) as temporary:
        env_fixture = Path(temporary)
        fake_target = env_fixture / "9.9.9"
        write_env_fake_version(fake_target, "9.9.9")
        fake_base = {"CLAUDE_PRELOAD_TARGET": str(fake_target)}
        fake_hostile = {
            "BUN_OPTIONS": "--smol",
            "CLAUDE_RENDERPATCH_ACTIVE": "hostile",
            "CLAUDE_RENDERPATCH_USER_MODULE": "/hostile-user.mjs",
            "CLAUDE_RENDERPATCH_TARGET": "/hostile-target",
            "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID": "hostile-build",
            "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256": "0" * 64,
            "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION": "0.0.0",
        }
        fake_status = require_success(
            "fake target status scrub",
            run(
                [str(wrapper), "--renderpatch-status"],
                env={**fake_base, **fake_hostile},
                timeout=args.timeout,
            ),
        )
        require("FAKE_ENV" not in fake_status, fake_status)
        fake_safe = require_success(
            "fake target safe scrub",
            run(
                [str(wrapper), "--renderpatch-safe", "--version"],
                env={**fake_base, **fake_hostile},
                timeout=args.timeout,
            ),
        )
        require(fake_safe.strip() == "9.9.9 (Claude Code)", fake_safe)
        for name, value in fake_hostile.items():
            rejected = run(
                [str(wrapper), "--version"],
                env={**fake_base, name: value},
                timeout=args.timeout,
            )
            require(rejected.returncode != 0, rejected.stdout)
            require(f"Refusing inherited {name}" in rejected.stdout, rejected.stdout)
            require("FAKE_ENV" not in rejected.stdout, rejected.stdout)
    tests.append(("low-level launcher scrubs/rejects bridge and user env", "fake target"))

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
    require(api["bridgeBuildPresent"] is False, api)
    require(api["bridgeArtifactShaPresent"] is False, api)
    require(api["bridgeTargetVersionPresent"] is False, api)
    require(api["userModulePresent"] is False, api)
    require(api["registryApiVersion"] == 1, api)
    require(api["runtimeApiVersion"] == 2, api)
    require(api["policyApiVersion"] == 2, api)
    require(api["bridgeAbi"] == 1, api)
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

    sdk_output = require_success(
        "runtime SDK v2 probe",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_RENDERPATCH_MODULE": str(EXAMPLES / "sdk-v2-probe.mjs"),
            },
            timeout=max(args.timeout, 60.0),
        ),
    )
    sdk = json_line(sdk_output, "SDK_V2 ")
    alias = sdk["alias"]
    require(alias["keys"] == ["c", "q"], alias)
    require(alias["enumerable"] is False, alias)
    require(alias["writable"] is False, alias)
    require(alias["configurable"] is False, alias)
    require(alias["frozen"] is True, alias)
    require(alias["sameAsRuntimeBridge"] is True, alias)

    versions = sdk["versions"]
    require(versions["registryApi"] == 1, versions)
    require(versions["runtimeApi"] == 2, versions)
    require(versions["policyApi"] == 2, versions)
    require(versions["bridgeAbi"] == 1, versions)
    require(versions["bridgeBuildId"] == "internal-sdk-2.1.220.1", versions)
    require(versions["rawSlotApi"] == "2.1.220.1", versions)
    stock_verification = sdk["stockVerification"]
    require(stock_verification["verificationMode"] == "stock-lab", stock_verification)
    require(stock_verification["artifactVerified"] is False, stock_verification)

    fallbacks = sdk["fallbacks"]
    require(fallbacks["missingIdentity"] is True, fallbacks)
    for field, expected in {
        "missing": 81,
        "thrown": 82,
        "promise": 83,
        "rejectedPromise": 831,
        "thenable": 84,
        "throwingThenGetter": 85,
        "undefined": 86,
        "wrongType": 87,
        "belowRange": 88,
        "aboveRange": 89,
        "badPayload": 90,
    }.items():
        require(fallbacks[field] == expected, fallbacks)

    sentinels = sdk["validSentinels"]
    require(sentinels == {"zero": 0, "falseReset": False, "falseToggle": False}, sentinels)
    transactions = sdk["transactions"]
    for field in (
        "incompleteRejected",
        "aliasDuplicateRejected",
        "ownershipRejected",
        "asyncRejected",
    ):
        require(transactions[field] is True, transactions)
    require(transactions["inactiveAfterReject"] == 17, transactions)

    unsafe_denied = sdk["unsafeDenied"]
    require(
        unsafe_denied
        == {
            "bridgeBuild": True,
            "rawSlotApi": True,
            "target": True,
            "bridgeAbi": True,
            "captureAbi": True,
        },
        unsafe_denied,
    )
    require(sdk["unsafeExact"] is False, sdk)
    require(sdk["captureReturnIgnored"] is True, sdk)
    require(sdk["staticCapturePreserved"] is True, sdk)
    capture = sdk["capture"]
    require(capture["firstGeneration"] == 1, capture)
    require(capture["firstBitmap"] == 273, capture)
    require(capture["afterStaleGeneration"] == 2, capture)
    require(capture["afterStaleBitmap"] == 273, capture)
    require(capture["safeReplacementVisible"] is True, capture)
    require(capture["snapshotRawCount"] == 2, capture)
    require(capture["snapshotRenderedCount"] == 3, capture)
    require(capture["exportAvailable"] is True, capture)
    require(capture["exportSummaryCount"] == 3, capture)
    require(capture["exportContainsContent"] is False, capture)
    require(capture["searchMatchCount"] == 2, capture)
    require(capture["statusContainsRaw"] is False, capture)
    require(capture["cleared"] is True, capture)
    require(capture["captureDomainCount"] == 6, capture)

    actions = sdk["actions"]
    require("repl.showAll" in actions["listed"], actions)
    require("msg.search" in actions["listed"], actions)
    require(actions["stale"]["ok"] is False and actions["stale"]["reason"] == "stale", actions)
    require(actions["valid"]["ok"] is True, actions)
    require(actions["invalid"]["ok"] is False and actions["invalid"]["reason"] == "invalid", actions)
    require(actions["toggle"]["ok"] is True, actions)
    require(actions["redraw"]["ok"] is True, actions)
    require(actions["value"] is True, actions)
    require(actions["toggleValue"] is True, actions)
    require(actions["redrawValue"] is True, actions)
    require(actions["currentViewType"] == "object", actions)
    require(actions["currentViewFields"]["id"] == "main", actions)
    require(actions["commandCount"] == 1, actions)

    safe_facades = sdk["safeFacades"]
    require(safe_facades["mc"]["canonical"] == "first", safe_facades)
    require(safe_facades["mc"]["provider"] == "proxy", safe_facades)
    require(safe_facades["mc"]["window"] == 200000, safe_facades)
    require(safe_facades["mc"]["catalogContainsSecret"] is False, safe_facades)
    require(safe_facades["sr"]["canonicalRequested"] == "first", safe_facades)
    require(safe_facades["app"]["available"] is True, safe_facades)
    require(safe_facades["app"]["taskCount"] == 1, safe_facades)
    require(safe_facades["app"]["containsPrompt"] is False, safe_facades)
    require(safe_facades["app"]["subscriptionOk"] is True, safe_facades)
    require(safe_facades["app"]["observed"] is True, safe_facades)
    require(safe_facades["app"]["disposed"] is True, safe_facades)
    require(safe_facades["ink"]["available"] is True, safe_facades)
    require(safe_facades["ink"]["liveInstance"] is True, safe_facades)
    require(safe_facades["ink"]["redrawOk"] is True, safe_facades)
    require(safe_facades["ink"]["invalidateOk"] is True, safe_facades)
    require(safe_facades["key"]["available"] is True, safe_facades)
    require(safe_facades["key"]["bindingCount"] == 1, safe_facades)
    require(safe_facades["key"]["invokeOk"] is True, safe_facades)
    require(safe_facades["key"]["invoked"] == "ink.redraw", safe_facades)
    require(safe_facades["key"]["registerOk"] is True, safe_facades)
    require(safe_facades["key"]["registered"] == "ink.redraw", safe_facades)
    require(safe_facades["key"]["disposed"] is True, safe_facades)
    require(safe_facades["key"]["observedEvents"] >= 1, safe_facades)
    require(safe_facades["key"]["containsSecret"] is False, safe_facades)
    require(safe_facades["diag"]["available"] is True, safe_facades)
    require(safe_facades["diag"]["logFile"] == "debug.log", safe_facades)
    require(safe_facades["diag"]["logOk"] is True, safe_facades)
    require(safe_facades["diag"]["message"] == "[renderpatch-extension] diagnostic message", safe_facades)

    policies = sdk["defaultPolicies"]
    require(policies["messageTranscript"] == 3, policies)
    require(policies["messageRepl"] == 2, policies)
    require(policies["resetClassic"] is True, policies)
    require(policies["resetAltScreen"] is False, policies)
    require(policies["toggleEnter"] is True, policies)
    require(policies["toggleLeave"] is False, policies)
    require(policies["kimiWindow"] == 262144, policies)
    require(policies["otherWindow"] == 372000, policies)
    require(policies["claudeFallback"] == 123456, policies)
    require(policies["explicitShortcut"] is False, policies)
    require(sdk["statusFrozen"] is True, sdk)
    require(sdk["runtimeFrozen"] is True, sdk)
    tests.append(("runtime/policy/capture/action SDK v2", json.dumps(sdk)))

    patched_output = require_success(
        "signed patched candidate metadata",
        run(
            [str(PATCHED_PROTOTYPE), "--version"],
            env={
                **signed_preload_env,
                "CLAUDE_RENDERPATCH_MODULE": str(
                    EXAMPLES / "patched-candidate-probe.mjs"
                ),
            },
            timeout=max(args.timeout, 60.0),
        ),
    )
    patched = json_line(patched_output, "PATCHED_CANDIDATE ")
    require(patched["query"] == 372000, patched)
    require(patched["captureGeneration"] == 91, patched)
    require(patched["unsafeArtifactMismatchDenied"] is True, patched)
    require(patched["unsafeEnabled"] is True, patched)
    require(patched["unsafeGeneration"] == 91, patched)
    require(patched["bridgeActive"] is True, patched)
    require(patched["verificationMode"] == "signed-bridge-artifact", patched)
    require(patched["artifactVerified"] is True, patched)
    require(patched["bridgeMetadataPresent"] is True, patched)
    require(patched["buildEnvPresent"] is False, patched)
    require(patched["shaEnvPresent"] is False, patched)
    require(patched["versionEnvPresent"] is False, patched)
    tests.append(("signed patched candidate bridge activation", json.dumps(patched)))

    for label, metadata_override in (
        (
            "wrong signed artifact SHA",
            {"CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256": "0" * 64},
        ),
        (
            "wrong bridge build ID",
            {"CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID": "wrong-bridge-build"},
        ),
    ):
        rejected_output = require_success(
            label,
            run(
                [str(PATCHED_PROTOTYPE), "--version"],
                env={
                    **signed_preload_env,
                    **metadata_override,
                    "CLAUDE_RENDERPATCH_MODULE": str(
                        EXAMPLES / "target-mismatch-probe.mjs"
                    ),
                },
                timeout=max(args.timeout, 60.0),
            ),
        )
        rejected = json_line(rejected_output, "TARGET_MISMATCH ")
        require(rejected["fallback"] == 91, rejected)
        require(rejected["captureAvailable"] is False, rejected)
        require(rejected["bridgeActive"] is False, rejected)
        require(rejected["exactVersion"] is True, rejected)
        require(rejected["verificationMode"] is None, rejected)
        require(rejected["artifactVerified"] is False, rejected)
        require(rejected["bridgeMetadataPresent"] is True, rejected)
        tests.append((f"{label} disables bridge", json.dumps(rejected)))

    collision_output = require_success(
        "protected alias collision",
        run(
            [str(wrapper), "--version"],
            env={
                **base_env,
                "CLAUDE_PRELOAD_BOOTSTRAP": str(
                    EXAMPLES / "alias-collision-bootstrap.mjs"
                ),
            },
            timeout=args.timeout,
        ),
    )
    collision = json_line(collision_output, "ALIAS_COLLISION ")
    require(collision["preserved"] is True, collision)
    require(collision["result"] == "occupied", collision)
    require(collision["active"] is False, collision)
    require(collision["collision"] is True, collision)
    tests.append(("protected alias collision disables bridge", json.dumps(collision)))

    mismatch_target = next(
        (
            path
            for path in reversed(installed_versions(versions_dir))
            if path.name != "2.1.220"
        ),
        None,
    )
    require(mismatch_target is not None, "An older Claude version is required")
    mismatch_output = require_success(
        "exact target negotiation",
        run(
            [str(wrapper), "--version"],
            env={
                "CLAUDE_PRELOAD_TARGET": str(mismatch_target),
                "CLAUDE_RENDERPATCH_MODULE": str(
                    EXAMPLES / "target-mismatch-probe.mjs"
                ),
            },
            timeout=args.timeout,
        ),
    )
    mismatch = json_line(mismatch_output, "TARGET_MISMATCH ")
    require(mismatch["fallback"] == 91, mismatch)
    require(mismatch["captureAvailable"] is False, mismatch)
    require(mismatch["bridgeActive"] is False, mismatch)
    require(mismatch["exactVersion"] is False, mismatch)
    require(mismatch["verificationMode"] is None, mismatch)
    require(mismatch["artifactVerified"] is False, mismatch)
    require(mismatch["bridgeMetadataPresent"] is False, mismatch)
    tests.append(("non-target bridge calls fail stock-safe", json.dumps(mismatch)))

    child_output = require_success(
        "child environment cleanup",
        run(
            [str(PATCHED_PROTOTYPE), "--version"],
            env={
                **signed_preload_env,
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
    require(child["bridgeBuildPresent"] is False, child)
    require(child["bridgeArtifactShaPresent"] is False, child)
    require(child["bridgeTargetVersionPresent"] is False, child)
    require(child["userModulePresent"] is False, child)
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
