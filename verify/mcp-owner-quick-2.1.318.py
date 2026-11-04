#!/usr/bin/env python3
"""One-shot print-mode gate for MCP auto-background ownership in 2.1.318.

The gate launches one isolated ``-p`` session. The lead starts a genuinely
background, unnamed Agent and both the child and lead call the deterministic
20-second MCP fixture. With a five-second auto-background threshold, transcript
records—not model claims—must show:

* an MCP ``tool_result`` near five seconds for each caller;
* the child's completed MCP task notification delivered to the child;
* no delivery of that child MCP notification to the lead; and
* the lead's own completed MCP task notification delivered to the lead.

The output directory must not already exist, preventing accidental tuning by
re-running over the same evidence.
"""

import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

VERSION = "2.1.318"
SERVER = "bridge_bg"
MCP_TOOL = f"mcp__{SERVER}__nap"
CHILD_TAG = "OWNER_QUICK_CHILD_318"
LEAD_TAG = "OWNER_QUICK_LEAD_318"
FINAL_MARKER = "OWNER_QUICK_DONE_318"
BACKGROUND_MIN_SECONDS = 3.0
BACKGROUND_MAX_SECONDS = 8.0


class GateFailure(RuntimeError):
    pass


def require(condition, message, evidence=None):
    if condition:
        return
    if evidence is None:
        raise GateFailure(message)
    raise GateFailure(f"{message}: {json.dumps(evidence, indent=2, default=str)}")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def read_jsonl(path):
    rows = []
    try:
        with path.open() as stream:
            for line in stream:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return rows


def iso_seconds(value):
    if not value:
        return None
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def content_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif item.get("type") == "tool_result":
                    parts.append(content_text(item.get("content")))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True)


