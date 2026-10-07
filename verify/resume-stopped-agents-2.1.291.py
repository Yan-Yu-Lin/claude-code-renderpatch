#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Real stream-json resume gates for stopped background agents (2.1.291).

Each scenario starts a fresh SDK-style session (stream-json in/out, no
perTaskStopAffordance, i.e. exactly like T3 Code today) under the launcher
being tested, has the parent spawn a background agent that idles on a long
`sleep`, stops it, and checks whether SendMessage can resume it.

  taskstop   SDK `stop_task` control request (the UI/TaskStop path, source user)
  interrupt  SDK `interrupt` control request (the T3 path that hit identity-watch)
  restart    stop_task, end the process, `--resume` the session in a new process,
             then SendMessage by agent id, and by name in a third process
  noauto     stop_task, end, `--resume`, wait with no SendMessage: the agent
             transcript must not grow and no running task may appear

Evidence is the child's own transcript (`subagents/agent-<id>.jsonl`), the
sidecar `.meta.json`, and the parent's tool_result text. Model self-reports
are not used as proof.
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
                [self.proc.stdout, self.proc.stderr], [], [], 0.2
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
        except Exception:
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


def tool_results(events):
    out = []
    for e in events:
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_result":
                c = block.get("content")
                if isinstance(c, list):
                    c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                out.append(str(c))
    return out


def find_agent_id(events):
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "task_started":
            if e.get("task_type") == "local_agent":
                return e.get("task_id")
    for text in tool_results(events):
        if "agentId:" in text:
            return text.split("agentId:")[1].split()[0].strip(" .,)")
    return None


def agent_files(cwd, session_id, agent_id):
    base = project_dir(cwd) / session_id / "subagents"
    return base / f"agent-{agent_id}.jsonl", base / f"agent-{agent_id}.meta.json"


def line_count(path):
    try:
        return sum(1 for _ in path.open())
    except FileNotFoundError:
        return 0


def read_meta(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def marker_lines(path, marker):
    hits = []
    try:
        for n, line in enumerate(path.open(), 1):
            if marker in line:
                rec = json.loads(line)
                if rec.get("type") == "assistant":
                    hits.append(n)
    except FileNotFoundError:
        pass
    return hits


SPAWN = (
    'Call the Agent tool exactly once with name="{name}", subagent_type="general-purpose", '
    'model="sonnet", run_in_background=true, description="resume gate {name}", and prompt: '
    '"Run the Bash command `sleep 900` (timeout 900000) in the foreground and wait for it. '
    "If you are ever resumed with a new message, do not run sleep again; reply exactly with "
    'the token that message asks for and stop." '
    "Then reply exactly SPAWNED and stop. Do not do anything else."
)
RESUME = (
    "Call the SendMessage tool exactly once with to=\"{to}\" and message=\"You were resumed. "
    'Reply exactly {token} and stop. Do not run any tools." Then reply exactly with the full '
    "text of the SendMessage tool result and stop. Do not retry and do not call any other tool."
)


def start(args, sid, resume=False, extra_env=None):
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
        "bypassPermissions",
        "--strict-mcp-config",
    ]
    argv += ["--resume", sid] if resume else ["--session-id", sid]
    env = os.environ.copy()
    for k in ["CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT"]:
        env.pop(k, None)
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    if extra_env:
        env.update(extra_env)
    return argv, env


