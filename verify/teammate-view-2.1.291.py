#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Real-PTY gate for the 2.1.291 teammate transcript view.

The gate starts one interactive launcher session with in-process teams enabled.
It asks the parent to create a named teammate that makes 30 separate Read calls
and blocks on a release-file Bash call.  The child's own JSONL proves all Read
results completed and the wait is still pending before the gate opens /tasks,
selects the teammate with Down+f, expands the transcript with Ctrl+O, and
captures the last full repaint epoch. Exact Read markers are absent from the
actual dispatch prompts, and every required marker must appear in a tool row.

While that named view stays open, the first release lets the child execute eight
more separately marked Read calls and block on a second release.  Another fresh
expanded repaint must retain all early rows and add every late row, proving the
view does not re-cap live growth.  The gate then views a concurrently held plain
background Agent (WITHOUT name/team_name) through /tasks and applies the same
JSONL-to-rendered-row proof. It returns to the named view, leaves it before
the final release, requires the named task's idle row in /tasks, and reopens it.
All historical markers, the final tool result and final assistant row must be
present. Rendered transcript rows must meet or exceed the actual tool-call count;
additional real calls (for example SendMessage to the lead) are not rejected.

summary.json, isolated final-epoch *.ansi captures, cleaned *.txt captures, and
parent/child JSONL snapshots are retained under --output.  Prompt echo and raw
ANSI redraw counts are never accepted as row evidence.  Cleanup releases only
this probe's wait files and signals only its owned launcher process group.
"""

import argparse
import fcntl
import json
import os
import pty
import re
import select
import shlex
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


def clean_env():
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION")
    }
    env["TERM"] = "xterm-256color"
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    return env


def project_dir(cwd):
    return PROJECTS / str(cwd).replace("/", "-").replace(".", "-")


def strip_ansi(data):
    text = ANSI.sub(b"", data).decode(errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compact_line(line):
    return re.sub(r"\s+", " ", line).strip()


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
            if marker not in row or row in seen_text or not re.search(r"\b(?:Read|Bash)\(", row):
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
        "renderedTranscriptRowCount": sum(bool(re.match(r"^[⏺●⎿]", row)) for row in rows),
        "renderedToolHeaderCount": sum(bool(re.match(r"^[⏺●]\s*[A-Za-z_][\w:.-]*\(", row)) for row in rows),
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
            if until and re.sub(r"\s+", "", until) in re.sub(r"\s+", "", self.text_since(since)):
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
            # A writer may be between write and newline while the gate polls.
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
                matched = [marker for marker in markers if marker in encoded_input]
                tool_uses.append(
                    {
                        "line": line_number,
                        "id": tool_id,
                        "name": block.get("name"),
                        "input": block.get("input"),
                        "markers": matched,
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
    result_ids = sorted(tool_results)
    return {
        "path": str(path) if path else None,
        "messageRowCount": message_row_count,
        "toolCallCount": len(tool_uses),
        "toolCalls": tool_uses,
        "toolResultIds": result_ids,
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
                {
                    "line": line_number,
                    "id": tool_id,
                    "input": block.get("input") or {},
                }
            )
    return launches


def named_transcript(base, name):
    matches = sorted(base.glob(f"agent-a{name}-*.jsonl"))
    return matches[0] if matches else None


def plain_transcript(base, named_path, markers):
    for path in sorted(base.glob("agent-*.jsonl")):
        if named_path and path == named_path:
            continue
        evidence = transcript_evidence(path, markers)
        if evidence["markerToolCount"]:
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


def write_capture(out, name, data, markers):
    ansi_path = out / f"{name}.ansi"
    text_path = out / f"{name}.txt"
    ansi_path.write_bytes(data)
    evidence = rendered_marker_evidence(data, markers)
    text_path.write_text(evidence.pop("cleanText"))
    evidence.update(
        {
            "ansi": str(ansi_path),
            "text": str(text_path),
            "bytes": len(data),
        }
    )
    return evidence


def require(condition, message, details=None):
    if not condition:
        if details is not None:
            message = f"{message}: {json.dumps(details, sort_keys=True)}"
        raise GateFailure(message)


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

1. Make exactly 30 sequential Read tool calls. Read one marker file per call from directory {marker_dir}. Each filename is the literal prefix {read_prefix}, followed immediately by a two-digit decimal suffix, followed by .marker. Cover every suffix from zero through twenty-nine in order. Wait for each Read result before issuing the next Read; never emit parallel tool calls. Do not use Bash, Glob, a loop, or any other shortcut. Every file must be a separate real Read invocation with its own tool_use id and its own persisted assistant/tool-result message pair.
2. After all 30 Read results have returned, make exactly one Bash tool call with this exact command and wait for it to finish:
{grow_command}
3. After that Bash result returns, make exactly {len(post_read_markers)} more sequential Read tool calls using the same directory and filename rule, covering suffixes thirty through thirty-seven in order. Wait for each result before issuing the next Read; never emit parallel tool calls.
4. After those Read results return, make exactly one Bash tool call with this exact command and wait for it to finish:
{finish_command}
5. After the second Bash result returns, reply exactly {final} and stop. Do not call any other tool.
"""
    return (
        f"Call the Agent tool exactly once with name={json.dumps(name)}, "
        f"subagent_type=\"general-purpose\", model={json.dumps(model)}, "
        "run_in_background=true, description=\"2.1.291 teammate transcript view probe\", "
        f"and prompt={json.dumps(child_prompt)}. "
        "Do not call any other tool. Do not omit name. After the Agent launch result, "
        "reply exactly NAMED_PROBE_LAUNCHED and stop this turn; do not wait for the teammate."
    )


