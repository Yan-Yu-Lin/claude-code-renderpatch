#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Interactive default-mode gate for 2.1.318 teammate background work.

This gate uses real PTYs, in-process teams, isolated project/local settings,
and ``default`` permission mode with an explicit allowed-tool set. It clears
all inherited child-session markers before every launch. Evidence comes from
saved lead/teammate/helper JSONL and owned process PIDs, not model summaries.

Cases:
  core      busy + idle background Agent/Bash, lead isolation, lead-owned Agent
  esc       Esc interrupts only the foreground turn; both background jobs live
  stop      TaskStop of a teammate stops its shell and Agent children
  resume    SendMessage-resumed helper remains owned by the teammate
  message   lead-to-busy-teammate delivery with and without inbox-wake hook
"""

import argparse
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
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
TOOLS = "Agent,Bash,SendMessage,TaskStop,Read,Write"


class GateFailure(RuntimeError):
    pass


def require(condition, message, evidence=None):
    if condition:
        return
    if evidence is None:
        raise GateFailure(message)
    raise GateFailure(f"{message}: {json.dumps(evidence, indent=2, default=str)}")


def strip_ansi(data):
    return ANSI.sub(b"", data).decode(errors="replace").replace("\r", "\n")


def project_dir(cwd):
    return PROJECTS / str(cwd).replace("/", "-").replace(".", "-")


def records(path):
    out = []
    try:
        with path.open() as handle:
            for line in handle:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return out


def text_of(record):
    message = record.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "tool_result":
            value = block.get("content")
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(
                    item.get("text", "")
                    for item in value
                    if isinstance(item, dict) and item.get("type") == "text"
                )
    return "\n".join(parts)


def conversation_text(path):
    parts = []
    for record in records(path):
        if record.get("type") in ("user", "assistant", "attachment"):
            parts.append(text_of(record))
            attachment = record.get("attachment")
            if isinstance(attachment, dict):
                prompt = attachment.get("prompt")
                if isinstance(prompt, str):
                    parts.append(prompt)
    return "\n".join(parts)

def assistant_text(path):
    return "\n".join(
        text_of(record) for record in records(path) if record.get("type") == "assistant"
    )


def peer_messages(path):
    messages = []
    for record in records(path):
        if record.get("type") != "attachment":
            continue
        attachment = record.get("attachment") or {}
        origin = attachment.get("origin") or {}
        if origin.get("kind") == "peer":
            messages.append(origin.get("body") or attachment.get("prompt") or "")
    return messages


def peer_message_contains(path, marker):
    return any(marker in message for message in peer_messages(path))


def tool_calls(path, name=None):
    calls = []
    for record in records(path):
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if name is None or block.get("name") == name:
                calls.append(
                    {
                        "timestamp": record.get("timestamp"),
                        "name": block.get("name"),
                        "id": block.get("id"),
                        "input": block.get("input") or {},
                    }
                )
    return calls


def marker_events(path, marker):
    events = []
    for record in records(path):
        raw = json.dumps(record, ensure_ascii=False)
        if marker in raw:
            events.append(
                {
                    "timestamp": record.get("timestamp"),
                    "type": record.get("type"),
                    "subtype": record.get("subtype"),
                }
            )
    return events


def child_entries(session_dir):
    out = []
    meta_paths = session_dir.glob("**/subagents/agent-*.meta.json")
    for meta_path in sorted(meta_paths):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        transcript = meta_path.with_suffix("").with_suffix(".jsonl")
        out.append({"metaPath": meta_path, "transcript": transcript, "meta": meta})
    return out


def entry_agent_id(entry):
    value = entry["meta"].get("agentId") or entry["meta"].get("resumableAgentId")
    if value:
        return value
    name = entry["metaPath"].name
    return name[len("agent-") : -len(".meta.json")]


def teammate_entry(session_dir, name):
    for entry in child_entries(session_dir):
        meta = entry["meta"]
        if meta.get("name") == name or meta.get("agentType") == name:
            return entry
    return None


def descendants(session_dir, parent_agent_id):
    return [
        entry
        for entry in child_entries(session_dir)
        if entry["meta"].get("parentAgentId") == parent_agent_id
    ]


def lead_path(session_dir):
    paths = sorted(
        path for path in session_dir.glob("**/*.jsonl") if "subagents" not in path.parts
    )
    return paths[0] if paths else None


def task_notification_contains(path, marker):
    if path is None:
        return False
    for record in records(path):
        if record.get("type") == "attachment":
            attachment = record.get("attachment") or {}
            if attachment.get("type") == "queued_command":
                prompt = attachment.get("prompt") or ""
                if "<task-notification>" in prompt and marker in prompt:
                    return True
        if record.get("type") != "user":
            continue
        text = text_of(record)
        if "<task-notification>" in text and marker in text:
            return True
    return False


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def clean_env():
    env = os.environ.copy()
    for key in (
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_AGENT_ID",
    ):
        env.pop(key, None)
    env["TERM"] = "xterm-256color"
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    env["UV_CACHE_DIR"] = "/Volumes/111360128 Lin Yan Yu/DevCache/uv"
    return env


class PtySession:
    def __init__(self, argv, cwd, capture, env):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 90, 180, 0, 0))
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
        self.capture = capture.open("wb", buffering=0)
        self.closed = False

    def mark(self):
        return len(self.data)

    def text(self, mark=0):
        return strip_ansi(bytes(self.data[mark:]))

    def pump(self, seconds):
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
            if self.proc.poll() is not None:
                break

    def write(self, data):
        while data:
            count = os.write(self.master, data)
            data = data[count:]

    def line(self, text):
        self.write(b"\x1b[200~" + text.encode() + b"\x1b[201~")
        self.pump(0.4)
        self.write(b"\r")

    def startup(self, seconds=12):
        self.pump(seconds)
        text = self.text()
        if re.search(r"trust.*folder|Yes, I trust|Trust this", text, re.I | re.S):
            self.write(b"\x1b[B\r")
            self.pump(4)
        require(self.proc.poll() is None, "launcher exited during startup", text[-2000:])

    def select_task(self, target):
        mark = self.mark()
        self.line("/tasks")
        self.pump(3)
        for _ in range(20):
            view = self.text(mark)
            rows = [re.sub(r"\s+", " ", row) for row in view.splitlines()]
            if any("❯" in row and target in row for row in rows):
                self.write(b"f")
                self.pump(2)
                return
            self.write(b"\x1b[B")
            self.pump(0.35)
        raise GateFailure(f"could not select @{target} in /tasks: {self.text(mark)[-4000:]}")

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    self.proc.kill()
                except ProcessLookupError:
                    pass
        self.capture.close()
        try:
            os.close(self.master)
        except OSError:
            pass


def wait_for(session, seconds, predicate):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        session.pump(min(1.5, max(0, deadline - time.monotonic())))
    return predicate()


def settings_file(config_dir, hook=None):
    settings = {
        "permissions": {"defaultMode": "default", "allow": TOOLS.split(",")},
        "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
    }
    if hook is not None:
        settings["hooks"] = {
            "PostToolBatch": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"/usr/bin/python3 {hook}",
                            "timeout": 5,
                        }
                    ]
                }
            ]
        }
    path = config_dir / "settings.json"
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def launch(args, out, label, hook=None):
    nonce = uuid.uuid4().hex[:8]
    case_dir = args.cwd / f"teammate-bg-318-{label}-{nonce}"
    case_dir.mkdir(parents=True)
    config_dir = out / f"{label}-config-{nonce}"
    config_dir.mkdir(mode=0o700)
    settings = settings_file(config_dir, hook)
    (config_dir / ".claude.json").write_text(
        json.dumps(
            {
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "2.1.318",
                "projects": {str(case_dir): {"hasTrustDialogAccepted": True}},
            }
        )
        + "\n"
    )
    session_id = str(uuid.uuid4())
    argv = [
        str(args.launcher),
        "--session-id",
        session_id,
        "--model",
        args.model,
        "--teammate-mode",
        "in-process",
        "--permission-mode",
        "default",
        "--tools",
        TOOLS,
        "--allowedTools",
        TOOLS,
        "--setting-sources",
        "project,local",
        "--settings",
        str(settings),
        "--strict-mcp-config",
    ]
    env = clean_env()
    env.update(
        {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED": "1",
            "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN": "1",
        }
    )
    session = PtySession(argv, case_dir, out / f"{label}.ansi", env)
    session.startup(args.startup)
    session_root = config_dir / "projects"
    return session, session_id, case_dir, session_root


CORE_PROMPT = """
Run this gate exactly. Spawn one named in-process teammate `bgcore` with model haiku and this prompt:
1. Start Bash in background: `sleep 10; echo BUSY_BASH_RESULT_318`, description `BGCORE_BUSY_BASH_318`.
2. Start an Agent helper in background (general-purpose, haiku), description `BGCORE_BUSY_AGENT_318`; it must run Bash `sleep 12` then reply exactly `BUSY_AGENT_RESULT_318`.
3. While those run, execute four separate foreground Bash calls `sleep 4; echo OWN_CALL_N_318` for N=1..4. When each background result arrives, SendMessage me `BUSY_BASH_SEEN_318` or `BUSY_AGENT_SEEN_318`.
4. Start Bash in background: `sleep 8; echo IDLE_BASH_RESULT_318`, description `BGCORE_IDLE_BASH_318`, and another background Agent `BGCORE_IDLE_AGENT_318` that sleeps 10 then replies `IDLE_AGENT_RESULT_318`.
5. SendMessage me `BGCORE_IDLE_ARMED_318`, then end the turn and wait idle. When each result wakes you, SendMessage me `IDLE_BASH_SEEN_318` or `IDLE_AGENT_SEEN_318`.
Do not ask questions and do not send task-notification XML to me.
Also launch your own unnamed background Agent, description `LEAD_OWN_AGENT_318`, which sleeps 6 and replies exactly `LEAD_OWN_RESULT_318`.
Wait using separate Bash `sleep 5` calls until you received all five report tokens from bgcore and your own Agent result, then reply exactly `CORE_GATE_DONE_318`. Do not stop bgcore.
""".strip()


ESC_PROMPT = """
Spawn one named in-process teammate `bgesc` with model haiku and this exact task:
- start background Bash `sleep 12; echo ESC_BASH_RESULT_318`, description `BGESC_BASH_318`;
- start background Agent helper (general-purpose, haiku), description `BGESC_AGENT_318`, that runs `sleep 14` then replies `ESC_AGENT_RESULT_318`;
- SendMessage the lead `ESC_READY_318`, then run foreground Bash `sleep 120; echo ESC_FOREGROUND_SHOULD_NOT_FINISH_318`.
If that foreground call is interrupted, do not stop either background task. Wait for both completion notifications and SendMessage the lead `ESC_BASH_SEEN_318` and `ESC_AGENT_SEEN_318`.
After spawning, reply `ESC_LEAD_WAITING_318` and remain available. Do not TaskStop anything.
""".strip()


RESUME_PROMPT = """
Spawn one named in-process teammate `bgresume` with model haiku and this exact task:
Launch one background Agent helper (general-purpose, haiku), description `BGRESUME_HELPER_318`, which replies exactly `RESUME_FIRST_318` without tools. When its completion notification arrives, use SendMessage to that helper's agent id with: `Reply exactly RESUME_SECOND_318 and stop.` Wait for the second completion notification, then SendMessage the lead `RESUME_OWNER_OK_318`. Do not send the helper report to the lead yourself.
Wait until bgresume sends `RESUME_OWNER_OK_318`, then reply exactly `RESUME_GATE_DONE_318`.
""".strip()


MESSAGE_PROMPT = """
Spawn one named in-process teammate `bgmessage` with model haiku and this exact task:
Run five separate foreground Bash calls in order: `sleep 4; echo MESSAGE_CALL_N_318` for N=1..5. Keep a counter of completed calls. If a lead message containing `MESSAGE_PING_318` arrives, immediately SendMessage the lead `MESSAGE_ACK_AFTER_CALL_N_318` using your current completed-call count, then finish any remaining calls. After call 5 SendMessage `MESSAGE_WORKER_DONE_318` and end the turn.
After spawning, run Bash `sleep 7`, then SendMessage bgmessage `MESSAGE_PING_318`. Wait until both ACK and DONE arrive, then reply exactly `MESSAGE_GATE_DONE_318`.
""".strip()


def run_core(args, out):
    session, sid, _, session_dir = launch(args, out, "core")
    try:
        session.line(CORE_PROMPT)
        done = wait_for(
            session,
            args.case_timeout,
            lambda: (lead_path(session_dir) and "CORE_GATE_DONE_318" in assistant_text(lead_path(session_dir))),
        )
        require(done, "core session did not finish")
        teammate = teammate_entry(session_dir, "bgcore")
        require(teammate is not None, "bgcore teammate transcript missing")
        lead = lead_path(session_dir)
        teammate_text = conversation_text(teammate["transcript"])
        lead_text = conversation_text(lead)
        expected = [
            "BUSY_BASH_RESULT_318",
            "BUSY_AGENT_RESULT_318",
            "IDLE_BASH_RESULT_318",
            "IDLE_AGENT_RESULT_318",
        ]
        routed = {marker: task_notification_contains(teammate["transcript"], marker) for marker in expected}
        isolated = {marker: not task_notification_contains(lead, marker) for marker in expected}
        reports = {
            marker: peer_message_contains(lead, marker)
            for marker in (
                "BUSY_BASH_SEEN_318",
                "BUSY_AGENT_SEEN_318",
                "IDLE_BASH_SEEN_318",
                "IDLE_AGENT_SEEN_318",
            )
        }
        lead_own = task_notification_contains(lead, "LEAD_OWN_RESULT_318")
        agent_calls = tool_calls(teammate["transcript"], "Agent")
        bash_calls = tool_calls(teammate["transcript"], "Bash")
        require(all(routed.values()), "core notifications did not route to teammate", routed)
        require(all(isolated.values()), "lead saw teammate child task notification", isolated)
        require(all(reports.values()), "teammate did not report all busy/idle results", reports)
        require(lead_own, "lead-owned background Agent did not notify lead")
        require(any(call["input"].get("run_in_background") is True for call in agent_calls), "teammate background Agent call missing", agent_calls)
        require(sum(call["input"].get("run_in_background") is True for call in bash_calls) >= 2, "teammate background Bash calls missing", bash_calls)
        return {
            "session": sid,
            "teammate": teammate["meta"],
            "routed": routed,
            "leadIsolation": isolated,
            "reports": reports,
            "leadOwnBackground": lead_own,
        }
    finally:
        session.close()


def run_esc(args, out):
    session, sid, _, session_dir = launch(args, out, "esc")
    try:
        session.line(ESC_PROMPT)
        teammate = wait_for(session, 120, lambda: teammate_entry(session_dir, "bgesc"))
        require(teammate is not None, "bgesc teammate missing")
        ready = wait_for(
            session,
            120,
            lambda: peer_message_contains(lead_path(session_dir), "ESC_READY_318") if lead_path(session_dir) else False,
        )
        require(ready, "bgesc did not arm background work")
        foreground = wait_for(
            session,
            60,
            lambda: any(
                "ESC_FOREGROUND_SHOULD_NOT_FINISH_318" in str(call["input"].get("command", ""))
                for call in tool_calls(teammate["transcript"], "Bash")
            ),
        )
        require(foreground, "bgesc foreground Bash was not running")
        session.select_task("bgesc")
        session.write(b"\x1b")
        session.pump(2)
        if "Request interrupted by user" not in conversation_text(teammate["transcript"]):
            session.write(b"\x1b")
            session.pump(2)
        interrupted = wait_for(
            session,
            30,
            lambda: "Request interrupted by user" in conversation_text(teammate["transcript"]),
        )
        require(interrupted, "Esc did not interrupt teammate foreground turn")
        both = wait_for(
            session,
            args.case_timeout,
            lambda: all(
                peer_message_contains(lead_path(session_dir), marker)
                for marker in ("ESC_BASH_SEEN_318", "ESC_AGENT_SEEN_318")
            ) if lead_path(session_dir) else False,
        )
        require(both, "Esc background tasks did not survive and report")
        require(
            "ESC_FOREGROUND_SHOULD_NOT_FINISH_318" not in conversation_text(teammate["transcript"]).split("Request interrupted by user")[-1],
            "interrupted foreground Bash appears to have finished",
        )
        return {
            "session": sid,
            "interrupted": True,
            "bashSurvived": task_notification_contains(teammate["transcript"], "ESC_BASH_RESULT_318"),
            "agentSurvived": task_notification_contains(teammate["transcript"], "ESC_AGENT_RESULT_318"),
        }
    finally:
        session.close()


def run_resume(args, out):
    session, sid, _, session_dir = launch(args, out, "resume")
    try:
        session.line(RESUME_PROMPT)
        done = wait_for(
            session,
            args.case_timeout,
            lambda: (lead_path(session_dir) and "RESUME_GATE_DONE_318" in assistant_text(lead_path(session_dir))),
        )
        require(done, "resume ownership case did not finish")
        teammate = teammate_entry(session_dir, "bgresume")
        require(teammate is not None, "bgresume teammate missing")
        lead = lead_path(session_dir)
        teammate_first = task_notification_contains(teammate["transcript"], "RESUME_FIRST_318")
        teammate_second = task_notification_contains(teammate["transcript"], "RESUME_SECOND_318")
        lead_first = task_notification_contains(lead, "RESUME_FIRST_318")
        lead_second = task_notification_contains(lead, "RESUME_SECOND_318")
        require(teammate_first and teammate_second, "resumed helper notifications did not return to teammate")
        require(not lead_first and not lead_second, "resumed helper notification leaked to lead")
        return {
            "session": sid,
            "firstAtTeammate": teammate_first,
            "secondAtTeammate": teammate_second,
            "leadIsolation": not lead_first and not lead_second,
        }
    finally:
        session.close()


def run_stop(args, out):
    pid_file = out / "stop-shell.pid"
    prompt = f"""
