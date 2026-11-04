#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Real-PTY gate for the 2.1.318 teammate transcript view.

A named in-process teammate persists more than 50 user/assistant rows before the
gate opens the real /tasks picker, selects it with ``f``, and expands its view
with Ctrl+O.  While that view remains open, eight more Read calls prove live
growth remains uncapped.  A plain background Agent is the unchanged control.
The named teammate then finishes off-view and is reopened from its idle row,
which proves disk hydration, terminal retention, and final-row visibility.

Every rendered marker must occur in a real Read/Bash tool row and in the child
JSONL. Prompt echo and accumulated ANSI redraws are never accepted as evidence.
The session uses default permission mode with explicit allowedTools, clears an
inherited CLAUDE_CODE_CHILD_SESSION, and trashes only its owned fixture.
"""

import argparse
import fcntl
import json
import os
import pty
import re
import select
import shlex
import signal
import struct
import subprocess
import sys
import termios
import time
import uuid
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude/projects"
ANSI = re.compile(
    rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    rb"|\x1b[P^_].*?\x1b\\"
    rb"|\x1b\[[0-?]*[ -/]*[@-~]"
    rb"|\x1b[@-_]",
    re.S,
)


class GateFailure(RuntimeError):
    pass


def require(condition, message, details=None):
    if condition:
        return
    if details is not None:
        message = f"{message}: {json.dumps(details, sort_keys=True)}"
    raise GateFailure(message)


def clean_env(extra=None):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION")
    }
    env["TERM"] = "xterm-256color"
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def project_dir(cwd, config_dir=HOME / ".claude"):
    return config_dir / "projects" / str(cwd).replace("/", "-").replace(".", "-")


def strip_ansi(data):
    text = ANSI.sub(b"", data).decode(errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compact_line(line):
    return re.sub(r"\s+", " ", line).strip()


def compact_text(text):
    return re.sub(r"\s+", "", text)


def rendered_marker_evidence(data, markers):
    text = strip_ansi(data)
    rows = [compact_line(line) for line in text.splitlines()]
    rows = [line for line in rows if line]
    marker_rows = {}
    first_by_marker = {}
    for marker in markers:
        seen_text = set()
        matches = []
        for index, row in enumerate(rows):
            if marker not in row or row in seen_text:
                continue
            if not re.search(r"\b(?:Read|Bash)\(", row):
                continue
            seen_text.add(row)
            matches.append({"line": index + 1, "text": row[-500:]})
        if matches:
            marker_rows[marker] = matches
            first_by_marker[marker] = matches[0]
    distinct_rows = {entry["text"] for entry in first_by_marker.values()}
    return {
        "renderedMarkers": sorted(first_by_marker),
        "renderedMarkerCount": len(first_by_marker),
        "distinctMarkerRowCount": len(distinct_rows),
        "expectedMarkerCount": len(markers),
        "renderedTranscriptRowCount": sum(
            bool(re.match(r"^[⏺●⎿]", row)) for row in rows
        ),
        "renderedToolHeaderCount": sum(
            bool(re.match(r"^[⏺●]\s*[A-Za-z_][\w:.-]*\(", row)) for row in rows
        ),
        "missingMarkers": [marker for marker in markers if marker not in first_by_marker],
        "markerRows": marker_rows,
        "cleanText": text,
    }


class PtySession:
    def __init__(self, argv, cwd, env, capture, cols=160, rows=180):
        self.cols = cols
        self.rows = rows
        self.master, slave = pty.openpty()
        fcntl.ioctl(
            slave,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", rows, cols, 0, 0),
        )
        self.proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
        os.close(slave)
        self.data = bytearray()
        self.closed = False
        self.capture = capture.open("wb", buffering=0)

    def mark(self):
        return len(self.data)

    def bytes_since(self, mark):
        return bytes(self.data[mark:])

    def text_since(self, mark=0):
        return strip_ansi(self.bytes_since(mark))

    def read(self, seconds, until=None, since=0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [self.master], [], [], min(0.2, max(0, deadline - time.monotonic()))
            )
            if ready:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.data.extend(chunk)
                self.capture.write(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(self.master, b"\x1b[1;1R")
                if b"\x1b[c" in chunk:
                    os.write(self.master, b"\x1b[?62;22c")
            if until and compact_text(until) in compact_text(self.text_since(since)):
                return True
            if self.proc.poll() is not None:
                break
        return until is None

    def drain(self, seconds=0.25):
        self.read(seconds)

    def write(self, data):
        while data:
            written = os.write(self.master, data)
            data = data[written:]

    def line(self, text, wait=0.5):
        self.write(b"\x1b[200~" + text.encode() + b"\x1b[201~")
        self.read(wait)
        self.write(b"\r")

    def resize(self, cols, rows=None):
        rows = self.rows if rows is None else rows
        self.cols = cols
        self.rows = rows
        fcntl.ioctl(
            self.master,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", rows, cols, 0, 0),
        )
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass

    def repaint_capture(self, seconds=3.0):
        self.drain()
        self.resize(self.cols - 1)
        self.read(0.8)
        mark = self.mark()
        self.resize(self.cols + 1)
        self.read(seconds)
        data = self.bytes_since(mark)
        start = data.rfind(b"\x1b[2J")
        require(start >= 0, "final resize did not produce a full repaint")
        return data[start:]

    def finish(self):
        if self.closed:
            return self.proc.returncode
        if self.proc.poll() is None:
            try:
                self.line("/exit")
                self.read(5)
            except OSError:
                pass
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.proc.wait()
        else:
            self.proc.wait()
        try:
            os.close(self.master)
        except OSError:
            pass
        self.closed = True
        self.capture.close()
        return self.proc.returncode


def jsonl_records(path):
    records = []
    if not path or not path.exists():
        return records
    for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append((line_number, json.loads(line)))
        except json.JSONDecodeError:
            # The writer may be between its write and terminating newline.
            continue
    return records


def transcript_evidence(path, markers, final_marker=None):
    tool_uses = []
    tool_results = set()
    assistant_text = []
    seen_tool_ids = set()
    message_row_count = 0
    for line_number, record in jsonl_records(path):
        if record.get("type") in ("user", "assistant"):
            message_row_count += 1
        message = record.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if record.get("type") == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    assistant_text.append(str(block.get("text", "")))
                if block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id", ""))
                if tool_id and tool_id in seen_tool_ids:
                    continue
                if tool_id:
                    seen_tool_ids.add(tool_id)
                encoded_input = json.dumps(block.get("input"), sort_keys=True)
                tool_uses.append(
                    {
                        "line": line_number,
                        "id": tool_id,
                        "name": block.get("name"),
                        "input": block.get("input"),
                        "markers": [m for m in markers if m in encoded_input],
                    }
                )
        elif record.get("type") == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_results.add(str(block.get("tool_use_id", "")))
    marker_uses = {}
    for use in tool_uses:
        for marker in use["markers"]:
            marker_uses.setdefault(marker, []).append(use["id"])
    return {
        "path": str(path) if path else None,
        "messageRowCount": message_row_count,
        "toolCallCount": len(tool_uses),
        "toolCalls": tool_uses,
        "toolResultIds": sorted(tool_results),
        "toolResultCount": len(tool_results),
        "markerToolIds": marker_uses,
        "markerToolCount": len(marker_uses),
        "missingMarkerTools": [marker for marker in markers if marker not in marker_uses],
        "completedMarkerTools": sorted(
            marker
            for marker, ids in marker_uses.items()
            if ids and all(tool_id in tool_results for tool_id in ids)
        ),
        "finalMarker": final_marker,
        "finalMarkerInAssistant": bool(
            final_marker and any(final_marker in text for text in assistant_text)
        ),
    }


def agent_launches(path):
    launches = []
    seen = set()
    for line_number, record in jsonl_records(path):
        if record.get("type") != "assistant":
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Agent":
                continue
            tool_id = str(block.get("id", ""))
            if tool_id and tool_id in seen:
                continue
            if tool_id:
                seen.add(tool_id)
            launches.append(
                {"line": line_number, "id": tool_id, "input": block.get("input") or {}}
            )
    return launches


def named_transcript(base, name):
    matches = sorted(base.glob(f"agent-a{name}-*.jsonl"))
    return matches[0] if matches else None


def plain_transcript(base, named_path, markers):
    for path in sorted(base.glob("agent-*.jsonl")):
        if named_path and path == named_path:
            continue
        if transcript_evidence(path, markers)["markerToolCount"]:
            return path
    return None


def wait_until(session, seconds, predicate):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        session.read(min(0.5, max(0, deadline - time.monotonic())))
        last = predicate()
        if last:
            return last
        if session.proc.poll() is not None:
            break
    return last


def snapshot(source, destination):
    destination.write_bytes(source.read_bytes())


def write_capture(out, name, data, markers):
    ansi_path = out / f"{name}.ansi"
    text_path = out / f"{name}.txt"
    ansi_path.write_bytes(data)
    evidence = rendered_marker_evidence(data, markers)
    text_path.write_text(evidence.pop("cleanText"))
    evidence.update({"ansi": str(ansi_path), "text": str(text_path), "bytes": len(data)})
    return evidence


def build_named_prompt(
    name,
    model,
    marker_dir,
    pre_read_markers,
    post_read_markers,
    grow_wait_marker,
    grow_release,
    finish_wait_marker,
    finish_release,
    final,
):
    read_prefix = pre_read_markers[0].rsplit("_", 1)[0] + "_"
    grow_command = (
        f"printf '%s\\n' {shlex.quote(grow_wait_marker)}; "
        f"until test -e {shlex.quote(str(grow_release))}; do sleep 0.2; done; "
        f"printf '%s\\n' {shlex.quote(grow_wait_marker + '_RELEASED')}"
    )
    finish_command = (
        f"printf '%s\\n' {shlex.quote(finish_wait_marker)}; "
        f"until test -e {shlex.quote(str(finish_release))}; do sleep 0.2; done; "
        f"printf '%s\\n' {shlex.quote(finish_wait_marker + '_RELEASED')}"
    )
    child_prompt = f"""This is a deterministic transcript rendering probe. Do exactly this work and nothing else.