def build_plain_prompt(model, marker_dir, read_markers, wait_marker, release, final):
    read_prefix = read_markers[0].rsplit("_", 1)[0] + "_"
    wait_command = (
        f"printf '%s\\n' {shlex.quote(wait_marker)}; "
        f"until test -e {shlex.quote(str(release))}; do sleep 0.2; done; "
        f"printf '%s\\n' {shlex.quote(wait_marker + '_RELEASED')}"
    )
    child_prompt = f"""This is the plain background control. Do exactly this work and nothing else.

1. Make exactly four sequential Read tool calls, one per marker file in directory {marker_dir}. Each filename is the literal prefix {read_prefix}, followed immediately by a two-digit decimal suffix, followed by .marker. Cover the first four non-negative suffixes in order. Wait for each Read result before issuing the next; never emit parallel tool calls. Do not use Bash, Glob, loops, or any other shortcut. Every file must be its own real invocation.
2. After all four Read results return, make exactly one Bash tool call with this exact command and wait for it to finish:
{wait_command}
3. After that Bash result returns, reply exactly {final} and stop. Do not call any other tool."""
    return (
        "Call the Agent tool exactly once WITHOUT name and WITHOUT team_name, with "
        f"subagent_type=\"general-purpose\", model={json.dumps(model)}, "
        "run_in_background=true, description=\"2.1.291 plain background control\", "
        f"and prompt={json.dumps(child_prompt)}. "
        "Do not call any other tool. After the Agent launch result, reply exactly "
        "PLAIN_CONTROL_LAUNCHED and stop this turn; do not wait for the subagent."
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

    session_id = str(uuid.uuid4())
    tag = uuid.uuid4().hex[:6]
    teammate_name = f"tv291{tag}"
    probe_dir = cwd / f".teammate-view-probe-{session_id}"
    marker_dir = probe_dir / "markers"
    grow_release = probe_dir / "grow-release"
    finish_release = probe_dir / "finish-release"
    plain_release = probe_dir / "plain-release"
    marker_dir.mkdir(parents=True)

    pre_read_markers = [f"TV291_{tag}_{index:02d}" for index in range(30)]
    grow_wait_marker = f"TV291_{tag}_GROW_WAIT"
    post_read_markers = [f"TV291_{tag}_{index:02d}" for index in range(30, 38)]
    named_read_markers = pre_read_markers + post_read_markers
    finish_wait_marker = f"TV291_{tag}_FINISH_WAIT"
    initial_named_markers = pre_read_markers + [grow_wait_marker]
    named_markers = (
        initial_named_markers + post_read_markers + [finish_wait_marker]
    )
    plain_read_markers = [f"PLAIN291_{tag}_{index:02d}" for index in range(4)]
    plain_wait_marker = f"PLAIN291_{tag}_WAIT"
    plain_markers = plain_read_markers + [plain_wait_marker]
    for marker in pre_read_markers + post_read_markers + plain_read_markers:
        (marker_dir / f"{marker}.marker").write_text(marker + "\n")

    named_final = f"TV291_{tag}_FINISHED"
    plain_final = f"PLAIN291_{tag}_FINISHED"
    subagents = project_dir(cwd) / session_id / "subagents"
    parent_path = project_dir(cwd) / f"{session_id}.jsonl"
    summary = {
        "version": "2.1.291",
        "launcher": str(launcher),
        "cwd": str(cwd),
        "output": str(out),
        "sessionId": session_id,
        "teammateName": teammate_name,
        "model": args.model,
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
            "bypassPermissions",
            "--tools",
            "Agent,SendMessage,Read,Bash",
            "--allowedTools",
            "Agent,SendMessage,Read,Bash",
            "--strict-mcp-config",
        ]
        if args.system_prompt is not None:
            argv += ["--system-prompt", args.system_prompt]
        summary["argv"] = argv
        print(f"session={session_id} teammate={teammate_name}", flush=True)
        session = PtySession(argv, cwd, clean_env(), out / "session-live.ansi")
        session.read(args.startup)
        require(session.proc.poll() is None, "launcher exited during startup")

        named_prompt = build_named_prompt(
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
        session.line(named_prompt)

        def named_running_ready():
            path = named_transcript(subagents, teammate_name)
            if not path:
                return None
            evidence = transcript_evidence(path, named_markers, named_final)
            wait_ids = evidence["markerToolIds"].get(grow_wait_marker, [])
            reads_complete = all(
                marker in evidence["completedMarkerTools"]
                for marker in pre_read_markers
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
        shutil.copyfile(named_path, out / "named-running-child.jsonl")
        summary["named"]["transcript"] = str(named_path)
        summary["named"]["runningJsonl"] = running_evidence
        require(
            running_evidence["messageRowCount"] > 50,
            "named child JSONL did not persist more than 50 user/assistant rows before first open",
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
            "parent JSONL does not prove one named teammate Agent launch",
            launches,
        )
        summary["named"]["parentAgentLaunch"] = named_launches[0]
        require(
            not any(marker in named_launches[0]["input"]["prompt"] for marker in named_read_markers),
            "parent expanded exact Read markers into the teammate prompt",
        )
        require(
            not grow_release.exists()
            and not finish_release.exists()
            and not plain_release.exists(),
            "a release file existed before the running checkpoints",
        )
        require(session.proc.poll() is None, "launcher exited before running capture")
        parent_named_turn = transcript_evidence(
            parent_path, [], "NAMED_PROBE_LAUNCHED"
        )
        require(
            parent_named_turn["finalMarkerInAssistant"],
            "parent did not return to input after named launch",
        )

        plain_prompt = build_plain_prompt(
            args.model,
            marker_dir,
            plain_read_markers,
            plain_wait_marker,
            plain_release,
            plain_final,
        )
        session.line(plain_prompt)

        def plain_running_ready():
            path = plain_transcript(subagents, named_path, plain_markers)
            if not path:
                return None
            evidence = transcript_evidence(path, plain_markers, plain_final)
            wait_ids = evidence["markerToolIds"].get(plain_wait_marker, [])
            reads_complete = all(
                marker in evidence["completedMarkerTools"]
                for marker in plain_read_markers
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

        plain_running = wait_until(
            session, args.spawn_timeout, plain_running_ready
        )
        require(plain_running, "plain background control did not reach wait checkpoint")
        plain_path, plain_running_evidence = plain_running
        shutil.copyfile(plain_path, out / "plain-running-child.jsonl")
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
            "parent JSONL does not prove one plain background Agent launch without name",
            launches,
        )
        summary["plain"]["parentAgentLaunch"] = plain_launches[0]
        require(
            not any(marker in plain_launches[0]["input"]["prompt"] for marker in plain_read_markers),
            "parent expanded exact Read markers into the plain prompt",
        )
        parent_plain_turn = transcript_evidence(
            parent_path, [], "PLAIN_CONTROL_LAUNCHED"
        )
        require(
            parent_plain_turn["finalMarkerInAssistant"],
            "parent did not return to input after plain launch",
        )

        def open_task_view(target, downs, artifact_name, markers, expect_idle=False):
            session.drain()
            tasks_mark = session.mark()
            session.line("/tasks")
            found = session.read(10, until=target, since=tasks_mark)
            if expect_idle:
                deadline = time.monotonic() + 30
                idle = False
                while time.monotonic() < deadline:
                    state = strip_ansi(session.repaint_capture(0.3))
                    if re.search(re.escape(teammate_name) + r"[^\n]*\bidle\b", state, re.I):
                        idle = True
                        break
                require(idle, "finished teammate did not show idle in /tasks")
            for _ in range(downs):
                session.write(b"\x1b[B")
                session.read(0.4)
            tasks_data = session.repaint_capture(0.5)
            tasks_text = strip_ansi(tasks_data)
            write_capture(out, f"{artifact_name}-tasks", tasks_data, [])
            require(found, f"{target} was not rendered in /tasks")
            require(
                f"@{teammate_name}" in tasks_text
                and "2.1.291plainbackgroundcontrol" in re.sub(r"\s+", "", tasks_text),
                "/tasks did not render both probe tasks as selectable rows",
            )
            require(
                any("❯" in row and re.sub(r"\s+", "", target) in re.sub(r"\s+", "", row) for row in tasks_text.splitlines()),
                "task picker did not select the requested row",
            )
            session.drain()
            session.write(b"f")
            session.read(2)
            # Ctrl+O expands collapsed Read/Search aggregation.  Count only a
            # fresh repaint epoch after expansion, never transition output or
            # repeated redraws accumulated across states.
            session.write(b"\x0f")
            session.read(2)
            view_data = session.repaint_capture(args.capture_seconds)
            require(
                "Showingdetailedtranscript" in re.sub(r"\s+", "", strip_ansi(view_data)),
                "selected task did not open in the expanded transcript surface",
            )
            return write_capture(out, artifact_name, view_data, markers)

        def return_to_leader():
            # Escape cancels a running teammate. Close expansion with Ctrl+O,
            # then select the leader through /tasks so retention really ends.
            session.write(b"\x0f")
            session.read(1)
            mark = session.mark()
            session.line("/tasks")
            session.read(3)
            picker = session.repaint_capture(0.5)
            require(
                any("❯" in row and "@team-lead" in row for row in strip_ansi(picker).splitlines()),
                "task picker did not select the leader row",
            )
            session.write(b"\r")
            session.read(2)
            write_capture(out, "return-to-leader", session.bytes_since(mark), [])

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

        # Source order is team leader, named teammate, then plain agent.
        hydrated_view = open_task_view(
            f"@{teammate_name}", 1, "named-hydrated-view", initial_named_markers
        )
        summary["named"]["hydratedView"] = hydrated_view
        assert_rendered_view(
            hydrated_view,
            running_evidence["toolCallCount"],
            [pre_read_markers[0], pre_read_markers[-1]],
            "initial hydrated teammate view",
        )

        # Keep the named view open while the teammate adds more tool rows.  A
        # cap accidentally re-applied to viewed transcripts loses early rows.
        grow_release.touch()

        def named_growth_ready():
            evidence = transcript_evidence(named_path, named_markers, named_final)
            grow_ids = evidence["markerToolIds"].get(grow_wait_marker, [])
            finish_ids = evidence["markerToolIds"].get(finish_wait_marker, [])
            grown_reads_complete = all(
                marker in evidence["completedMarkerTools"]
                for marker in post_read_markers
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

        growth_evidence = wait_until(
            session, args.spawn_timeout, named_growth_ready
        )
        require(growth_evidence, "named teammate did not reach live-growth checkpoint")
        shutil.copyfile(named_path, out / "named-growth-child.jsonl")
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

        # Exercise the unchanged plain background path through the real view
        # while it is still held on its release file.
        return_to_leader()
        plain_view = open_task_view(
            "2.1.291 plain background control",
            2,
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

        # Return to the named teammate before its final release.  This keeps
        # the second checkpoint running and verifies the expanded list survives
        # a view switch as well as live appends.
        return_to_leader()
        returned_named_view = open_task_view(
            f"@{teammate_name}",
            1,
            "named-returned-running-view",
            named_markers,
        )
        summary["named"]["returnedRunningView"] = returned_named_view
        assert_rendered_view(
            returned_named_view,
            growth_evidence["toolCallCount"],
            [pre_read_markers[0], post_read_markers[-1]],
            "returned running teammate view",
        )

        # Leave the view before completion.  The final proof must hydrate by
        # reopening /tasks after the teammate is idle/finished.
        return_to_leader()
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

        finished_evidence = wait_until(
            session, args.finish_timeout, named_finished_ready
        )
        require(finished_evidence, "named teammate did not finish off-view")
        shutil.copyfile(named_path, out / "named-child.jsonl")
        summary["named"]["finishedJsonl"] = finished_evidence

        finished_view = open_task_view(
            f"@{teammate_name}",
            1,
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
            re.search(r"^[ \t]*[⏺●]?[ \t]*" + re.escape(named_final) + r"[ \t]*$", finished_text, re.M)
        )
        summary["named"]["renderedFinalToolResult"] = bool(
            re.search(r"^[ \t]*[⎿]?[ \t]*" + re.escape(finish_wait_marker + "_RELEASED") + r"[ \t]*$", finished_text, re.M)
        )
        require(summary["named"]["renderedFinalAssistant"], "finished view lacks its final assistant row")
        require(summary["named"]["renderedFinalToolResult"], "finished view lacks the completed final tool result")
        return_to_leader()

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

        plain_evidence = wait_until(
            session, args.finish_timeout, plain_finished_ready
        )
        require(plain_evidence, "plain background control did not finish after release")
        shutil.copyfile(plain_path, out / "plain-child.jsonl")
        summary["plain"]["finishedJsonl"] = plain_evidence
        require(session.proc.poll() is None, "launcher exited before cleanup")
        launches = agent_launches(parent_path)
        summary["parentAgentLaunches"] = launches
        shutil.copyfile(parent_path, out / "parent.jsonl")

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
                shutil.rmtree(probe_dir)
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