Spawn one named in-process teammate `bgstop` with model haiku and this exact task:
Start background Bash `echo $$ > {pid_file}; sleep 300`, description `BGSTOP_SHELL_318`. Start a background Agent helper (general-purpose, haiku), description `BGSTOP_AGENT_318`, that runs Bash `sleep 300`. SendMessage the lead `STOP_CHILDREN_ARMED_318`, then run foreground Bash `sleep 300`.
When you receive STOP_CHILDREN_ARMED_318, immediately call TaskStop on the bgstop teammate task. Then reply exactly STOP_GATE_DONE_318. Do not separately stop either child.
""".strip()
    session, sid, _, session_dir = launch(args, out, "stop")
    try:
        session.line(prompt)
        armed = wait_for(
            session,
            150,
            lambda: pid_file.exists() and teammate_entry(session_dir, "bgstop"),
        )
        require(armed, "stop case did not arm children")
        teammate = teammate_entry(session_dir, "bgstop")
        parent_id = entry_agent_id(teammate)
        helper = wait_for(
            session,
            90,
            lambda: next(
                (
                    entry
                    for entry in descendants(session_dir, parent_id)
                    if entry["meta"].get("description") == "BGSTOP_AGENT_318"
                    and any(
                        "sleep 300" in str(call["input"].get("command", ""))
                        for call in tool_calls(entry["transcript"], "Bash")
                    )
                ),
                None,
            ),
        )
        require(helper is not None, "teammate Agent child did not start its long Bash")
        done = wait_for(
            session,
            args.case_timeout,
            lambda: (
                lead_path(session_dir)
                and "STOP_GATE_DONE_318" in assistant_text(lead_path(session_dir))
            ),
        )
        require(done, "lead did not TaskStop teammate")
        shell_pid = read_pid(pid_file)
        shell_stopped = wait_for(
            session, 30, lambda: shell_pid is not None and not pid_alive(shell_pid)
        )
        lead = lead_path(session_dir)
        helper_stopped = wait_for(
            session,
            30,
            lambda: task_notification_contains(lead, "BGSTOP_AGENT_318"),
        )
        shell_notified = task_notification_contains(lead, "BGSTOP_SHELL_318")
        require(shell_stopped, "TaskStop left teammate shell process alive", shell_pid)
        require(helper_stopped, "TaskStop did not stop/forward teammate Agent child")
        return {
            "session": sid,
            "shellPid": shell_pid,
            "shellStopped": shell_stopped,
            "shellStopNotified": shell_notified,
            "helper": helper["meta"],
            "helperStopped": helper_stopped,
        }
    finally:
        session.close()


def message_ack_number(lead):
    hits = []
    for message in peer_messages(lead):
        hits.extend(re.findall(r"MESSAGE_ACK_AFTER_CALL_(\d+)_318", message))
    return int(hits[-1]) if hits else None


def run_message(args, out, label, hook):
    session, sid, _, session_dir = launch(args, out, label, hook)
    try:
        session.line(MESSAGE_PROMPT)
        done = wait_for(
            session,
            args.case_timeout,
            lambda: (lead_path(session_dir) and "MESSAGE_GATE_DONE_318" in assistant_text(lead_path(session_dir))),
        )
        require(done, f"{label} message case did not finish")
        teammate = teammate_entry(session_dir, "bgmessage")
        require(teammate is not None, f"{label} teammate missing")
        lead = lead_path(session_dir)
        number = message_ack_number(lead)
        require(number is not None, f"{label} ACK missing")
        return {
            "session": sid,
            "ackAfterCall": number,
            "workerDone": peer_message_contains(lead, "MESSAGE_WORKER_DONE_318"),
        }
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--startup", type=float, default=12)
    parser.add_argument("--case-timeout", type=float, default=360)
    parser.add_argument(
        "--only",
        action="append",
        choices=("core", "esc", "stop", "resume", "message"),
    )
    parser.add_argument(
        "--inbox-hook",
        type=Path,
        default=HOME / ".claude/hooks/teammate_inbox_wake.py",
    )
    args = parser.parse_args()
    args.launcher = args.launcher.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    args.cwd = args.cwd.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    args.cwd.mkdir(parents=True, exist_ok=True)
    require(args.launcher.exists(), "launcher missing", args.launcher)
    selected = set(args.only or ("core", "esc", "stop", "resume", "message"))
    if "message" in selected:
        require(args.inbox_hook.exists(), "inbox-wake hook missing", args.inbox_hook)

    summary = {"version": "2.1.318", "permissionMode": "default", "cases": {}}
    error = None
    try:
        if "core" in selected:
            summary["cases"]["core"] = run_core(args, args.output)
        if "esc" in selected:
            summary["cases"]["esc"] = run_esc(args, args.output)
        if "stop" in selected:
            summary["cases"]["stop"] = run_stop(args, args.output)
        if "resume" in selected:
            summary["cases"]["resume"] = run_resume(args, args.output)
        if "message" in selected:
            nohook = run_message(args, args.output, "message-nohook", None)
            hook = run_message(args, args.output, "message-hook", args.inbox_hook)
            require(hook["ackAfterCall"] < 5, "hook did not deliver before turn end", hook)
            require(nohook["ackAfterCall"] >= 5, "no-hook delivery changed from upstream turn-end behavior", nohook)
            summary["cases"]["messageNoHook"] = nohook
            summary["cases"]["messageHook"] = hook
        summary["ok"] = True
    except Exception as exc:
        error = exc
        summary["ok"] = False
        summary["error"] = str(exc)
    finally:
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    print(json.dumps(summary, indent=2, default=str))
    if error is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
