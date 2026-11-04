#!/usr/bin/env python3
"""One-shot interactive gate for MCP auto-background ownership in 2.1.318.

The gate launches a real Claude PTY session, not print mode, with the upstream
``CLAUDE_AUTO_BACKGROUND_TASKS`` opt-in explicitly absent. An unnamed background
Agent calls the deterministic 20-second MCP fixture. Transcript records—not
model claims—must show a background acknowledgement near five seconds, followed
by the completed MCP task notification in the child transcript and not the lead
transcript.

The output directory must not already exist. The evidence summary is committed
before bounded process cleanup so a failed live run remains inspectable.
"""

import argparse
import datetime
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import uuid
from pathlib import Path

VERSION = "2.1.318"
SERVER = "bridge_bg"
MCP_TOOL = f"mcp__{SERVER}__nap"
CHILD_TAG = "OWNER_INTERACTIVE_CHILD_318"
CHILD_MARKER = "CHILD_OWNER_INTERACTIVE_FINISHED_318"
FINAL_MARKER = "OWNER_INTERACTIVE_DONE_318"
AUTO_BACKGROUND_MS = 5000
BACKGROUND_MIN_SECONDS = 3.0
BACKGROUND_MAX_SECONDS = 8.0
RUN_MAX_SECONDS = 150.0
CLEANUP_MAX_SECONDS = 10.0
ANSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-Za-z]")


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


def assistant_text_contains(path, marker):
    for record in read_jsonl(path):
        if record.get("type") != "assistant":
            continue
        if marker in content_text((record.get("message") or {}).get("content")):
            return True
    return False


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
        "CLAUDE_AUTO_BACKGROUND_TASKS",
        "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS",
    ):
        env.pop(key, None)
    env.update(
        {
            "TERM": "xterm-256color",
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
            "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1",
            "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": str(AUTO_BACKGROUND_MS),
        }
    )
    return env


class PtySession:
    def __init__(self, argv, cwd, env):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
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

    def text(self):
        return ANSI.sub(b"", bytes(self.data)).decode(errors="replace")

    def read_until(self, deadline, marker=None):
        while time.monotonic() < deadline:
            wait = min(0.2, max(0.0, deadline - time.monotonic()))
            readable, _, _ = select.select([self.master], [], [], wait)
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
            if marker and marker in self.text():
                return True
            if self.proc.poll() is not None:
                break
        return marker is None

    def submit(self, text):
        os.write(self.master, text.encode())
        self.read_until(time.monotonic() + 1.0)
        os.write(self.master, b"\x1b\r")

    def cleanup(self, timeout=CLEANUP_MAX_SECONDS):
        started = time.monotonic()
        deadline = started + timeout
        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)
        for index, sent_signal in enumerate(signals):
            if self.proc.poll() is not None:
                break
            try:
                os.killpg(self.proc.pid, sent_signal)
            except ProcessLookupError:
                break
            phase_deadline = deadline if index == len(signals) - 1 else min(deadline, time.monotonic() + 2.0)
            self.read_until(phase_deadline)
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        remaining = max(0.0, deadline - time.monotonic())
        try:
            self.proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.close(self.master)
        except OSError:
            pass
        return {
            "seconds": round(time.monotonic() - started, 3),
            "returncode": self.proc.poll(),
            "withinLimit": time.monotonic() - started <= timeout,
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
        / ".local/share/claude-renderpatch/releases/2.1.318-host-darwin-arm64.3/claude-renderpatch-candidate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo / "patched/verification-2.1.318/interactive-mcp-owner-quick",
    )
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--timeout", type=float, default=RUN_MAX_SECONDS)
    args = parser.parse_args()
    args.launcher = args.launcher.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    require(0 < args.timeout <= RUN_MAX_SECONDS, "timeout must be between 0 and 150 seconds", args.timeout)
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
            "env": {"CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": str(AUTO_BACKGROUND_MS)},
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
        f"The call must auto-background. Wait for the actual task-notification containing MCP_RESULT_{CHILD_TAG}. "
        f"Do not repeat that MCP result in your final report. After receiving it, reply exactly {CHILD_MARKER}."
    )
    prompt = (
        "Call Agent exactly once with subagent_type=\"general-purpose\", "
        f"model=\"{args.model}\", description=\"interactive MCP owner child\", run_in_background=true, and prompt="
        f"{json.dumps(child_prompt)}. Do not set the Agent name field; this must be an unnamed background child. "
        f"Do not call any other tools. Wait for the Agent completion, then reply exactly {FINAL_MARKER}."
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
    ]
    require("-p" not in [str(value) for value in argv], "interactive gate unexpectedly uses print mode")

    run_started = time.monotonic()
    deadline = run_started + args.timeout
    summary = {
        "version": VERSION,
        "sessionId": session_id,
        "launcher": str(args.launcher),
        "interactive": True,
        "argv": [str(value) for value in argv],
        "environment": {
            "CLAUDE_AUTO_BACKGROUND_TASKS": "<unset>",
            "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": str(AUTO_BACKGROUND_MS),
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
        },
        "limits": {"runSeconds": args.timeout, "cleanupSeconds": CLEANUP_MAX_SECONDS},
        "summaryWrittenBeforeCleanup": True,
        "pass": False,
    }
    terminal = None
    error = None
    exit_code = 1
    try:
        env = clean_env(config_dir)
        require("CLAUDE_AUTO_BACKGROUND_TASKS" not in env, "upstream auto-background opt-in leaked into environment")
        terminal = PtySession(argv, workspace, env)
        startup_deadline = min(deadline, time.monotonic() + 12.0)
        terminal.read_until(startup_deadline)
        require(terminal.proc.poll() is None, "interactive Claude exited before prompt submission", terminal.text()[-4000:])
        terminal.submit(prompt)
        project = project_directory(config_dir, workspace)
        lead = project / f"{session_id}.jsonl"
        while time.monotonic() < deadline and not assistant_text_contains(lead, FINAL_MARKER):
            terminal.read_until(min(deadline, time.monotonic() + 0.5))
        require(
            assistant_text_contains(lead, FINAL_MARKER),
            "interactive run did not reach the final marker before its deadline",
            terminal.text()[-8000:],
        )

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
        child_notices = actual_task_notifications(child, f"MCP_RESULT_{CHILD_TAG}")
        leaked_notices = actual_task_notifications(lead, f"MCP_RESULT_{CHILD_TAG}")
        require(len(child_notices) == 1, "child did not receive its actual MCP task-notification", child_notices)
        require(not leaked_notices, "lead received the child's MCP task-notification", leaked_notices)

        summary.update(
            {
                "pass": True,
                "runSeconds": round(time.monotonic() - run_started, 3),
                "transcripts": {"lead": str(lead), "child": str(child)},
                "agentSpawn": spawn,
                "childCall": child_call,
                "notifications": {
                    "childReceived": child_notices,
                    "childDeliveredToLead": leaked_notices,
                },
                "finalMarkerInLeadTranscript": True,
            }
        )
        exit_code = 0
    except Exception as exc:
        error = exc
        summary["runSeconds"] = round(time.monotonic() - run_started, 3)
        summary["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if terminal is not None:
            (args.output / "terminal-before-cleanup.ansi").write_bytes(bytes(terminal.data))
            (args.output / "terminal-before-cleanup.txt").write_text(terminal.text())
        write_json(args.output / "summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
        if terminal is not None:
            cleanup = terminal.cleanup()
            write_json(args.output / "cleanup.json", cleanup)

    if error is not None:
        raise SystemExit(1)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