def message_blocks(record):
    content = (record.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def actual_tool_result(path, tool_use_id):
    matches = []
    for record in read_jsonl(path):
        if record.get("type") != "user":
            continue
        for block in message_blocks(record):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") != tool_use_id:
                continue
            matches.append(
                {
                    "timestamp": record.get("timestamp"),
                    "uuid": record.get("uuid"),
                    "toolUseId": tool_use_id,
                    "text": content_text(block.get("content")),
                    "isError": block.get("is_error", False),
                }
            )
    return matches


def actual_task_notifications(path, marker):
    matches = []
    for record in read_jsonl(path):
        text = ""
        source = None
        if record.get("type") == "user":
            text = content_text((record.get("message") or {}).get("content"))
            source = "user"
        elif record.get("type") == "attachment":
            attachment = record.get("attachment") or {}
            prompt = attachment.get("prompt")
            if isinstance(prompt, str):
                text = prompt
                source = "attachment"
        if source and "<task-notification>" in text and marker in text:
            matches.append(
                {
                    "timestamp": record.get("timestamp"),
                    "uuid": record.get("uuid"),
                    "source": source,
                    "excerpt": re.sub(r"\s+", " ", text)[:1200],
                }
            )
    return matches


def agent_spawn_evidence(path):
    matches = []
    for record in read_jsonl(path):
        if record.get("type") != "assistant":
            continue
        for block in message_blocks(record):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Agent":
                continue
            input_value = block.get("input") or {}
            if CHILD_TAG not in json.dumps(input_value, sort_keys=True):
                continue
            matches.append(
                {
                    "timestamp": record.get("timestamp"),
                    "toolUseId": block.get("id"),
                    "input": input_value,
                    "runInBackground": input_value.get("run_in_background"),
                    "namePresent": "name" in input_value,
                }
            )
    return matches


def project_directory(config_dir, cwd):
    encoded = str(cwd).replace("/", "-").replace(".", "-")
    return config_dir / "projects" / encoded


def clean_env(config_dir):
    env = os.environ.copy()
    for key in (
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_EXECPATH",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_AGENT_ID",
        "CLAUDE_CONFIG_DIR",
    ):
        env.pop(key, None)
    env.update(
        {
            "TERM": "xterm-256color",
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
            "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1",
            "CLAUDE_AUTO_BACKGROUND_TASKS": "1",
            "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "5000",
        }
    )
    return env


def bounded_run(argv, cwd, env, timeout):
    started = time.monotonic()
    proc = subprocess.Popen(
        [str(value) for value in argv],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate(timeout=10)
    return {
        "argv": [str(value) for value in argv],
        "returncode": proc.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "timedOut": timed_out,
        "stdout": stdout,
        "stderr": stderr,
    }


def one_event(events, event, tag):
    matches = [row for row in events if row.get("event") == event and row.get("tag") == tag]
    require(len(matches) == 1, f"expected one fixture {event} event for {tag}", matches)
    return matches[0]


def call_evidence(tag, transcript, events):
    started = one_event(events, "started", tag)
    completed = one_event(events, "completed", tag)
    tool_use_id = started.get("toolUseId")
    require(tool_use_id, f"fixture did not record a tool-use ID for {tag}", started)
    results = actual_tool_result(transcript, tool_use_id)
    require(len(results) == 1, f"expected one actual tool_result for {tag}", results)
    result = results[0]
    started_at = iso_seconds(started.get("timestamp"))
    result_at = iso_seconds(result.get("timestamp"))
    require(started_at is not None and result_at is not None, f"missing timestamps for {tag}")
    delay = result_at - started_at
    text = result.get("text", "")
    require(
        BACKGROUND_MIN_SECONDS <= delay <= BACKGROUND_MAX_SECONDS,
        f"{tag} tool_result was not near the five-second auto-background threshold",
        {"delaySeconds": delay, "result": result, "started": started},
    )
    require(
        not result.get("isError") and "background" in text.lower(),
        f"{tag} tool_result is not an actual background acknowledgement",
        result,
    )
    require(
        f"MCP_RESULT_{tag}" not in text,
        f"{tag} completed synchronously instead of backgrounding",
        result,
    )
    return {
        "tag": tag,
        "toolUseId": tool_use_id,
        "fixtureStarted": started,
        "fixtureCompleted": completed,
        "backgroundToolResult": result,
        "backgroundDelaySeconds": round(delay, 3),
    }


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--launcher",
        type=Path,
        default=Path.home()
        / ".local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.2/claude-renderpatch-candidate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo / "patched/verification-2.1.318/fast-mcp-owner-quick",
    )
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--timeout", type=float, default=150.0)
    args = parser.parse_args()
    args.launcher = args.launcher.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    require(args.timeout <= 180, "timeout must be at most 180 seconds", args.timeout)
    require(args.launcher.is_file(), "launcher missing", args.launcher)
    require(not args.output.exists(), "output directory already exists; use a fresh path", args.output)

    args.output.mkdir(parents=True)
    workspace = args.output / "workspace"
    workspace.mkdir()
    config_dir = args.output / "config"
    config_dir.mkdir(mode=0o700)
    fixture_log = args.output / "server.jsonl"
    fixture = repo / "verify/fixtures/mcp-background-2.1.318.py"
    require(fixture.is_file(), "MCP fixture missing", fixture)

    tools = f"Agent,{MCP_TOOL}"
    settings = config_dir / "settings.json"
    write_json(
        settings,
        {
            "permissions": {"defaultMode": "default", "allow": tools.split(",")},
            "env": {
                "CLAUDE_AUTO_BACKGROUND_TASKS": "1",
                "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "5000",
            },
        },
    )
    write_json(
        config_dir / ".claude.json",
        {
            "hasCompletedOnboarding": True,
            "lastOnboardingVersion": VERSION,
            "projects": {str(workspace): {"hasTrustDialogAccepted": True}},
        },
    )
    mcp_config = args.output / "mcp.json"
    write_json(
        mcp_config,
        {
            "mcpServers": {
                SERVER: {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(fixture), "--log", str(fixture_log)],
                }
            }
        },
    )

    session_id = str(uuid.uuid4())
    child_prompt = (
        f"Call {MCP_TOOL} exactly once with seconds=20, tag=\"{CHILD_TAG}\", and marker_after_s=-1. "
        f"The call must auto-background; wait for its actual task-notification containing MCP_RESULT_{CHILD_TAG}. "
        "Do not repeat that MCP result in your final report. After receiving it, reply exactly CHILD_OWNER_QUICK_FINISHED_318."
    )
    prompt = (
        "Perform these steps exactly. First call Agent exactly once with subagent_type=\"general-purpose\", "
        f"model=\"{args.model}\", description=\"MCP owner quick child\", run_in_background=true, and prompt="
        f"{json.dumps(child_prompt)}. Do not set the Agent name field; this must be an unnamed background child. "
        f"Immediately after the Agent spawn acknowledgement, call {MCP_TOOL} exactly once yourself with "
        f"seconds=20, tag=\"{LEAD_TAG}\", and marker_after_s=-1. The MCP call must auto-background. "
        f"Wait for your actual task-notification containing MCP_RESULT_{LEAD_TAG} and for the Agent completion. "
        f"Do not call any other tools. Then reply exactly {FINAL_MARKER}."
    )
    argv = [
        args.launcher,
        "--settings",
        settings,
        "--setting-sources",
        "project,local",
        "--session-id",
        session_id,
        "--model",
        args.model,
        "--permission-mode",
        "default",
        "--strict-mcp-config",
        "--mcp-config",
        mcp_config,
        "--tools",
        tools,
        "--allowedTools",
        tools,
        "--output-format",
        "stream-json",
        "--verbose",
        "-p",
        prompt,
    ]

    summary = {
        "version": VERSION,
        "sessionId": session_id,
        "environment": {
            "CLAUDE_AUTO_BACKGROUND_TASKS": "1",
            "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "5000",
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
        },
        "pass": False,
    }
    error = None
    try:
        run = bounded_run(argv, workspace, clean_env(config_dir), args.timeout)
        (args.output / "stdout.jsonl").write_text(run.pop("stdout"))
        (args.output / "stderr.txt").write_text(run.pop("stderr"))
        write_json(args.output / "run.json", run)
        require(not run["timedOut"], "print-mode run timed out", run)
        require(run["returncode"] == 0, "print-mode run failed", run)

        project = project_directory(config_dir, workspace)
        lead = project / f"{session_id}.jsonl"
        children = sorted((project / session_id / "subagents").glob("agent-*.jsonl"))
        require(lead.is_file(), "lead transcript missing", lead)
        require(len(children) == 1, "expected exactly one child transcript", children)
        child = children[0]
        events = read_jsonl(fixture_log)
        require(events, "fixture emitted no events", fixture_log)

        spawns = agent_spawn_evidence(lead)
        require(len(spawns) == 1, "expected one matching Agent spawn", spawns)
        spawn = spawns[0]
        require(spawn["runInBackground"] is True, "child Agent was not truly backgrounded", spawn)
        require(not spawn["namePresent"], "child Agent was named", spawn)

        child_call = call_evidence(CHILD_TAG, child, events)
        lead_call = call_evidence(LEAD_TAG, lead, events)
        child_notices = actual_task_notifications(child, f"MCP_RESULT_{CHILD_TAG}")
        leaked_notices = actual_task_notifications(lead, f"MCP_RESULT_{CHILD_TAG}")
        lead_notices = actual_task_notifications(lead, f"MCP_RESULT_{LEAD_TAG}")
        require(len(child_notices) == 1, "child did not receive its actual MCP task-notification", child_notices)
        require(not leaked_notices, "lead received the child's MCP task-notification", leaked_notices)
        require(len(lead_notices) == 1, "lead did not receive its own actual MCP task-notification", lead_notices)

        stdout_text = (args.output / "stdout.jsonl").read_text()
        summary.update(
            {
                "pass": True,
                "transcripts": {"lead": str(lead), "child": str(child)},
                "agentSpawn": spawn,
                "childCall": child_call,
                "leadCall": lead_call,
                "notifications": {
                    "childReceived": child_notices,
                    "childDeliveredToLead": leaked_notices,
                    "leadReceivedOwn": lead_notices,
                },
                "finalMarkerInStream": FINAL_MARKER in stdout_text,
            }
        )
    except Exception as exc:
        error = exc
        summary["error"] = str(exc)
    finally:
        write_json(args.output / "summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    if error is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
