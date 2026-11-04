#!/usr/bin/env python3
"""Bounded .2 smoke and N2 MCP server-requested backgrounding proof.

The MCP call runs for 20 seconds, asks to be backgrounded after two seconds,
and has the normal auto-background threshold pinned at 60 seconds. Evidence is
written before the isolated workspace/config directories are removed.
"""

import argparse
import datetime
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

VERSION = "2.1.318"
RELEASE_ID = "2.1.318-host-darwin-arm64.2"
TAG = "N2_MARKER_QUICK_318"
SMOKE_MARKER = "MCP_MARKER_SMOKE_318_OK"
FINAL_MARKER = "MCP_MARKER_QUICK_318_DONE"
AUTO_BACKGROUND_MS = 60000
TOOL_SECONDS = 20
MARKER_AFTER_SECONDS = 2


class SmokeOnlyComplete(Exception):
    pass

MAX_COMMAND_SECONDS = 180
DEFAULT_LAUNCHER = (
    Path.home()
    / ".local/share/claude-renderpatch/releases"
    / RELEASE_ID
    / "claude-renderpatch-candidate"
)
REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "patched/verification-2.1.318/fast-marker-quick"
DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures/mcp-background-2.1.318.py"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for value in values:
            stream.write(json.dumps(value, sort_keys=True) + "\n")


def clean_env(config_dir):
    rejected = {
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_EXECPATH",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED",
        "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS",
        "CLAUDE_AUTO_BACKGROUND_TASKS",
        "ENABLE_TOOL_SEARCH",
    }
    env = {key: value for key, value in os.environ.items() if key not in rejected}
    env.update({
        "TERM": "xterm-256color",
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
        "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1",
        "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": str(AUTO_BACKGROUND_MS),
        "CLAUDE_AUTO_BACKGROUND_TASKS": "1",
    })
    return env


def terminate_group(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"process group {proc.pid} survived SIGKILL")


