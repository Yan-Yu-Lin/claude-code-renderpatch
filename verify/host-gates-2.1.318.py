#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Repeatable non-render gates for a Claude Code 2.1.318 host release.

The default run covers immutable status/basic controls, four live model slots and
/context, S1/S2 routing against child-owned JSONL in candidate/safe/stock,
official Mods in candidate/safe/stock, launcher exec, isolated-HOME model
restoration, real Bash and MCP child isolation, and tamper refusal.
"""

import argparse
import fcntl
import hashlib
import json
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import uuid
from pathlib import Path

HOME = Path.home()
ANSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-Za-z]")
PRELOAD_NAMES = (
    "BUN_OPTIONS",
    "RP_HOST_ENTRY",
    "CLAUDE_RENDERPATCH_ACTIVE",
    "CLAUDE_RENDERPATCH_MODULE",
    "CLAUDE_RENDERPATCH_USER_MODULE",
    "CLAUDE_RENDERPATCH_TARGET",
    "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
    "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
    "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
    "CLAUDE_PRELOAD_TARGET",
    "CLAUDE_PRELOAD_VERSIONS_DIR",
    "CLAUDE_PRELOAD_BOOTSTRAP",
)
REQUIRED_BAKED_IN = {
    "full-redraw",
    "explicit-subagent-model-routing",
    "resumable-stopped-agents",
    "teammate-transcript-view",
    "teammate-background-work",
}
MOD_MARKER = "RENDERPATCH_MOD_2_1_318"


def clean_env(extra=None, *, home=None):
    rejected = {
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_EXECPATH",
        "ENABLE_TOOL_SEARCH",
        "CLAUDE_CODE_FORK_SUBAGENT",
    }
    env = {key: value for key, value in os.environ.items() if key not in rejected}
    env["TERM"] = "xterm-256color"
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["UV_CACHE_DIR"] = "/Volumes/111360128 Lin Yan Yu/DevCache/uv"
    if home is not None:
        env["HOME"] = str(home)
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def project_dir(cwd, *, home=HOME):
    return home / ".claude/projects" / str(cwd).replace("/", "-").replace(".", "-")


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def trash_path(path):
    if path.exists() or path.is_symlink():
        subprocess.run(["trash", str(path)], check=True)


def run(argv, label, out, cwd, *, env=None, timeout=300):
    started = time.time()
    proc = subprocess.run(
        [str(value) for value in argv],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env or clean_env(),
        timeout=timeout,
    )
    record = {
        "label": label,
        "argv": [str(value) for value in argv],
        "returncode": proc.returncode,
        "seconds": round(time.time() - started, 3),
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-6000:],
    }
    write_json(out / f"{label}.json", record)
    return record


class Pty:
    def __init__(self, argv, cwd, env, cols=120, rows=40):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.proc = subprocess.Popen(
            [str(value) for value in argv],
            cwd=cwd,
            env=env,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
        os.close(slave)
        self.data = bytearray()

    def read(self, seconds, until=None):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            readable, _, _ = select.select([self.master], [], [], 0.2)
            if readable:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.data.extend(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(self.master, b"\x1b[1;1R")
                if b"\x1b[c" in chunk:
                    os.write(self.master, b"\x1b[?62;22c")
            if until and until in self.text():
                return True
            if self.proc.poll() is not None:
                break
        return until is None

    def text(self):
        return ANSI.sub(b"", bytes(self.data)).decode(errors="replace")

    def submit(self, text, wait=1.0):
        os.write(self.master, text.encode())
        self.read(wait)
        os.write(self.master, b"\r")

    def finish(self):
        for wait_seconds in (0.5, 1.5):
            if self.proc.poll() is not None:
                break
            try:
                os.write(self.master, b"\x03")
            except OSError:
                break
            self.read(wait_seconds)
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait()
        os.close(self.master)
        return self.proc.returncode


def mode_prefix(args, mode, *, plugin_test=False, settings=True):
    if mode == "candidate":
        return [args.launcher]
    if mode == "safe":
        return [args.launcher, "--renderpatch-safe"]
    prefix = [args.stock]
    if settings and not plugin_test:
        prefix += ["--settings", args.overlay]
    return prefix


def parse_single_json(stdout):
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("stdout contained no JSON")
    return json.loads(lines[-1])


def child_models(transcript):
    models = []
    lines = []
    markers = []
    for number, line in enumerate(transcript.open(), 1):
        record = json.loads(line)
        if record.get("type") == "assistant":
            model = (record.get("message") or {}).get("model")
            if model:
                models.append(model)
                lines.append(number)
            content = (record.get("message") or {}).get("content") or []
            if isinstance(content, list):
                markers.extend(block.get("text", "") for block in content if isinstance(block, dict))
    return sorted(set(models)), lines, "\n".join(markers)

def stream_assistant_text(stdout):
    texts = []
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") == "assistant":
            content = (record.get("message") or {}).get("content") or []
            if isinstance(content, list):
                texts.extend(block.get("text", "") for block in content if isinstance(block, dict))
        if record.get("type") == "result" and isinstance(record.get("result"), str):
            texts.append(record["result"])
    return "\n".join(texts)

def transcript_tool_result_text(transcript):
    texts = []
    for line in transcript.read_text().splitlines():
        record = json.loads(line)
        message = record.get("message") or {}
        if message.get("role") != "user":
            continue
        content = message.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            value = block.get("content")
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, list):
                texts.extend(
                    item.get("text", "") for item in value
                    if isinstance(item, dict) and item.get("type") == "text"
                )
    return "\n".join(texts)


def gate_basic(args, out):
    status = run([args.launcher, "--renderpatch-status"], "status", out, args.cwd)
    status_fields = {}
    for line in status["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            status_fields[key] = value
    baked = set(filter(None, status_fields.get("baked_in", "").split(",")))
    versions = {}
    invalid = {}
    prints = {}
    for mode in ("candidate", "safe", "stock"):
        version_argv = mode_prefix(args, mode, settings=False) + ["--version"]
        version = run(version_argv, f"version-{mode}", out, args.cwd)
        version_lines = [line for line in version["stdout"].splitlines() if line.strip()]
        versions[mode] = {
            "returncode": version["returncode"],
            "lines": version_lines,
            "exact": len(version_lines) == 1 and version_lines[0].startswith("2.1.318 "),
        }
        bad = run(mode_prefix(args, mode, settings=False) + ["--definitely-not-a-real-option"], f"invalid-{mode}", out, args.cwd)
        invalid[mode] = {"returncode": bad["returncode"], "stderr": bad["stderr"][-1000:]}
        marker = f"HOST_BASIC_{mode.upper()}_318_OK"
        live = run(
            mode_prefix(args, mode) + [
                "--permission-mode", "default",
                "--strict-mcp-config",
                "--tools", "",
                "--output-format", "json",
                "-p", f"Reply exactly {marker}.",
            ],
            f"print-{mode}",
            out,
            args.cwd,
            timeout=400,
        )
        try:
            payload = parse_single_json(live["stdout"])
        except Exception:
            payload = {}
        prints[mode] = {
            "returncode": live["returncode"],
            "result": payload.get("result"),
            "pass": live["returncode"] == 0 and payload.get("result", "").strip() == marker,
        }
    summary = {
        "status": status_fields,
        "missingBakedIn": sorted(REQUIRED_BAKED_IN - baked),
        "versions": versions,
        "invalid": invalid,
        "print": prints,
    }
    summary["pass"] = (
        status["returncode"] == 0
        and status_fields.get("target_version") == "2.1.318"
        and status_fields.get("verification") == "ok"
        and not summary["missingBakedIn"]
        and all(item["returncode"] == 0 and item["exact"] for item in versions.values())
        and all(item["returncode"] != 0 for item in invalid.values())
        and all(item["pass"] for item in prints.values())
    )
    write_json(out / "basic-summary.json", summary)
    return summary


def expected_windows(overlay_env):
    windows = {}
    for slot in ("fable", "opus", "sonnet", "haiku"):
        model = overlay_env[f"ANTHROPIC_DEFAULT_{slot.upper()}_MODEL"]
        if model.endswith("[1m]"):
            windows[slot] = "1m"
        else:
            limit = int(overlay_env.get("CLAUDE_CODE_MAX_CONTEXT_TOKENS", "200000"))
            windows[slot] = f"{limit // 1000}k"
    return windows

def expected_model_usage_key(configured_model):
    base = re.sub(r"\[[^]]+\]$", "", configured_model)
    if re.match(r"^claude-(?:fable|opus|sonnet|haiku)-\d", base):
        return base
    return configured_model


def gate_slots(args, out):
    overlay_env = read_json(args.overlay).get("env") or {}
    slots = {}
    forbidden = re.compile(r"(?:gpt|sol|luna|kimi|k[23])", re.I)
    for slot in ("fable", "opus", "sonnet", "haiku"):
        expected_model = overlay_env.get(f"ANTHROPIC_DEFAULT_{slot.upper()}_MODEL")
        expected_usage_model = expected_model_usage_key(expected_model) if expected_model else None
        marker = f"HOST_SLOT_{slot.upper()}_318_OK"
        record = run(
            [args.launcher,
             "--model", slot,
             "--permission-mode", "default",
             "--strict-mcp-config",
             "--tools", "",
             "--output-format", "json",
             "-p", f"Reply exactly {marker}."],
            f"slot-{slot}",
            out,
            args.cwd,
            timeout=400,
        )
        try:
            payload = parse_single_json(record["stdout"])
        except Exception:
            payload = {}
        models = sorted((payload.get("modelUsage") or {}).keys())
        slots[slot] = {
            "configuredModel": expected_model,
            "expectedModelUsage": expected_usage_model,
            "modelUsage": models,
            "result": payload.get("result"),
            "returncode": record["returncode"],
            "pass": (
                record["returncode"] == 0
                and expected_model is not None
                and models == [expected_usage_model]
                and payload.get("result", "").strip() == marker
                and forbidden.search(expected_model) is None
                and expected_model.startswith("claude-")
            ),
        }
    windows = expected_windows(overlay_env)
    contexts = {}
    for slot, expected in windows.items():
        terminal = Pty([args.launcher, "--model", slot, "--permission-mode", "default"], args.cwd, clean_env())
        terminal.read(12)
        terminal.submit("/context")
        terminal.read(10)
        terminal.submit("/exit")
        terminal.read(5)
        returncode = terminal.finish()
        (out / f"context-{slot}.ansi").write_bytes(bytes(terminal.data))
        matches = re.findall(r"([0-9.]+k)\s*/\s*([0-9.]+[km])\s*tokens\s*\((\d+)%\)", terminal.text(), re.I)
        actual = matches[-1][1].lower() if matches else None
        contexts[slot] = {"expected": expected, "actual": actual, "returncode": returncode, "pass": actual == expected}
    summary = {"slots": slots, "contexts": contexts, "pass": all(v["pass"] for v in slots.values()) and all(v["pass"] for v in contexts.values())}
    write_json(out / "slots-context-summary.json", summary)
    return summary


def gate_routing(args, out):
    overlay_env = read_json(args.overlay).get("env") or {}
    configured = overlay_env["ANTHROPIC_DEFAULT_SONNET_MODEL"]
    expected_candidate = re.sub(r"\[[^]]+\]$", "", configured)
    parent_model = "claude-sonnet-4-6"
    requested_sites = set(args.routing_sites or ("S1", "S2"))
    results = []
    config_dir = out / "routing-config"
    config_dir.mkdir(mode=0o700)
    routing_project_dir = config_dir / "projects" / str(args.cwd).replace("/", "-").replace(".", "-")
    write_json(config_dir / "settings.json", {})
    write_json(config_dir / ".claude.json", {
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "2.1.318",
        "projects": {str(args.cwd): {"hasTrustDialogAccepted": True}},
    })
    routing_env = clean_env({
        "CLAUDE_CONFIG_DIR": config_dir,
        "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
    })
    for mode in ("candidate", "safe", "stock"):
        expected = expected_candidate if mode == "candidate" else parent_model
        prefix = mode_prefix(args, mode)
        if "S1" in requested_sites:
            plain_session = str(uuid.uuid4())
            plain_child_marker = f"S1_CHILD_{mode.upper()}_318_OK"
            plain_parent_marker = f"S1_PARENT_{mode.upper()}_318_OK"
            plain_prompt = (
                'Call Agent exactly once with subagent_type="general-purpose", model="sonnet", '
                f'description="S1 routing collision 318", prompt="Reply exactly {plain_child_marker}. Do not use tools." '
                f"Do not supply name or team_name. Wait for its response, then reply exactly {plain_parent_marker}."
            )
            plain = run(
                prefix + [
                    "--session-id", plain_session,
                    "--model", parent_model,
                    "--permission-mode", "default",
                    "--system-prompt", "Follow this routing gate exactly. Use only the one requested Agent call.",
                    "--tools", "Agent",
                    "--allowedTools", "Agent",
                    "--strict-mcp-config",
                    "--setting-sources", "project,local",
                    "--output-format", "stream-json",
                    "--verbose",
                    "-p", plain_prompt,
                ],
                f"routing-s1-{mode}",
                out,
                args.cwd,
                timeout=500,
                env=routing_env,
            )
            plain_children = sorted((routing_project_dir / plain_session / "subagents").glob("agent-*.jsonl"))
            plain_models, plain_lines, plain_text = child_models(plain_children[0]) if len(plain_children) == 1 else ([], [], "")
            results.append({
                "site": "S1",
                "mode": mode,
                "sessionId": plain_session,
                "expectedModel": expected,
                "actualModels": plain_models,
                "assistantLines": plain_lines,
                "childTranscript": str(plain_children[0]) if len(plain_children) == 1 else None,
                "childCount": len(plain_children),
                "returncode": plain["returncode"],
                "childMarker": plain_child_marker in plain_text,
                "parentMarker": plain_parent_marker in stream_assistant_text(plain["stdout"]),
            })

        if "S2" in requested_sites:
            named_session = str(uuid.uuid4())
            named_child_marker = f"S2_CHILD_{mode.upper()}_318_OK"
            named_parent_marker = f"S2_PARENT_{mode.upper()}_318_OK"
            terminal = Pty(
                prefix + [
                    "--session-id", named_session,
                    "--model", parent_model,
                    "--teammate-mode", "in-process",
                    "--permission-mode", "default",
                    "--system-prompt", "Follow this routing gate exactly. Use only the one requested Agent call.",
                    "--tools", "Agent,SendMessage",
                    "--allowedTools", "Agent,SendMessage",
                    "--strict-mcp-config",
                    "--setting-sources", "project,local",
                ],
                args.cwd,
                clean_env({
                    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
                    "CLAUDE_CONFIG_DIR": config_dir,
                    "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
                    "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN": "1",
                }),
            )
            terminal.read(12)
            terminal.submit(
                'Call Agent exactly once with name="routeprobe", subagent_type="general-purpose", model="sonnet", '
                f'description="S2 named routing collision 318", prompt="Reply exactly {named_child_marker}. Do not use tools." '
                f"Do not omit name. Wait for its result, then reply exactly {named_parent_marker}."
            )
            parent_jsonl = routing_project_dir / f"{named_session}.jsonl"
            deadline = time.monotonic() + 360
            teammate = None
            child_path = None
            parent_text = ""
            spawn_text = ""
            while time.monotonic() < deadline:
                terminal.read(2)
                for meta_path in sorted((routing_project_dir / named_session / "subagents").glob("agent-arouteprobe-*.meta.json")):
                    meta = read_json(meta_path)
                    candidate_path = meta_path.with_name(meta_path.name.removesuffix(".meta.json") + ".jsonl")
                    if (
                        meta.get("taskKind") == "in_process_teammate"
                        and meta.get("name") == "routeprobe"
                        and candidate_path.exists()
                    ):
                        teammate = meta | {"metaPath": str(meta_path)}
                        child_path = candidate_path
                        break
                if parent_jsonl.exists():
                    parent_text = child_models(parent_jsonl)[2]
                    spawn_text = transcript_tool_result_text(parent_jsonl)
                child_text = child_models(child_path)[2] if child_path else ""
                agent_id = child_path.stem.removeprefix("agent-") if child_path else ""
                spawn_ok = (
                    "Spawned successfully." in spawn_text
                    and f"agent_id: {agent_id}" in spawn_text
                    and "name: routeprobe" in spawn_text
                )
                if named_child_marker in child_text and named_parent_marker in parent_text and spawn_ok:
                    break
            if terminal.proc.poll() is None:
                try:
                    terminal.submit("/exit")
                    terminal.read(8)
                except OSError:
                    pass
            returncode = terminal.finish()
            (out / f"routing-s2-{mode}.ansi").write_bytes(bytes(terminal.data))
            named_models, named_lines, named_text = child_models(child_path) if child_path else ([], [], "")
            agent_id = child_path.stem.removeprefix("agent-") if child_path else ""
            spawn_ok = (
                "Spawned successfully." in spawn_text
                and f"agent_id: {agent_id}" in spawn_text
                and "name: routeprobe" in spawn_text
            )
            results.append({
                "site": "S2",
                "mode": mode,
                "sessionId": named_session,
                "expectedModel": expected,
                "actualModels": named_models,
                "assistantLines": named_lines,
                "childTranscript": str(child_path) if child_path else None,
                "childCount": 1 if child_path else 0,
                "returncode": returncode,
                "childMarker": named_child_marker in named_text,
                "parentMarker": named_parent_marker in parent_text,
                "agentId": agent_id or None,
                "spawnResult": spawn_ok,
                "taskKind": teammate.get("taskKind") if teammate else None,
                "teammateName": teammate.get("name") if teammate else None,
                "metaPath": teammate.get("metaPath") if teammate else None,
            })
    for result in results:
        result["pass"] = (
            result["returncode"] == 0
            and result["childCount"] == 1
            and result["actualModels"] == [result["expectedModel"]]
            and result["childMarker"]
            and result["parentMarker"]
            and (
                result["site"] != "S2"
                or (
                    result["agentId"].startswith("arouteprobe-")
                    and result["spawnResult"]
                    and result["taskKind"] == "in_process_teammate"
                    and result["teammateName"] == "routeprobe"
                )
            )
        )
    summary = {
        "parentModel": parent_model,
        "requestedChildAlias": "sonnet",
        "requestedSites": sorted(requested_sites),
        "candidateExpectedModel": expected_candidate,
        "results": results,
        "pass": bool(results) and all(result["pass"] for result in results),
    }
    write_json(out / "routing-summary.json", summary)
    return summary


def gate_mod(args, out):
    fixture = args.repo / "verify/fixtures/mod-2.1.318"
    work = out / "mod-fixture-2.1.318"
    trash_path(work)
    shutil.copytree(fixture, work)
    results = {}
    for mode in ("candidate", "safe", "stock"):
        validate = run(mode_prefix(args, mode) + ["plugin", "validate", work], f"mod-validate-{mode}", out, args.cwd)
        test = run(mode_prefix(args, mode, plugin_test=True, settings=False) + ["plugin", "test", work], f"mod-test-{mode}", out, args.cwd)
        command = run(
            mode_prefix(args, mode) + ["--plugin-dir", work, "--permission-mode", "default", "-p", "/renderpatch-hello"],
            f"mod-command-{mode}", out, args.cwd,
        )
        terminal = Pty(mode_prefix(args, mode) + ["--plugin-dir", work, "--permission-mode", "default"], args.cwd, clean_env())
        terminal.read(12)
        terminal.submit("/plugin")
        terminal.read(7)
        os.write(terminal.master, b"\x1b")
        terminal.read(1)
        terminal.submit("/renderpatch-hello")
        terminal.read(7)
        terminal.submit("/exit")
        terminal.read(5)
        returncode = terminal.finish()
        (out / f"mod-ui-{mode}.ansi").write_bytes(bytes(terminal.data))
        ui = terminal.text()
        pass_fail = re.findall(r"(\d+) pass.*?(\d+) fail", test["stdout"] + test["stderr"], re.S)
        results[mode] = {
            "validate": validate["returncode"],
            "test": test["returncode"],
            "testPassFail": pass_fail[-1] if pass_fail else None,
            "command": command["returncode"] == 0 and MOD_MARKER in command["stdout"],
            "uiExit": returncode,
            "uiCommand": MOD_MARKER in ui,
            "uiPluginActive": bool(re.search(r"1 mod|mod.{0,30}active|renderpatch-mod-fixture", ui, re.I)),
        }
        item = results[mode]
        item["pass"] = (
            item["validate"] == 0
            and item["test"] == 0
            and item["testPassFail"] == ("1", "0")
            and item["command"]
            and item["uiExit"] == 0
            and item["uiCommand"]
            and item["uiPluginActive"]
        )
    summary = {"fixture": str(fixture), "results": results, "pass": all(value["pass"] for value in results.values())}
    write_json(out / "mods-summary.json", summary)
    return summary


def gate_exec(args, out):
    terminal = Pty([args.launcher, "--model", "haiku", "--permission-mode", "default"], args.cwd, clean_env())
    terminal.read(12)
    record = run(["ps", "-ww", "-p", str(terminal.proc.pid), "-o", "pid=,ppid=,comm=,args="], "launcher-exec-ps", out, args.cwd)
    command_line = record["stdout"].strip()
    terminal.submit("/exit")
    terminal.read(5)
    returncode = terminal.finish()
    (out / "launcher-exec.ansi").write_bytes(bytes(terminal.data))
    runtime = str(args.release / "runtime/claude")
    summary = {
        "launcherPid": terminal.proc.pid,
        "ps": command_line,
        "runtime": runtime,
        "exit": returncode,
        "pass": record["returncode"] == 0 and runtime in command_line and returncode == 0,
    }
    write_json(out / "launcher-exec-summary.json", summary)
    return summary


def prepare_isolated_home(args, out):
    isolated = out / f"model-restore-home-{uuid.uuid4()}"
    trash_path(isolated)
    (isolated / ".claude").mkdir(parents=True, mode=0o700)
    (isolated / ".cli-proxy-api").mkdir(parents=True, mode=0o700)
    settings = isolated / ".claude/settings.json"
    settings.write_text(json.dumps({"model": "claude-f51[1m]"}, indent=2) + "\n")
    overlay = isolated / ".claude/claude-mix-settings.json"
    shutil.copyfile(args.overlay, overlay)
    key_file = isolated / ".cli-proxy-api/.local-api-key"
    shutil.copyfile(HOME / ".cli-proxy-api/.local-api-key", key_file)
    (isolated / ".claude.json").write_text(json.dumps({
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "2.1.318",
        "projects": {str(args.cwd): {"hasTrustDialogAccepted": True}},
    }) + "\n")
    for path in (settings, overlay, key_file, isolated / ".claude.json"):
        path.chmod(0o600)
    release = args.launcher.resolve().parent
    cloned_release = isolated / ".local/share/claude-renderpatch/releases" / release.name
    cloned_release.parent.mkdir(parents=True, mode=0o700)
    subprocess.run(["/bin/cp", "-cR", str(release), str(cloned_release)], check=True, capture_output=True, text=True)
    cloned_launcher = cloned_release / args.launcher.name
    return isolated, settings, cloned_launcher


def gate_restore(args, out):
    live_settings = HOME / ".claude/settings.json"
    live_before = sha256(live_settings)
    isolated, settings, cloned_launcher = prepare_isolated_home(args, out)
    before = read_json(settings).get("model")
    terminal = Pty(
        [cloned_launcher, "--model", "opus", "--permission-mode", "default"],
        args.cwd,
        clean_env({"CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN": "1"}, home=isolated),
    )
    terminal.read(12)
    terminal.submit("/model gpt-5.6-sol")
    deadline = time.monotonic() + 20
    during = None
    while time.monotonic() < deadline:
        terminal.read(0.5)
        during = read_json(settings).get("model")
        if during == "gpt-5.6-sol":
            break
    terminal.submit("/exit")
    terminal.read(5)
    returncode = terminal.finish()
    deadline = time.monotonic() + 10
    after = read_json(settings).get("model")
    while time.monotonic() < deadline and after != before:
        time.sleep(0.1)
        after = read_json(settings).get("model")
    live_after = sha256(live_settings)
    (out / "model-restore.ansi").write_bytes(bytes(terminal.data))
    summary = {
        "isolatedHome": str(isolated),
        "originalLauncher": str(args.launcher),
        "clonedLauncher": str(cloned_launcher),
        "launcherSha256Match": sha256(args.launcher) == sha256(cloned_launcher),
        "before": before,
        "during": during,
        "after": after,
        "exit": returncode,
        "liveSettingsSha256Before": live_before,
        "liveSettingsSha256After": live_after,
        "pass": (
            returncode == 0
            and during == "gpt-5.6-sol"
            and after == before
            and live_after == live_before
            and sha256(args.launcher) == sha256(cloned_launcher)
        ),
    }
    for sensitive in (
        isolated / ".claude/claude-mix-settings.json",
        isolated / ".cli-proxy-api/.local-api-key",
        isolated / ".claude/settings.json",
    ):
        if sensitive.exists():
            sensitive.write_text("\n")
    trash_path(isolated)
    summary["isolatedHomeDisposed"] = True
    write_json(out / "model-restore-summary.json", summary)
    return summary


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def gate_env(args, out):
    bash_marker = "RP_BASH_ENV_2_1_318"
    shell = "printf '" + bash_marker + "\\n" + "".join(f"{name}=%s\\n" for name in PRELOAD_NAMES + ("CLAUDE_CODE_EXECPATH",)) + "' "
    shell += " ".join(f'"${{{name}-<unset>}}"' for name in PRELOAD_NAMES + ("CLAUDE_CODE_EXECPATH",))
    bash = run(
        [args.launcher,
         "--model", "haiku",
         "--permission-mode", "default",
         "--tools", "Bash",
         "--allowedTools", "Bash",
         "--strict-mcp-config",
         "--output-format", "stream-json",
         "--verbose",
         "-p", f"Run exactly this Bash command once: {shell} Then reply exactly {bash_marker}."],
        "bash-child-env-run",
        out,
        args.cwd,
        timeout=400,
    )
    bash_seen = {}
    for name in PRELOAD_NAMES + ("CLAUDE_CODE_EXECPATH",):
        matches = re.findall(re.escape(name) + r"=([^\s\\\"]+)", bash["stdout"])
        bash_seen[name] = matches[-1] if matches else None

    mcp_dir = out / "mcp-env-project"
    trash_path(mcp_dir)
    mcp_dir.mkdir(parents=True)
    server_log = out / "mcp-env-server.jsonl"
    trash_path(server_log)
    mcp_config = mcp_dir / "mcp.json"
    write_json(mcp_config, {"mcpServers": {"rpverify": {
        "type": "stdio",
        "command": sys.executable,
        "args": [str(args.mcp_fixture), "--mode", "basic", "--log", str(server_log)],
    }}})
    mcp_marker = "RP_MCP_ENV_2_1_318"
    mcp = run(
        [args.launcher,
         "--model", "haiku",
         "--permission-mode", "default",
         "--mcp-config", mcp_config,
         "--strict-mcp-config",
         "--tools", "mcp__rpverify__env_report",
         "--allowedTools", "mcp__rpverify__env_report",
         "--output-format", "stream-json",
         "--verbose",
         "-p", f"Call mcp__rpverify__env_report exactly once, then reply exactly {mcp_marker}."],
        "mcp-child-env-run",
        out,
        mcp_dir,
        timeout=400,
    )
    server_events = read_jsonl(server_log) if server_log.exists() else []
    startups = [event for event in server_events if event.get("event") == "startup"]
    calls = [event for event in server_events if event.get("event") == "tool_call" and event.get("name") == "env_report"]
    mcp_seen = startups[-1].get("env", {}) if startups else {}
    bash_leaked = [name for name in PRELOAD_NAMES if bash_seen.get(name) not in (None, "<unset>")]
    mcp_leaked = [name for name in PRELOAD_NAMES if mcp_seen.get(name) not in (None, "<unset>")]
    runtime = str(args.release / "runtime/claude")
    summary = {
        "bash": {
            "returncode": bash["returncode"],
            "seen": bash_seen,
            "leaked": bash_leaked,
            "marker": bash_marker in bash["stdout"],
            "execPath": bash_seen.get("CLAUDE_CODE_EXECPATH"),
        },
        "mcp": {
            "returncode": mcp["returncode"],
            "seen": mcp_seen,
            "leaked": mcp_leaked,
            "startupCount": len(startups),
            "callCount": len(calls),
            "marker": mcp_marker in mcp["stdout"],
        },
    }
    summary["pass"] = (
        bash["returncode"] == 0
        and not bash_leaked
        and bash_marker in bash["stdout"]
        and bash_seen.get("CLAUDE_CODE_EXECPATH") == runtime
        and mcp["returncode"] == 0
        and not mcp_leaked
        and len(startups) == 1
        and len(calls) == 1
        and mcp_marker in mcp["stdout"]
        and mcp_seen.get("CLAUDE_CODE_EXECPATH") == "<unset>"
    )
    write_json(out / "child-env-summary.json", summary)
    return summary


def restore_clone_modes(source, clone):
    manifest = read_json(source / "release-manifest.json")
    for relative, metadata in manifest["assets"].items():
        path = clone / relative
        if path.exists():
            os.chmod(path, metadata["mode"])
    os.chmod(clone / "claude-renderpatch-candidate", 0o555)
    os.chmod(clone / ".claude-renderpatch-release", 0o444)
    os.chmod(clone / "release-manifest.json", 0o444)
    for directory in sorted((path for path in clone.rglob("*") if path.is_dir()), reverse=True):
        os.chmod(directory, 0o555)
    os.chmod(clone, 0o555)


def gate_tamper(args, out):
    graph_assets = sorted((args.release / "graph").glob("*.js"))
    if not graph_assets:
        raise RuntimeError("release contains no graph JavaScript assets")
    graph_relative = graph_assets[0].relative_to(args.release)
    results = {}
    for case in ("graph", "host", "extra"):
        clone = out / f"tamper-{case}-clone"
        trash_path(clone)
        subprocess.run(["cp", "-cR", str(args.release), str(clone)], check=True)
        subprocess.run(["chmod", "-R", "u+w", str(clone)], check=True)
        if case == "graph":
            path = clone / graph_relative
            path.write_text(path.read_text() + "\n// renderpatch tamper gate\n")
            expected = f"asset hash mismatch: {graph_relative}"
        elif case == "host":
            path = clone / "host.mjs"
            path.write_text(path.read_text() + "\n// renderpatch tamper gate\n")
            expected = "asset hash mismatch: host.mjs"
        else:
            (clone / "unexpected-asset").write_text("tamper\n")
            os.chmod(clone / "unexpected-asset", 0o444)
            expected = "unlisted asset: unexpected-asset"
        restore_clone_modes(args.release, clone)
        result = run([clone / "claude-renderpatch-candidate", "--version"], f"tamper-{case}", out, args.cwd)
        results[case] = {"returncode": result["returncode"], "expected": expected, "stderr": result["stderr"].strip()}
        subprocess.run(["chmod", "-R", "u+w", str(clone)], check=True)
        trash_path(clone)
    ambient = run([args.launcher, "--version"], "reject-ambient-preload", out, args.cwd, env=clean_env({"BUN_OPTIONS": "--preload=/tmp/rp-invalid.mjs"}))
    safe = run([args.launcher, "--renderpatch-safe", "--version"], "safe-scrub-ambient", out, args.cwd, env=clean_env({"BUN_OPTIONS": "--preload=/tmp/rp-invalid.mjs"}))
    results["ambient"] = {"returncode": ambient["returncode"], "stderr": ambient["stderr"].strip()}
    results["safeScrub"] = {"returncode": safe["returncode"], "stdout": safe["stdout"].strip()}
    results["pass"] = (
        all(results[case]["returncode"] == 1 and results[case]["expected"] in results[case]["stderr"] for case in ("graph", "host", "extra"))
        and ambient["returncode"] == 1
        and "refusing inherited BUN_OPTIONS" in ambient["stderr"]
        and safe["returncode"] == 0
        and safe["stdout"].strip().startswith("2.1.318 ")
    )
    write_json(out / "tamper-summary.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("launcher", type=Path)
    parser.add_argument("--stock", type=Path, help="Official 2.1.318 executable; defaults to release runtime/claude")
    parser.add_argument("--overlay", type=Path, default=HOME / ".claude/claude-mix-settings.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, default=Path("/tmp/rp-host-gates-2.1.318"))
    parser.add_argument("--only", action="append", choices=("basic", "slots", "routing", "mod", "exec", "restore", "env", "tamper"))
    parser.add_argument("--routing-sites", action="append", choices=("S1", "S2"))
    args = parser.parse_args()
    args.launcher = args.launcher.resolve()
    args.release = args.launcher.parent
    args.stock = (args.stock or args.release / "runtime/claude").resolve()
    args.overlay = args.overlay.resolve()
    args.repo = Path(__file__).resolve().parents[1]
    args.mcp_fixture = args.repo / "verify/fixtures/mcp-2.1.318.py"
    args.cwd.mkdir(parents=True, exist_ok=True)
    args.cwd = args.cwd.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    gates = {
        "basic": gate_basic,
        "slots": gate_slots,
        "routing": gate_routing,
        "mod": gate_mod,
        "exec": gate_exec,
        "restore": gate_restore,
        "env": gate_env,
        "tamper": gate_tamper,
    }
    passed = {}
    for name in args.only or gates:
        result = gates[name](args, out)
        passed[name] = result.get("pass") is True
        print(name, json.dumps(result, sort_keys=True)[:2000], flush=True)
    write_json(out / "host-gates-summary.json", passed)
    print(json.dumps(passed, sort_keys=True))
    if not all(passed.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