def spawn_and_stop(args, out, name, how):
    sid = str(uuid.uuid4())
    log = (out / f"{name}.log").open("w")
    argv, env = start(args, sid)
    s = Session(argv, args.cwd, log, env)
    s.user(SPAWN.format(name=name))
    s.wait_result(240)
    agent = find_agent_id(s.events)
    rec = {"session": sid, "agent": agent, "how": how}
    if not agent:
        rec["error"] = "no agent spawned"
        return s, rec
    transcript, meta = agent_files(args.cwd, sid, agent)
    # Wait until the child is really inside its sleep (its Bash call is logged).
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and "sleep 900" not in (
        transcript.read_text() if transcript.exists() else ""
    ):
        s.pump(2)
    rec["childStartedSleep"] = "sleep 900" in (
        transcript.read_text() if transcript.exists() else ""
    )
    if how == "stop_task":
        s.control({"subtype": "stop_task", "task_id": agent})
    else:
        s.control({"subtype": "interrupt"})
    s.pump(8)
    rec["metaAfterStop"] = read_meta(meta)
    rec["stoppedEvent"] = any(
        e.get("type") == "system"
        and e.get("subtype") in ("task_notification", "task_updated")
        and e.get("task_id") == agent
        for e in s.events
    )
    return s, rec


def resume_in(s, agent, to, token, out_events_from):
    before = len(s.events)
    s.user(RESUME.format(to=to, token=token))
    s.wait_result(240)
    return [t[:600] for t in tool_results(s.events[before:])]