def run_bounded(argv, label, out, cwd, env, timeout, *, observe_lines=False):
    timeout = min(float(timeout), MAX_COMMAND_SECONDS)
    started_wall = time.time()
    started_monotonic = time.monotonic()
    proc = subprocess.Popen(
        [str(value) for value in argv],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    line_buffers = {"stdout": bytearray(), "stderr": bytearray()}
    observations = []
    timed_out = False
    deadline = started_monotonic + timeout

    def note_lines(stream_name, data):
        if not observe_lines:
            return
        line_buffers[stream_name].extend(data)
        while b"\n" in line_buffers[stream_name]:
            raw, _, rest = line_buffers[stream_name].partition(b"\n")
            line_buffers[stream_name] = bytearray(rest)
            observations.append({
                "stream": stream_name,
                "observedMonotonic": time.monotonic(),
                "observedWall": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "line": raw.decode("utf-8", "replace"),
            })

    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0 and proc.poll() is None:
                timed_out = True
                terminate_group(proc)
                remaining = 0
            events = selector.select(min(0.2, max(0, remaining)))
            for key, _ in events:
                data = os.read(key.fileobj.fileno(), 65536)
                if data:
                    chunks[key.data].extend(data)
                    note_lines(key.data, data)
                else:
                    selector.unregister(key.fileobj)
            if proc.poll() is not None and not events:
                for key in list(selector.get_map().values()):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if data:
                        chunks[key.data].extend(data)
                        note_lines(key.data, data)
                    else:
                        selector.unregister(key.fileobj)
        if proc.poll() is None:
            remaining = max(0, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                terminate_group(proc)
    finally:
        selector.close()
        if proc.poll() is None:
            timed_out = True
            terminate_group(proc)

    for stream_name, raw in line_buffers.items():
        if observe_lines and raw:
            observations.append({
                "stream": stream_name,
                "observedMonotonic": time.monotonic(),
                "observedWall": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "line": raw.decode("utf-8", "replace"),
            })
    stdout = chunks["stdout"].decode("utf-8", "replace")
    stderr = chunks["stderr"].decode("utf-8", "replace")
    record = {
        "label": label,
        "argv": [str(value) for value in argv],
        "returncode": proc.returncode,
        "timedOut": timed_out,
        "timeoutSeconds": timeout,
        "startedWall": datetime.datetime.fromtimestamp(
            started_wall, datetime.timezone.utc
        ).isoformat(),
        "startedMonotonic": started_monotonic,
        "seconds": round(time.monotonic() - started_monotonic, 3),
        "stdout": stdout,
        "stderr": stderr,
    }
    write_json(out / f"{label}.json", record)
    if observe_lines:
        write_jsonl(out / f"{label}-observations.jsonl", observations)
    return record, observations


def parse_last_json(text):
    for line in reversed(text.splitlines()):
        if not line.strip():
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


def parse_status(text):
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def block_text(block):
    value = block.get("content")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            item.get("text", "")
            for item in value
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


def stream_evidence(observations):
    tool_uses = []
    tool_results = []
    for observation in observations:
        if observation["stream"] != "stdout":
            continue
        try:
            record = json.loads(observation["line"])
        except json.JSONDecodeError:
            continue
        message = record.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            continue
        if record.get("type") == "assistant":
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") in ("tool_use", "mcp_tool_use")
                    and block.get("name") == "mcp__markerquick__nap"
                ):
                    tool_uses.append({
                        "id": block.get("id"),
                        "input": block.get("input"),
                        "observedMonotonic": observation["observedMonotonic"],
                    })
        if record.get("type") == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_results.append({
                        "toolUseId": block.get("tool_use_id"),
                        "text": block_text(block),
                        "isError": block.get("is_error") is True,
                        "observedMonotonic": observation["observedMonotonic"],
                    })
    matching_results = []
    ids = {item["id"] for item in tool_uses}
    for result in tool_results:
        if result["toolUseId"] in ids:
            matching_results.append(result)
    return tool_uses, matching_results


def read_fixture_events(path):
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event": "malformed", "raw": line})
    return events


def copy_transcripts(config_dir, out, needle):
    copied = []
    destination = out / "transcripts"
    for path in config_dir.rglob("*.jsonl"):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if needle not in text:
            continue
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / path.name
        if target.exists():
            target = destination / f"{path.parent.name}-{path.name}"
        shutil.copy2(path, target)
        copied.append(str(target))
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, default=DEFAULT_LAUNCHER)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--smoke-only", action="store_true")
    modes.add_argument("--marker-only", action="store_true")
    parser.add_argument("--command-timeout", type=float, default=120)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.fixture = args.fixture.resolve()
    if args.command_timeout <= 0 or args.command_timeout > MAX_COMMAND_SECONDS:
        parser.error(f"--command-timeout must be in (0, {MAX_COMMAND_SECONDS}]")
    if args.out.exists():
        parser.error(f"refusing to reuse evidence directory: {args.out}")
    if not args.launcher.is_file():
        parser.error(f"launcher not found: {args.launcher}")
    if RELEASE_ID not in str(args.launcher.resolve()):
        parser.error(f"launcher is not the required .2 release: {args.launcher}")
    if not args.fixture.is_file():
        parser.error(f"fixture not found: {args.fixture}")

    args.out.mkdir(parents=True)
    work = args.out / "work"
    config_dir = args.out / "config"
    work.mkdir()
    config_dir.mkdir(mode=0o700)
    env = clean_env(config_dir)
    fixture_log = args.out / "mcp-server.jsonl"
    mcp_config = work / "mcp.json"
    write_json(mcp_config, {"mcpServers": {"markerquick": {
        "type": "stdio",
        "command": sys.executable,
        "args": [str(args.fixture), "--log", str(fixture_log)],
    }}})

    summary = {
        "pass": False,
        "releaseId": RELEASE_ID,
        "launcher": str(args.launcher),
        "environment": {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": env.get(
                "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED"
            ),
            "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": env.get(
                "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS"
            ),
            "CLAUDE_AUTO_BACKGROUND_TASKS": env.get(
                "CLAUDE_AUTO_BACKGROUND_TASKS"
            ),
            "cleared": {
                key: key not in env
                for key in (
                    "CLAUDE_CODE_CHILD_SESSION",
                    "CLAUDECODE",
                    "CLAUDE_CODE_EXECPATH",
                )
            },
        },
        "smoke": {},
        "n2": {},
        "cleanup": {
            "performed": False,
            "retained": [str(work), str(config_dir)],
            "summaryWrittenBeforeCleanup": True,
        },
    }
    exit_code = 1
    try:
        if args.marker_only:
            summary["smoke"] = {"pass": True, "skipped": True}
        else:
            status, _ = run_bounded(
                [args.launcher, "--renderpatch-status"],
                "status", args.out, work, env, 30,
            )
            version, _ = run_bounded(
                [args.launcher, "--version"],
                "version", args.out, work, env, 30,
            )
            safe_version, _ = run_bounded(
                [args.launcher, "--renderpatch-safe", "--version"],
                "safe-version", args.out, work, env, 30,
            )
            proxy, _ = run_bounded(
                [
                    args.launcher,
                    "--setting-sources", "project,local",
                    "--model", "sonnet",
                    "--permission-mode", "default",
                    "--strict-mcp-config",
                    "--tools", "",
                    "--output-format", "json",
                    "-p", f"Reply exactly {SMOKE_MARKER}.",
                ],
                "proxy-smoke", args.out, work, env, args.command_timeout,
            )
            status_fields = parse_status(status["stdout"])
            proxy_payload = parse_last_json(proxy["stdout"])
            expected_build_id = f"host-{VERSION}-darwin-arm64.2"
            expected_release_dir = f"/{RELEASE_ID}/"
            smoke_checks = {
                "statusExitZero": status["returncode"] == 0 and not status["timedOut"],
                "statusTargetVersion": status_fields.get("target_version") == VERSION,
                "statusBuildId": status_fields.get("bridge_build_id") == expected_build_id,
                "statusTargetRelease": expected_release_dir in status_fields.get("target", ""),
                "statusVerification": status_fields.get("verification") == "ok",
                "version": version["returncode"] == 0
                and version["stdout"].strip().startswith(f"{VERSION} "),
                "safeVersion": safe_version["returncode"] == 0
                and safe_version["stdout"].strip().startswith(f"{VERSION} "),
                "realProxy": proxy["returncode"] == 0
                and proxy_payload.get("result", "").strip() == SMOKE_MARKER,
            }
            summary["smoke"] = {
                "checks": smoke_checks,
                "pass": all(smoke_checks.values()),
                "status": status_fields,
                "proxyResult": proxy_payload.get("result"),
            }
            if not summary["smoke"]["pass"]:
                raise RuntimeError(".2 smoke failed; N2 marker call was not started")
            if args.smoke_only:
                summary["pass"] = True
                exit_code = 0
                raise SmokeOnlyComplete()

        prompt = (
            "Call mcp__markerquick__nap exactly once with "
            f'{{"seconds":{TOOL_SECONDS},"tag":"{TAG}",'
            f'"marker_after_s":{MARKER_AFTER_SECONDS}}}. '
            "Do not call any other tool. As soon as that tool_result returns, "
            f"reply exactly {FINAL_MARKER}. Do not wait for the background task."
        )
        marker, observations = run_bounded(
            [
                args.launcher,
                "--setting-sources", "project,local",
                "--model", "sonnet",
                "--permission-mode", "default",
                "--mcp-config", mcp_config,
                "--strict-mcp-config",
                "--allowedTools", "mcp__markerquick__nap",
                "--output-format", "stream-json",
                "--verbose",
                "-p", prompt,
            ],
            "n2-marker", args.out, work, env, args.command_timeout,
            observe_lines=True,
        )
        tool_uses, tool_results = stream_evidence(observations)
        fixture_events = read_fixture_events(fixture_log)
        starts = [event for event in fixture_events if event.get("event") == "started" and event.get("tag") == TAG]
        markers = [event for event in fixture_events if event.get("event") == "marker" and event.get("tag") == TAG]
        completions = [event for event in fixture_events if event.get("event") == "completed" and event.get("tag") == TAG]
        start = starts[0] if len(starts) == 1 else None
        server_marker = markers[0] if len(markers) == 1 else None
        result = tool_results[0] if len(tool_results) == 1 else None
        result_since_start = (
            result["observedMonotonic"] - start["monotonic"]
            if result is not None and start is not None else None
        )
        result_after_marker = (
            result["observedMonotonic"] - server_marker["monotonic"]
            if result is not None and server_marker is not None else None
        )
        result_text = result["text"] if result is not None else ""
        lower_result = result_text.lower()
        final_text = "\n".join(
            observation["line"] for observation in observations
            if observation["stream"] == "stdout"
        )
        exact_input = {
            "seconds": TOOL_SECONDS,
            "tag": TAG,
            "marker_after_s": MARKER_AFTER_SECONDS,
        }
        checks = {
            "commandExitZero": marker["returncode"] == 0 and not marker["timedOut"],
            "oneToolUse": len(tool_uses) == 1,
            "exactToolInput": len(tool_uses) == 1 and tool_uses[0]["input"] == exact_input,
            "oneMatchingToolResult": len(tool_results) == 1,
            "serverSawOneStart": len(starts) == 1,
            "serverSawOneMarker": len(markers) == 1,
            "toolUseIdBound": len(tool_uses) == 1 and start is not None
            and start.get("toolUseId") == tool_uses[0]["id"],
            "serverMarkerNearTwoSeconds": server_marker is not None
            and 1.5 <= server_marker.get("elapsed", -1) <= 4.0,
            "toolResultNearTwoSeconds": result_since_start is not None
            and 1.5 <= result_since_start <= 5.0,
            "toolResultImmediatelyAfterMarker": result_after_marker is not None
            and 0 <= result_after_marker <= 2.0,
            "beforeTwentySecondCompletion": result is not None
            and (
                not completions
                or result["observedMonotonic"] < min(
                    event["monotonic"] for event in completions
                )
            ),
            "serverSpecificReason": (
                'mcp tool "markerquick/nap"' in lower_result
                and "because the server requested backgrounding" in lower_result
                and "keeps running" in lower_result
            ),
            "notTimeoutReason": "still running after" not in lower_result,
            "notQueuedMessageReason": "message that arrived" not in lower_result,
            "notFinalServerResult": f"mcp_result_{TAG.lower()}" not in lower_result,
            "finalMarker": FINAL_MARKER in final_text,
            "thresholdPinnedToSixtySeconds": env.get(
                "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS"
            ) == str(AUTO_BACKGROUND_MS),
            "headlessAutoBackgroundEnabled": env.get(
                "CLAUDE_AUTO_BACKGROUND_TASKS"
            ) == "1",
        }
        copied = copy_transcripts(config_dir, args.out, TAG)
        summary["n2"] = {
            "pass": all(checks.values()),
            "checks": checks,
            "thresholdMs": AUTO_BACKGROUND_MS,
            "toolSeconds": TOOL_SECONDS,
            "requestedMarkerAfterSeconds": MARKER_AFTER_SECONDS,
            "serverMarkerElapsedSeconds": server_marker.get("elapsed") if server_marker else None,
            "toolResultSinceServerStartSeconds": round(result_since_start, 3) if result_since_start is not None else None,
            "toolResultAfterServerMarkerSeconds": round(result_after_marker, 3) if result_after_marker is not None else None,
            "toolUse": tool_uses,
            "toolResult": result,
            "fixtureEvents": fixture_events,
            "transcripts": copied,
        }
        summary["pass"] = summary["smoke"]["pass"] and summary["n2"]["pass"]
        exit_code = 0 if summary["pass"] else 1
    except SmokeOnlyComplete:
        pass
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
    finally:
        # Retain the isolated owned directories as evidence; no destructive
        # cleanup is needed. The receipt is still committed before returning.
        write_json(args.out / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
