#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral stream-json gates for resumable stopped agents on 2.1.318.

All seven scenarios run in ``default`` permission mode with only Agent,
SendMessage, and Bash exposed and allowed. ``--setting-sources project,local``
keeps user settings and user hooks out of the gate. Each session also clears
inherited child-session markers so its transcript is persisted.

The assertions are behavioral: child transcript continuation, stop-marker
state, absence of automatic task starts/transcript growth, and completion
notification delivery. No scenario depends on incidental notice wording.

Scenarios:

* taskstop: explicit stop_task, then SendMessage by id in the same process.
* interrupt: SDK interrupt, then SendMessage by id in the same process.
* restart: stop and restart, resume by id, stop again, restart, resume by name.
* noauto: a stopped agent stays stopped across restart without SendMessage.
* orphan: interrupt plus immediate close; restart does not resurrect it, but an
  explicit SendMessage does.
* grouped: two stopped orphans remain stopped together, then each resumes only
  after its own explicit SendMessage.
* wakeafter: after explicit revival, the child's normal completion notification
  reaches the parent and the stale stoppedByUser marker is gone.
"""

import argparse
import json
import os
import select
import subprocess
import time
import uuid
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude/projects"
IDLE_COMMAND = "python3 -c 'import time; time.sleep(900)'"


def project_dir(cwd):
    return PROJECTS / str(cwd).replace("/", "-").replace(".", "-")


class Session:
    def __init__(self, argv, cwd, log, env):
        self.log = log
        self.events = []
        self.proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.buf = b""
        self.req = 0

    def send(self, obj):
        line = json.dumps(obj) + "\n"
        self.log.write("> " + line)
        self.log.flush()
        self.proc.stdin.write(line.encode())
        self.proc.stdin.flush()

    def user(self, text):
        self.send(
            {
                "type": "user",
                "message": {"role": "user", "content": text},
                "parent_tool_use_id": None,
                "session_id": "",
            }
        )

    def control(self, request):
        self.req += 1
        rid = f"rp-{self.req}"
        self.send({"type": "control_request", "request_id": rid, "request": request})
        return rid

    def pump(self, seconds, until=None):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [self.proc.stdout, self.proc.stderr], [], [], min(0.2, max(0, deadline - time.monotonic()))
            )
            for stream in ready:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    continue
                if stream is self.proc.stderr:
                    self.log.write("! " + chunk.decode(errors="replace"))
                    continue
                self.buf += chunk
                while b"\n" in self.buf:
                    raw, self.buf = self.buf.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    self.log.write("< " + raw.decode(errors="replace") + "\n")
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    self.events.append(ev)
                    if until and until(ev):
                        self.log.flush()
                        return ev
            if self.proc.poll() is not None and not ready:
                break
        self.log.flush()
        return None

    def wait_result(self, seconds):
        return self.pump(seconds, lambda e: e.get("type") == "result")

    def close(self):
        try:
            self.proc.stdin.close()
        except (BrokenPipeError, AttributeError):
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.flush()
        self.log.close()


def tool_results(events):
    out = []
    for event in events:
        if event.get("type") != "user":
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            value = block.get("content")
            if isinstance(value, list):
                value = "".join(
                    item.get("text", "") for item in value if isinstance(item, dict)
                )
            out.append(str(value))
    return out


def find_agent_id(events):
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "task_started":
            if event.get("task_type") == "local_agent":
                return event.get("task_id")
    for text in tool_results(events):
        if "agentId:" in text:
            return text.split("agentId:", 1)[1].split()[0].strip(" .,)")
    return None


def agent_files(cwd, session_id, agent_id):
    base = project_dir(cwd) / session_id / "subagents"
    return base / f"agent-{agent_id}.jsonl", base / f"agent-{agent_id}.meta.json"


def line_count(path):
    try:
        with path.open() as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def read_meta(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def stopped(meta):
    return isinstance(meta, dict) and meta.get("stoppedByUser") is True


def marker_lines(path, marker):
    hits = []
    try:
        with path.open() as handle:
            for number, line in enumerate(handle, 1):
                if marker not in line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") == "assistant":
                    hits.append(number)
    except OSError:
        pass
    return hits

def bash_command_count(path, command):
    count = 0
    try:
        with path.open() as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "assistant":
                    continue
                content = (record.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("name") == "Bash"
                        and isinstance(block.get("input"), dict)
                        and block["input"].get("command") == command
                    ):
                        count += 1
    except OSError:
        return 0
    return count


def wait_condition(session, seconds, predicate):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        session.pump(min(2, max(0, deadline - time.monotonic())))
    return predicate()


SPAWN = (
    'Call the Agent tool exactly once with name="{name}", subagent_type="general-purpose", '
    'model="sonnet", run_in_background=true, description="resume gate {name}", and prompt: '
    f'"Run the Bash command `{IDLE_COMMAND}` (timeout 900000) in the foreground and wait for it. '
    "If you are ever resumed with a new message, do not run the idle command again; reply exactly with "
    'the token that message asks for and stop." '
    "Then reply exactly SPAWNED and stop. Do not do anything else."
)
RESUME = (
    'Call the SendMessage tool exactly once with to="{to}" and message="You were resumed. '
    'Reply exactly {token} and stop. Do not run any tools." Then reply exactly with the full '
    "text of the SendMessage tool result and stop. Do not retry and do not call any other tool."
)
RESTART_FOR_STOP = (
    'Call the SendMessage tool exactly once with to="{to}" and message="For this gate step, '
    'ignore the earlier instruction not to run the idle command again. Run the Bash command '
    f'`{IDLE_COMMAND}` (timeout 900000) in the foreground and wait for it. Do not reply before '
    'the command ends." Then reply exactly with the full text of the SendMessage tool result '
    "and stop. Do not retry and do not call any other tool."
)


def start(args, session_id, resume=False):
    argv = [
        str(args.launcher),
        "--print",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        "sonnet",
        "--permission-mode",
        "default",
        "--tools",
        "Agent,SendMessage,Bash",
        "--allowedTools",
        "Agent,SendMessage,Bash",
        "--setting-sources",
        "project,local",
        "--strict-mcp-config",
    ]
    argv += ["--resume", session_id] if resume else ["--session-id", session_id]
    env = os.environ.copy()
    for key in [
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_AGENT_ID",
    ]:
        env.pop(key, None)
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["CLAUDE_CONFIG_DIR"] = str(args.config_dir)
    env["CLAUDE_CODE_DISABLE_HOME_SETTINGS_SEED"] = "1"
    env["UV_CACHE_DIR"] = "/Volumes/111360128 Lin Yan Yu/DevCache/uv"
    return argv, env


def spawn_and_stop(args, out, name, how):
    session_id = str(uuid.uuid4())
    log = (out / f"{name}.log").open("w")
    argv, env = start(args, session_id)
    session = Session(argv, args.cwd, log, env)
    session.user(SPAWN.format(name=name))
    session.wait_result(240)
    agent = find_agent_id(session.events)
    record = {"session": session_id, "agent": agent, "how": how}
    if not agent:
        record["error"] = "no agent spawned"
        return session, record
    transcript, meta = agent_files(args.cwd, session_id, agent)
    record["childStartedSleep"] = bool(
        wait_condition(
            session,
            120,
            lambda: bash_command_count(transcript, IDLE_COMMAND) >= 1,
        )
    )
    if how == "stop_task":
        session.control({"subtype": "stop_task", "task_id": agent})
    else:
        session.control({"subtype": "interrupt"})
    wait_condition(session, 30, lambda: stopped(read_meta(meta)))
    record["metaAfterStop"] = read_meta(meta)
    record["stoppedEvent"] = any(
        event.get("type") == "system"
        and event.get("subtype") in ("task_notification", "task_updated")
        and event.get("task_id") == agent
        for event in session.events
    )
    return session, record


def resume_in(session, to, token):
    before = len(session.events)
    session.user(RESUME.format(to=to, token=token))
    session.wait_result(240)
    return [text[:600] for text in tool_results(session.events[before:])]

def restart_for_stop(session, to):
    before = len(session.events)
    session.user(RESTART_FOR_STOP.format(to=to))
    session.wait_result(240)
    return [text[:600] for text in tool_results(session.events[before:])]


def wait_marker(session, path, marker, seconds):
    return wait_condition(session, seconds, lambda: marker_lines(path, marker)) or []


def auto_started(events, agent):
    return any(
        event.get("type") == "system"
        and event.get("subtype") == "task_started"
        and event.get("task_id") == agent
        for event in events
    )


def scenario_inproc(args, out, how, label):
    session, record = spawn_and_stop(args, out, label, how)
    if "error" in record:
        session.close()
        return record
    token = f"RESUMED_{label.upper()}_OK"
    record["sendMessageResult"] = resume_in(session, record["agent"], token)
    transcript, meta = agent_files(args.cwd, record["session"], record["agent"])
    record["childMarkerLines"] = wait_marker(session, transcript, token, 180)
    session.pump(5)
    record["metaAfterResume"] = read_meta(meta)
    session.close()
    record["pass"] = (
        record["childStartedSleep"]
        and stopped(record["metaAfterStop"])
        and bool(record["childMarkerLines"])
        and not stopped(record["metaAfterResume"])
    )
    return record


def scenario_restart(args, out):
    label = "restartgate"
    session, record = spawn_and_stop(args, out, label, "stop_task")
    session.close()
    if "error" in record:
        return record
    session_id, agent = record["session"], record["agent"]
    transcript, meta = agent_files(args.cwd, session_id, agent)

    log = (out / f"{label}-byid.log").open("w")
    argv, env = start(args, session_id, resume=True)
    by_id = Session(argv, args.cwd, log, env)
    token = "RESUMED_BYID_OK"
    record["byIdResult"] = resume_in(by_id, agent, token)
    record["byIdMarkerLines"] = wait_marker(by_id, transcript, token, 180)
    record["metaAfterById"] = read_meta(meta)
    record["secondRunResult"] = restart_for_stop(by_id, agent)
    record["secondIdleCommandStarted"] = bool(
        wait_condition(
            by_id,
            120,
            lambda: bash_command_count(transcript, IDLE_COMMAND) >= 2,
        )
    )
    by_id.control({"subtype": "stop_task", "task_id": agent})
    wait_condition(by_id, 30, lambda: stopped(read_meta(meta)))
    record["metaBeforeByName"] = read_meta(meta)
    by_id.close()

    log = (out / f"{label}-byname.log").open("w")
    argv, env = start(args, session_id, resume=True)
    by_name = Session(argv, args.cwd, log, env)
    token = "RESUMED_BYNAME_OK"
    record["byNameResult"] = resume_in(by_name, label, token)
    record["byNameMarkerLines"] = wait_marker(by_name, transcript, token, 180)
    record["metaAfterByName"] = read_meta(meta)
    by_name.close()

    record["pass"] = (
        record["childStartedSleep"]
        and stopped(record["metaAfterStop"])
        and bool(record["byIdMarkerLines"])
        and not stopped(record["metaAfterById"])
        and record["secondIdleCommandStarted"]
        and stopped(record["metaBeforeByName"])
        and bool(record["byNameMarkerLines"])
        and not stopped(record["metaAfterByName"])
    )
    return record


def scenario_noauto(args, out):
    label = "noautogate"
    session, record = spawn_and_stop(args, out, label, "stop_task")
    session.close()
    if "error" in record:
        return record
    session_id, agent = record["session"], record["agent"]
    transcript, meta = agent_files(args.cwd, session_id, agent)
    before = line_count(transcript)

    log = (out / f"{label}-resume.log").open("w")
    argv, env = start(args, session_id, resume=True)
    resumed = Session(argv, args.cwd, log, env)
    resumed.user("Reply exactly IDLE_CHECK and stop. Do not call any tool.")
    resumed.wait_result(180)
    resumed.pump(45)
    after = line_count(transcript)
    record["childLinesBefore"] = before
    record["childLinesAfter"] = after
    record["taskStartedForAgent"] = auto_started(resumed.events, agent)
    record["metaAfterIdleRestart"] = read_meta(meta)
    resumed.close()
    record["pass"] = (
        record["childStartedSleep"]
        and stopped(record["metaAfterStop"])
        and before == after
        and not record["taskStartedForAgent"]
        and stopped(record["metaAfterIdleRestart"])
    )
    return record


def scenario_orphan(args, out):
    label = "orphangate"
    session_id = str(uuid.uuid4())
    log = (out / f"{label}.log").open("w")
    argv, env = start(args, session_id)
    session = Session(argv, args.cwd, log, env)
    session.user(SPAWN.format(name=label))
    session.wait_result(240)
    agent = find_agent_id(session.events)
    record = {"session": session_id, "agent": agent, "how": "interrupt+close"}
    if not agent:
        record["error"] = "no agent spawned"
        session.close()
        return record
    transcript, meta = agent_files(args.cwd, session_id, agent)
    record["childStartedSleep"] = bool(
        wait_condition(
            session,
            120,
            lambda: bash_command_count(transcript, IDLE_COMMAND) >= 1,
        )
    )
    session.control({"subtype": "interrupt"})
    session.close()
    record["metaAfterStop"] = read_meta(meta)
    before = line_count(transcript)

    log = (out / f"{label}-resume.log").open("w")
    argv, env = start(args, session_id, resume=True)
    resumed = Session(argv, args.cwd, log, env)
    resumed.user("Reply exactly IDLE_CHECK and stop. Do not call any tool.")
    resumed.wait_result(180)
    resumed.pump(30)
    idle_events = list(resumed.events)
    after_idle = line_count(transcript)
    record["childLinesBefore"] = before
    record["childLinesAfterIdle"] = after_idle
    record["taskStartedBeforeSendMessage"] = auto_started(idle_events, agent)
    record["metaAfterIdleRestart"] = read_meta(meta)

    token = "RESUMED_ORPHAN_OK"
    record["sendMessageResult"] = resume_in(resumed, agent, token)
    record["childMarkerLines"] = wait_marker(resumed, transcript, token, 180)
    record["metaAfterResume"] = read_meta(meta)
    resumed.close()
    record["pass"] = (
        record["childStartedSleep"]
        and stopped(record["metaAfterStop"])
        and after_idle == before
        and not record["taskStartedBeforeSendMessage"]
        and stopped(record["metaAfterIdleRestart"])
        and bool(record["childMarkerLines"])
        and not stopped(record["metaAfterResume"])
    )
    return record


def scenario_grouped(args, out):
    session_id = str(uuid.uuid4())
    log = (out / "groupedgate.log").open("w")
    argv, env = start(args, session_id)
    session = Session(argv, args.cwd, log, env)
    agents = []
    for name in ("groupa", "groupb"):
        before_events = len(session.events)
        session.user(SPAWN.format(name=name))
        session.wait_result(240)
        agents.append(find_agent_id(session.events[before_events:]))
    record = {"session": session_id, "agents": agents}
    if None in agents:
        record["error"] = "spawn failed"
        session.close()
        return record

    started = {}
    for agent in agents:
        transcript, _ = agent_files(args.cwd, session_id, agent)
        started[agent] = bool(
            wait_condition(
                session,
                120,
                lambda path=transcript: bash_command_count(path, IDLE_COMMAND) >= 1,
            )
        )
    record["childStartedSleep"] = started
    for agent in agents:
        session.control({"subtype": "stop_task", "task_id": agent})
    session.close()

    transcripts = {agent: agent_files(args.cwd, session_id, agent)[0] for agent in agents}
    metas = {agent: agent_files(args.cwd, session_id, agent)[1] for agent in agents}
    before = {agent: line_count(transcripts[agent]) for agent in agents}
    record["metaAfterStop"] = {agent: read_meta(metas[agent]) for agent in agents}

    log = (out / "groupedgate-resume.log").open("w")
    argv, env = start(args, session_id, resume=True)
    resumed = Session(argv, args.cwd, log, env)
    resumed.user("Reply exactly IDLE_CHECK and stop. Do not call any tool.")
    resumed.wait_result(180)
    resumed.pump(30)
    idle_events = list(resumed.events)
    after_idle = {agent: line_count(transcripts[agent]) for agent in agents}
    record["childLinesBefore"] = before
    record["childLinesAfterIdle"] = after_idle
    record["taskStartedBeforeSendMessage"] = {
        agent: auto_started(idle_events, agent) for agent in agents
    }
    record["metaAfterIdleRestart"] = {
        agent: read_meta(metas[agent]) for agent in agents
    }

    marker_lines_by_agent = {}
    send_results = {}
    for index, agent in enumerate(agents, 1):
        token = f"RESUMED_GROUP_{index}_OK"
        send_results[agent] = resume_in(resumed, agent, token)
        marker_lines_by_agent[agent] = wait_marker(
            resumed, transcripts[agent], token, 180
        )
    record["sendMessageResults"] = send_results
    record["childMarkerLines"] = marker_lines_by_agent
    record["metaAfterResume"] = {
        agent: read_meta(metas[agent]) for agent in agents
    }
    resumed.close()

    record["pass"] = (
        all(started.values())
        and all(stopped(record["metaAfterStop"][agent]) for agent in agents)
        and all(after_idle[agent] == before[agent] for agent in agents)
        and not any(record["taskStartedBeforeSendMessage"].values())
        and all(stopped(record["metaAfterIdleRestart"][agent]) for agent in agents)
        and all(bool(marker_lines_by_agent[agent]) for agent in agents)
        and all(not stopped(record["metaAfterResume"][agent]) for agent in agents)
    )
    return record


def scenario_wakeafter(args, out):
    session, record = spawn_and_stop(args, out, "wakegate", "stop_task")
    if "error" in record:
        session.close()
        return record
    token = "RESUMED_WAKEGATE_OK"
    record["sendMessageResult"] = resume_in(session, record["agent"], token)
    transcript, meta = agent_files(args.cwd, record["session"], record["agent"])
    record["childMarkerLines"] = wait_marker(session, transcript, token, 180)
    session.pump(
        60,
        lambda event: event.get("type") == "system"
        and event.get("subtype") == "task_notification"
        and event.get("task_id") == record["agent"]
        and event.get("status") == "completed",
    )
    record["completedNotification"] = any(
        event.get("type") == "system"
        and event.get("subtype") == "task_notification"
        and event.get("task_id") == record["agent"]
        and event.get("status") == "completed"
        for event in session.events
    )
    record["metaAfterResume"] = read_meta(meta)
    session.close()
    record["pass"] = (
        record["childStartedSleep"]
        and stopped(record["metaAfterStop"])
        and bool(record["childMarkerLines"])
        and record["completedNotification"]
        and not stopped(record["metaAfterResume"])
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("launcher", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument(
        "--only",
        choices=[
            "taskstop",
            "interrupt",
            "restart",
            "noauto",
            "orphan",
            "grouped",
            "wakeafter",
        ],
        action="append",
    )
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    args.config_dir = (out / "config").resolve()
    args.config_dir.mkdir(parents=True, exist_ok=True)
    global PROJECTS
    PROJECTS = args.config_dir / "projects"
    args.cwd = (args.cwd or out / "workspace").resolve()
    args.cwd.mkdir(parents=True, exist_ok=True)
    args.launcher = args.launcher.resolve()

    wanted = args.only or [
        "taskstop",
        "interrupt",
        "restart",
        "noauto",
        "orphan",
        "grouped",
        "wakeafter",
    ]
    summary = {
        "launcher": str(args.launcher),
        "cwd": str(args.cwd),
        "configDir": str(args.config_dir),
        "homeSettingsSeedDisabled": True,
        "permissionMode": "default",
        "allowedTools": ["Agent", "SendMessage", "Bash"],
        "settingSources": ["project", "local"],
        "scenarios": {},
    }
    for name in wanted:
        if name == "taskstop":
            record = scenario_inproc(args, out, "stop_task", "taskstopgate")
        elif name == "interrupt":
            record = scenario_inproc(args, out, "interrupt", "interruptgate")
        elif name == "restart":
            record = scenario_restart(args, out)
        elif name == "noauto":
            record = scenario_noauto(args, out)
        elif name == "orphan":
            record = scenario_orphan(args, out)
        elif name == "grouped":
            record = scenario_grouped(args, out)
        else:
            record = scenario_wakeafter(args, out)
        summary["scenarios"][name] = record
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(name, json.dumps(record)[:1500], flush=True)
    print(json.dumps({key: value.get("pass") for key, value in summary["scenarios"].items()}))


if __name__ == "__main__":
    main()