1. Make exactly 30 sequential Read tool calls. Read one marker file per call from directory {marker_dir}. Each filename is the literal prefix {read_prefix}, followed immediately by a two-digit decimal suffix, followed by .marker. Cover every suffix from zero through twenty-nine in order. Wait for each Read result before issuing the next Read; never emit parallel tool calls. Do not use Bash, Glob, a loop, or another shortcut. Every file must be a separate real Read invocation.
2. Make exactly one Bash tool call with this exact command and wait for it:
{grow_command}
3. Make exactly {len(post_read_markers)} more sequential Read calls using the same rule, suffixes thirty through thirty-seven in order.
4. Make exactly one Bash tool call with this exact command and wait for it:
{finish_command}
5. Reply exactly {final} and stop. Do not call another tool."""
    return (
        f"Call the Agent tool exactly once with name={json.dumps(name)}, "
        f"subagent_type=\"general-purpose\", model={json.dumps(model)}, "
        "run_in_background=true, description=\"2.1.318 teammate transcript view probe\", "
        f"and prompt={json.dumps(child_prompt)}. Do not call another tool. Do not omit name. "
        "After the Agent launch result, reply exactly NAMED_PROBE_LAUNCHED and stop this turn; "
        "do not wait for the teammate."
    )


def build_plain_prompt(model, marker_dir, read_markers, wait_marker, release, final):
    read_prefix = read_markers[0].rsplit("_", 1)[0] + "_"
    wait_command = (
        f"printf '%s\\n' {shlex.quote(wait_marker)}; "
        f"until test -e {shlex.quote(str(release))}; do sleep 0.2; done; "
        f"printf '%s\\n' {shlex.quote(wait_marker + '_RELEASED')}"
    )
    child_prompt = f"""This is the plain background control. Do exactly this work and nothing else.