def wait_marker(path, marker, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        hits = marker_lines(path, marker)
        if hits:
            return hits
        time.sleep(2)
    return []


def scenario_inproc(args, out, how, label):
    s, rec = spawn_and_stop(args, out, label, how)
    if "error" in rec:
        s.close()
        return rec
    token = f"RESUMED_{label.upper()}_OK"
    rec["sendMessageResult"] = resume_in(s, rec["agent"], rec["agent"], token, 0)
    transcript, meta = agent_files(args.cwd, rec["session"], rec["agent"])
    rec["childMarkerLines"] = wait_marker(transcript, token, 180)
    s.pump(5)
    rec["metaAfterResume"] = read_meta(meta)
    s.close()
    rec["pass"] = bool(rec["childMarkerLines"])
    return rec


def scenario_restart(args, out):
    label = "restartgate"
    s, rec = spawn_and_stop(args, out, label, "stop_task")
    s.close()
    if "error" in rec:
        return rec
    sid, agent = rec["session"], rec["agent"]
    transcript, meta = agent_files(args.cwd, sid, agent)
    # Process 2: resume by agent id.
    log = (out / f"{label}-byid.log").open("w")
    argv, env = start(args, sid, resume=True)
    s2 = Session(argv, args.cwd, log, env)
    tok = "RESUMED_BYID_OK"
    rec["byIdResult"] = resume_in(s2, agent, agent, tok, 0)
    rec["byIdMarkerLines"] = wait_marker(transcript, tok, 180)
    s2.pump(3)
    # Stop it again so the by-name check starts from a stopped agent.
    s2.control({"subtype": "stop_task", "task_id": agent})
    s2.pump(8)
    rec["metaBeforeByName"] = read_meta(meta)
    s2.close()
    # Process 3: resume by name only.
    log = (out / f"{label}-byname.log").open("w")
    argv, env = start(args, sid, resume=True)
    s3 = Session(argv, args.cwd, log, env)
    tok2 = "RESUMED_BYNAME_OK"
    rec["byNameResult"] = resume_in(s3, agent, label, tok2, 0)
    rec["byNameMarkerLines"] = wait_marker(transcript, tok2, 180)
    s3.pump(3)
    s3.close()
    rec["pass"] = bool(rec["byIdMarkerLines"]) and bool(rec["byNameMarkerLines"])
    return rec


def scenario_noauto(args, out):
    label = "noautogate"
    s, rec = spawn_and_stop(args, out, label, "stop_task")
    s.close()
    if "error" in rec:
        return rec
    sid, agent = rec["session"], rec["agent"]
    transcript, meta = agent_files(args.cwd, sid, agent)
    before = line_count(transcript)
    log = (out / f"{label}-resume.log").open("w")
    argv, env = start(args, sid, resume=True)
    s2 = Session(argv, args.cwd, log, env)
    s2.user("Reply exactly IDLE_CHECK and stop. Do not call any tool.")
    s2.wait_result(180)
    s2.pump(60)
    after = line_count(transcript)
    rec["childLinesBefore"] = before
    rec["childLinesAfter"] = after
    rec["taskStartedForAgent"] = any(
        e.get("type") == "system"
        and e.get("subtype") == "task_started"
        and e.get("task_id") == agent
        for e in s2.events
    )
    rec["orphanNotice"] = [
        str(e)[:1200]
        for e in s2.events
        if agent in json.dumps(e) and "paused" in json.dumps(e)
    ][:2]
    s2.close()
    rec["pass"] = after == before and not rec["taskStartedForAgent"]
    return rec


def scenario_orphan(args, out):
    """The identity-watch timing: interrupt, then close ~immediately (T3)."""
    label = "orphangate"
    sid = str(uuid.uuid4())
    log = (out / f"{label}.log").open("w")
    argv, env = start(args, sid)
    s = Session(argv, args.cwd, log, env)
    s.user(SPAWN.format(name=label))
    s.wait_result(240)
    agent = find_agent_id(s.events)
    rec = {"session": sid, "agent": agent, "how": "interrupt+close"}
    if not agent:
        rec["error"] = "no agent spawned"
        s.close()
        return rec
    transcript, meta = agent_files(args.cwd, sid, agent)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and "sleep 900" not in (transcript.read_text() if transcript.exists() else ""):
        s.pump(2)
    s.control({"subtype": "interrupt"})
    s.close()
    rec["metaAfterStop"] = read_meta(meta)
    before = line_count(transcript)
    log = (out / f"{label}-resume.log").open("w")
    argv, env = start(args, sid, resume=True)
    s2 = Session(argv, args.cwd, log, env)
    s2.user("Reply exactly IDLE_CHECK and stop. Do not call any tool.")
    s2.wait_result(180)
    s2.pump(20)
    rec["childLinesBefore"] = before
    rec["childLinesAfterIdle"] = line_count(transcript)
    parent = project_dir(args.cwd) / f"{sid}.jsonl"
    notice = ""
    for line in parent.read_text().splitlines():
        if agent in line and "task-notification" in line:
            notice = line
    rec["noticeSaysPaused"] = "it is paused" in notice
    rec["noticeExcerpt"] = notice[notice.find("<note>"):notice.find("</note>") + 7][:700] if "<note>" in notice else notice[:500]
    tok = "RESUMED_ORPHAN_OK"
    rec["sendMessageResult"] = resume_in(s2, agent, agent, tok, 0)
    rec["childMarkerLines"] = wait_marker(transcript, tok, 180)
    s2.pump(3)
    s2.close()
    rec["pass"] = (
        rec["childLinesAfterIdle"] == before
        and bool(rec["childMarkerLines"])
        and (rec["noticeSaysPaused"] or not (rec["metaAfterStop"] or {}).get("stoppedByUser"))
    )
    return rec


def scenario_grouped(args, out):
    """Two stopped agents orphaned together: each must get a paused notice."""
    sid = str(uuid.uuid4())
    log = (out / "groupedgate.log").open("w")
    argv, env = start(args, sid)
    s = Session(argv, args.cwd, log, env)
    agents = []
    for name in ("groupa", "groupb"):
        before = len(s.events)
        s.user(SPAWN.format(name=name))
        s.wait_result(240)
        agents.append(find_agent_id(s.events[before:]))
    rec = {"session": sid, "agents": agents}
    if None in agents:
        rec["error"] = "spawn failed"
        s.close()
        return rec
    for a in agents:
        tr, _ = agent_files(args.cwd, sid, a)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and "sleep 900" not in (tr.read_text() if tr.exists() else ""):
            s.pump(2)
    # Stop both and close at once (T3 timing): the stop notifications are
    # not yet recorded as delivered, so the next process treats both agents
    # as orphans and must give each its own truthful paused notice.
    for a in agents:
        s.control({"subtype": "stop_task", "task_id": a})
    s.close()
    log = (out / "groupedgate-resume.log").open("w")
    argv, env = start(args, sid, resume=True)
    s2 = Session(argv, args.cwd, log, env)
    s2.user("Reply exactly IDLE_CHECK and stop. Do not call any tool.")
    s2.wait_result(180)
    s2.pump(10)
    s2.close()
    parent = (project_dir(args.cwd) / f"{sid}.jsonl").read_text()
    rec["metaStopped"] = {a: (read_meta(agent_files(args.cwd, sid, a)[1]) or {}).get("stoppedByUser") for a in agents}
    rec["pausedNotices"] = {a: any(a in line and "it is paused" in line for line in parent.splitlines()) for a in agents}
    rec["deliveredInSession"] = {a: any(a in line and "was stopped by user" in line and '"type":"user"' in line for line in parent.splitlines()) for a in agents}
    rec["genericGroupedNotice"] = "Resume any of them" in parent
    # A stopped agent either got its in-session stop notice (already truthful
    # upstream wording) or, if orphaned, its own paused notice; never the
    # grouped generic wording.
    rec["pass"] = all(rec["pausedNotices"][a] or rec["deliveredInSession"][a] for a in agents) and not rec["genericGroupedNotice"]
    return rec


def scenario_wakeafter(args, out):
    """Revive a stopped agent, then let it finish: its completion must reach
    the parent (automatic notification path works after a reply resume)."""
    s, rec = spawn_and_stop(args, out, "wakegate", "stop_task")
    if "error" in rec:
        s.close()
        return rec
    tok = "RESUMED_WAKEGATE_OK"
    rec["sendMessageResult"] = resume_in(s, rec["agent"], rec["agent"], tok, 0)
    transcript, meta = agent_files(args.cwd, rec["session"], rec["agent"])
    rec["childMarkerLines"] = wait_marker(transcript, tok, 180)
    s.pump(30, lambda e: e.get("type") == "system" and e.get("subtype") == "task_notification" and e.get("task_id") == rec["agent"] and e.get("status") == "completed")
    rec["completedNotification"] = any(
        e.get("type") == "system" and e.get("subtype") == "task_notification" and e.get("task_id") == rec["agent"] and e.get("status") == "completed"
        for e in s.events
    )
    rec["metaAfterResume"] = read_meta(meta)
    s.close()
    rec["pass"] = bool(rec["childMarkerLines"]) and rec["completedNotification"] and not (rec["metaAfterResume"] or {}).get("stoppedByUser")
    return rec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("launcher", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cwd", type=Path, default=Path("/tmp/rp-resume-gate"))
    p.add_argument(
        "--only", choices=["taskstop", "interrupt", "restart", "noauto", "orphan", "grouped", "wakeafter"], action="append"
    )
    args = p.parse_args()
    args.cwd.mkdir(parents=True, exist_ok=True)
    args.cwd = args.cwd.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    wanted = args.only or ["taskstop", "interrupt", "restart", "noauto", "orphan", "grouped", "wakeafter"]
    summary = {"launcher": str(args.launcher), "cwd": str(args.cwd), "scenarios": {}}
    for name in wanted:
        if name == "taskstop":
            rec = scenario_inproc(args, out, "stop_task", "taskstopgate")
        elif name == "interrupt":
            rec = scenario_inproc(args, out, "interrupt", "interruptgate")
        elif name == "restart":
            rec = scenario_restart(args, out)
        elif name == "orphan":
            rec = scenario_orphan(args, out)
        elif name == "grouped":
            rec = scenario_grouped(args, out)
        elif name == "wakeafter":
            rec = scenario_wakeafter(args, out)
        else:
            rec = scenario_noauto(args, out)
        summary["scenarios"][name] = rec
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(name, json.dumps(rec)[:1500], flush=True)
    print(json.dumps({k: v.get("pass") for k, v in summary["scenarios"].items()}))


if __name__ == "__main__":
    main()