1. Make exactly four sequential Read calls, one per marker file in directory {marker_dir}. Each filename is the literal prefix {read_prefix}, then a two-digit suffix, then .marker. Cover suffixes zero through three in order. Never parallelize and do not use Bash, Glob, loops, or another shortcut.
2. Make exactly one Bash call with this exact command and wait for it:
{wait_command}
3. Reply exactly {final} and stop. Do not call another tool."""
    return (
        "Call the Agent tool exactly once WITHOUT name and WITHOUT team_name, with "
        f"subagent_type=\"general-purpose\", model={json.dumps(model)}, "
        "run_in_background=true, description=\"2.1.318 plain background control\", "
        f"and prompt={json.dumps(child_prompt)}. Do not call another tool. After the Agent launch "
        "result, reply exactly PLAIN_CONTROL_LAUNCHED and stop this turn; do not wait."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--system-prompt")
    parser.add_argument("--startup", type=float, default=12)
    parser.add_argument("--spawn-timeout", type=float, default=900)
    parser.add_argument("--finish-timeout", type=float, default=300)
    parser.add_argument("--capture-seconds", type=float, default=4)
    args = parser.parse_args()

    launcher = args.launcher.expanduser().resolve()
    cwd = args.cwd.expanduser().resolve()
    out = args.output.expanduser().resolve()
    require(launcher.is_file(), "launcher is not a file", str(launcher))
    cwd.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=False)
    config_dir = out / "config"
    config_dir.mkdir(mode=0o700)
    (config_dir / "settings.json").write_text("{}\n")
    (config_dir / ".claude.json").write_text(
        json.dumps(
            {
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "2.1.318",
                "projects": {str(cwd): {"hasTrustDialogAccepted": True}},
            }
        )
        + "\n"
    )

    session_id = str(uuid.uuid4())
    tag = uuid.uuid4().hex[:6]
    teammate_name = f"tv318{tag}"
    probe_dir = cwd / f".teammate-view-probe-{session_id}"
    marker_dir = probe_dir / "markers"
    grow_release = probe_dir / "grow-release"
    finish_release = probe_dir / "finish-release"
    plain_release = probe_dir / "plain-release"
    marker_dir.mkdir(parents=True)

    pre_read_markers = [f"TV318_{tag}_{index:02d}" for index in range(30)]
    grow_wait_marker = f"TV318_{tag}_GROW_WAIT"
    post_read_markers = [f"TV318_{tag}_{index:02d}" for index in range(30, 38)]
    named_read_markers = pre_read_markers + post_read_markers
    finish_wait_marker = f"TV318_{tag}_FINISH_WAIT"
    initial_named_markers = pre_read_markers + [grow_wait_marker]
    named_markers = initial_named_markers + post_read_markers + [finish_wait_marker]
    plain_read_markers = [f"PLAIN318_{tag}_{index:02d}" for index in range(4)]
    plain_wait_marker = f"PLAIN318_{tag}_WAIT"
    plain_markers = plain_read_markers + [plain_wait_marker]
    for marker in pre_read_markers + post_read_markers + plain_read_markers:
        (marker_dir / f"{marker}.marker").write_text(marker + "\n")

    named_final = f"TV318_{tag}_FINISHED"
    plain_final = f"PLAIN318_{tag}_FINISHED"
    subagents = project_dir(cwd, config_dir) / session_id / "subagents"
    parent_path = project_dir(cwd, config_dir) / f"{session_id}.jsonl"
    summary = {
        "version": "2.1.318",
        "launcher": str(launcher),
        "cwd": str(cwd),
        "output": str(out),
        "configDir": str(config_dir),
        "sessionId": session_id,
        "teammateName": teammate_name,
        "model": args.model,
        "permissionMode": "default",
        "allowedTools": ["Agent", "SendMessage", "Read", "Bash"],
        "systemPromptSupplied": args.system_prompt is not None,
        "namedExpectedToolCalls": len(named_markers),
        "plainExpectedToolCalls": len(plain_markers),
        "named": {},
        "plain": {},
        "pass": False,
    }
    session = None
    error = None

    try:
        argv = [
            str(launcher),
            "--session-id",
            session_id,
            "--model",
            args.model,
            "--teammate-mode",
            "in-process",
            "--permission-mode",
            "default",
            "--tools",
            "Agent,SendMessage,Read,Bash",
            "--allowedTools",
            "Agent,SendMessage,Read,Bash",
            "--strict-mcp-config",
            "--setting-sources",
            "project,local",
        ]
        if args.system_prompt is not None:
            argv += ["--system-prompt", args.system_prompt]
        summary["argv"] = argv
        print(f"session={session_id} teammate={teammate_name}", flush=True)
        session = PtySession(
            argv,
            cwd,
            clean_env(
                {
                    "CLAUDE_CONFIG_DIR": config_dir,
                    "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
                    "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN": "1",
                }
            ),
            out / "session-live.ansi",
        )
        session.read(args.startup)
        require(session.proc.poll() is None, "launcher exited during startup")

        session.line(
            build_named_prompt(
                teammate_name,
                args.model,
                marker_dir,
                pre_read_markers,
                post_read_markers,
                grow_wait_marker,
                grow_release,
                finish_wait_marker,
                finish_release,
                named_final,
            )
        )

        def named_running_ready():
            path = named_transcript(subagents, teammate_name)
            if not path:
                return None
            evidence = transcript_evidence(path, named_markers, named_final)
            wait_ids = evidence["markerToolIds"].get(grow_wait_marker, [])
            reads_complete = all(
                marker in evidence["completedMarkerTools"] for marker in pre_read_markers
            )
            wait_pending = bool(wait_ids) and all(
                tool_id not in evidence["toolResultIds"] for tool_id in wait_ids
            )
            if (
                evidence["toolCallCount"] >= len(initial_named_markers)
                and evidence["markerToolCount"] == len(initial_named_markers)
                and evidence["messageRowCount"] > 50
                and reads_complete
                and wait_pending
                and not evidence["finalMarkerInAssistant"]
            ):
                return path, evidence
            return None

        running = wait_until(session, args.spawn_timeout, named_running_ready)
        require(running, "named teammate did not reach controlled running checkpoint")
        named_path, running_evidence = running
        snapshot(named_path, out / "named-running-child.jsonl")
        summary["named"]["transcript"] = str(named_path)
        summary["named"]["runningJsonl"] = running_evidence
        require(
            running_evidence["messageRowCount"] > 50,
            "named child JSONL did not persist more than 50 rows before first open",
            running_evidence,
        )
        launches = agent_launches(parent_path)
        named_launches = [
            launch
            for launch in launches
            if launch["input"].get("name") == teammate_name
            and named_final in str(launch["input"].get("prompt", ""))
        ]
        require(
            len(named_launches) == 1,
            "parent JSONL does not prove one named teammate launch",
            launches,
        )
        summary["named"]["parentAgentLaunch"] = named_launches[0]
        require(
            not any(marker in named_launches[0]["input"]["prompt"] for marker in named_read_markers),
            "parent expanded exact Read markers into the teammate prompt",
        )
        require(
            not grow_release.exists() and not finish_release.exists() and not plain_release.exists(),
            "a release file existed before the running checkpoints",
        )
        require(
            transcript_evidence(parent_path, [], "NAMED_PROBE_LAUNCHED")["finalMarkerInAssistant"],
            "parent did not return to input after named launch",
        )

        session.line(
            build_plain_prompt(
                args.model,
                marker_dir,
                plain_read_markers,
                plain_wait_marker,
                plain_release,
                plain_final,
            )
        )

        def plain_running_ready():
            path = plain_transcript(subagents, named_path, plain_markers)
            if not path:
                return None
            evidence = transcript_evidence(path, plain_markers, plain_final)
            wait_ids = evidence["markerToolIds"].get(plain_wait_marker, [])
            reads_complete = all(
                marker in evidence["completedMarkerTools"] for marker in plain_read_markers
            )
            wait_pending = bool(wait_ids) and all(
                tool_id not in evidence["toolResultIds"] for tool_id in wait_ids
            )
            if (
                evidence["toolCallCount"] >= len(plain_markers)
                and evidence["markerToolCount"] == len(plain_markers)
                and reads_complete
                and wait_pending
                and not evidence["finalMarkerInAssistant"]
            ):
                return path, evidence
            return None

        plain_running = wait_until(session, args.spawn_timeout, plain_running_ready)
        require(plain_running, "plain background control did not reach wait checkpoint")
        plain_path, plain_running_evidence = plain_running
        snapshot(plain_path, out / "plain-running-child.jsonl")
        summary["plain"] = {
            "transcript": str(plain_path),
            "runningJsonl": plain_running_evidence,
            "withoutName": True,
        }
        launches = agent_launches(parent_path)
        plain_launches = [
            launch
            for launch in launches
            if plain_final in str(launch["input"].get("prompt", ""))
        ]
        require(
            len(plain_launches) == 1
            and "name" not in plain_launches[0]["input"]
            and "team_name" not in plain_launches[0]["input"],
            "parent JSONL does not prove one anonymous plain Agent launch",
            launches,
        )
        summary["plain"]["parentAgentLaunch"] = plain_launches[0]
        require(
            transcript_evidence(parent_path, [], "PLAIN_CONTROL_LAUNCHED")["finalMarkerInAssistant"],
            "parent did not return to input after plain launch",
        )

        def select_picker_row(target, artifact_name, expect_idle=False, require_probe_rows=True):
            session.drain()
            mark = session.mark()
            session.line("/tasks")
            found = session.read(10, until=target, since=mark)
            selected_data = None
            for _ in range(20):
                data = session.repaint_capture(0.4)
                text = strip_ansi(data)
                if expect_idle and re.search(
                    re.escape(teammate_name) + r"[^\n]*\bidle\b", text, re.I
                ) is None:
                    session.read(0.5)
                    continue
                if any(
                    "❯" in row and compact_text(target) in compact_text(row)
                    for row in text.splitlines()
                ):
                    selected_data = data
                    break
                session.write(b"\x1b[B")
                session.read(0.25)
            require(found, f"{target} was not rendered in /tasks")
            require(selected_data is not None, f"task picker did not select {target}")
            selected_text = strip_ansi(selected_data)
            if require_probe_rows:
                require(
                    f"@{teammate_name}" in selected_text
                    and "2.1.318plainbackgroundcontrol" in compact_text(selected_text),
                    "/tasks did not render both probe rows",
                )
            write_capture(out, artifact_name, selected_data, [])

        def open_task_view(target, artifact_name, markers, expect_idle=False):
            select_picker_row(target, f"{artifact_name}-tasks", expect_idle=expect_idle)
            session.write(b"f")
            session.read(2)
            session.write(b"\x0f")
            session.read(2)
            view_data = session.repaint_capture(args.capture_seconds)
            require(
                "Showingdetailedtranscript" in compact_text(strip_ansi(view_data)),
                "selected task did not open in the expanded transcript surface",
            )
            return write_capture(out, artifact_name, view_data, markers)

        def return_to_leader(label):
            # Escape interrupts a running teammate. Collapse with Ctrl+O and
            # select the leader through /tasks so retained-view state really ends.
            session.write(b"\x0f")
            session.read(1)
            select_picker_row("@team-lead", f"{label}-tasks", require_probe_rows=False)
            session.write(b"\r")
            session.read(2)
            write_capture(out, label, session.repaint_capture(0.5), [])

        def assert_rendered_view(view, expected_count, required_markers, label):
            require(
                not view["missingMarkers"],
                f"{label} is missing required Read/Bash tool rows",
                view,
            )
            require(
                view["distinctMarkerRowCount"] >= view["expectedMarkerCount"],
                f"{label} did not render distinct required tool rows",
                view,
            )
            require(
                view["renderedTranscriptRowCount"] >= expected_count,
                f"{label} rendered fewer transcript rows than JSONL tool calls",
                view,
            )
            require(
                all(marker in view["renderedMarkers"] for marker in required_markers),
                f"{label} lacks required early or late Read markers",
                view,
            )

        hydrated_view = open_task_view(
            f"@{teammate_name}", "named-hydrated-view", initial_named_markers
        )
        summary["named"]["hydratedView"] = hydrated_view
        assert_rendered_view(
            hydrated_view,
            running_evidence["toolCallCount"],
            [pre_read_markers[0], pre_read_markers[-1]],
            "initial hydrated teammate view",
        )

        grow_release.touch()

        def named_growth_ready():
            evidence = transcript_evidence(named_path, named_markers, named_final)
            grow_ids = evidence["markerToolIds"].get(grow_wait_marker, [])
            finish_ids = evidence["markerToolIds"].get(finish_wait_marker, [])
            grown_reads_complete = all(
                marker in evidence["completedMarkerTools"] for marker in post_read_markers
            )
            grow_complete = bool(grow_ids) and all(
                tool_id in evidence["toolResultIds"] for tool_id in grow_ids
            )
            finish_pending = bool(finish_ids) and all(
                tool_id not in evidence["toolResultIds"] for tool_id in finish_ids
            )
            if (
                evidence["toolCallCount"] >= len(named_markers)
                and evidence["markerToolCount"] == len(named_markers)
                and grown_reads_complete
                and grow_complete
                and finish_pending
                and not evidence["finalMarkerInAssistant"]
            ):
                return evidence
            return None

        growth_evidence = wait_until(session, args.spawn_timeout, named_growth_ready)
        require(growth_evidence, "named teammate did not reach live-growth checkpoint")
        snapshot(named_path, out / "named-growth-child.jsonl")
        summary["named"]["growthJsonl"] = growth_evidence
        live_growth_view = write_capture(
            out,
            "named-live-growth-view",
            session.repaint_capture(args.capture_seconds),
            named_markers,
        )
        summary["named"]["liveGrowthView"] = live_growth_view
        assert_rendered_view(
            live_growth_view,
            growth_evidence["toolCallCount"],
            [pre_read_markers[0], post_read_markers[-1]],
            "live-growth teammate view",
        )

        return_to_leader("return-to-leader-before-plain")
        plain_view = open_task_view(
            "2.1.318 plain background control",
            "plain-running-view",
            plain_markers,
        )
        summary["plain"]["runningView"] = plain_view
        assert_rendered_view(
            plain_view,
            plain_running_evidence["toolCallCount"],
            [plain_read_markers[0], plain_read_markers[-1]],
            "plain background agent view",
        )

        return_to_leader("return-to-leader-before-named")
        returned_named_view = open_task_view(
            f"@{teammate_name}", "named-returned-running-view", named_markers
        )
        summary["named"]["returnedRunningView"] = returned_named_view
        assert_rendered_view(
            returned_named_view,
            growth_evidence["toolCallCount"],
            [pre_read_markers[0], post_read_markers[-1]],
            "returned running teammate view",
        )

        return_to_leader("return-to-leader-before-finish")
        finish_release.touch()

        def named_finished_ready():
            evidence = transcript_evidence(named_path, named_markers, named_final)
            all_results = all(
                tool_id in evidence["toolResultIds"]
                for ids in evidence["markerToolIds"].values()
                for tool_id in ids
            )
            if (
                evidence["toolCallCount"] >= len(named_markers)
                and evidence["markerToolCount"] == len(named_markers)
                and all_results
                and evidence["finalMarkerInAssistant"]
            ):
                return evidence
            return None

        finished_evidence = wait_until(session, args.finish_timeout, named_finished_ready)
        require(finished_evidence, "named teammate did not finish off-view")
        snapshot(named_path, out / "named-child.jsonl")
        summary["named"]["finishedJsonl"] = finished_evidence

        finished_view = open_task_view(
            f"@{teammate_name}",
            "named-finished-reopen-view",
            named_markers,
            expect_idle=True,
        )
        summary["named"]["finishedReopenView"] = finished_view
        assert_rendered_view(
            finished_view,
            finished_evidence["toolCallCount"],
            [pre_read_markers[0], post_read_markers[-1]],
            "finished reopened teammate view",
        )
        finished_text = Path(finished_view["text"]).read_text()
        summary["named"]["renderedFinalAssistant"] = bool(
            re.search(
                r"^[ \t]*[⏺●]?[ \t]*" + re.escape(named_final) + r"[ \t]*$",
                finished_text,
                re.M,
            )
        )
        summary["named"]["renderedFinalToolResult"] = bool(
            re.search(
                r"^[ \t]*[⎿]?[ \t]*"
                + re.escape(finish_wait_marker + "_RELEASED")
                + r"[ \t]*$",
                finished_text,
                re.M,
            )
        )
        require(
            summary["named"]["renderedFinalAssistant"],
            "finished view lacks its final assistant row",
        )
        require(
            summary["named"]["renderedFinalToolResult"],
            "finished view lacks the completed final tool result",
        )
        return_to_leader("return-to-leader-after-finish")

        plain_release.touch()

        def plain_finished_ready():
            evidence = transcript_evidence(plain_path, plain_markers, plain_final)
            marker_ids = [
                tool_id
                for ids in evidence["markerToolIds"].values()
                for tool_id in ids
            ]
            if (
                evidence["toolCallCount"] >= len(plain_markers)
                and evidence["markerToolCount"] == len(plain_markers)
                and all(tool_id in evidence["toolResultIds"] for tool_id in marker_ids)
                and evidence["finalMarkerInAssistant"]
            ):
                return evidence
            return None

        plain_evidence = wait_until(session, args.finish_timeout, plain_finished_ready)
        require(plain_evidence, "plain background control did not finish after release")
        snapshot(plain_path, out / "plain-child.jsonl")
        summary["plain"]["finishedJsonl"] = plain_evidence
        require(session.proc.poll() is None, "launcher exited before cleanup")
        summary["parentAgentLaunches"] = agent_launches(parent_path)
        snapshot(parent_path, out / "parent.jsonl")
        summary["pass"] = True
    except Exception as exc:
        error = exc
        summary["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for release_path in (grow_release, finish_release, plain_release):
            try:
                release_path.touch(exist_ok=True)
            except OSError:
                pass
        if session is not None:
            try:
                summary["launcherExit"] = session.finish()
            except Exception as exc:
                summary["cleanupError"] = f"{type(exc).__name__}: {exc}"
            try:
                (out / "session.ansi").write_bytes(bytes(session.data))
                (out / "session.txt").write_text(strip_ansi(bytes(session.data)))
            except Exception as exc:
                summary["artifactError"] = f"{type(exc).__name__}: {exc}"
        try:
            if probe_dir.exists():
                trashed = subprocess.run(
                    ["trash", str(probe_dir)], capture_output=True, text=True
                )
                if trashed.returncode != 0:
                    summary["fixtureCleanupError"] = (
                        trashed.stderr.strip() or trashed.stdout.strip() or f"trash exit {trashed.returncode}"
                    )
        except OSError as exc:
            summary["fixtureCleanupError"] = str(exc)
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(json.dumps(summary, indent=2))
    if error is not None:
        print(f"teammate-view gate failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
