#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Repeatable non-render gates for a 2.1.291 host release.

  routing   plain headless Agent and named interactive teammate, parent
            claude-sonnet-4-6 requesting child alias "sonnet"; proof is each
            child's own subagents/agent-*.jsonl assistant message.model
  context   interactive /context for the four slots (window size text)
  mod       official Mods: validate, test, live -p command, interactive /plugin
  restore   /model gpt-5.6-sol during a session; the saved model is restored
  env       Bash/MCP child environment carries no host/preload variables
  tamper    APFS clone: graph, host and extra-asset tamper refuse; ambient
            BUN_OPTIONS refused normally and scrubbed in safe mode
"""

import argparse
import fcntl
import json
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import termios
import time
import uuid
from pathlib import Path

HOME = Path.home()
OVERLAY = HOME / ".claude/claude-mix-settings.json"
ANSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-Za-z]")


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION")}
    env["TERM"] = "xterm-256color"
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    if extra:
        env.update(extra)
    return env


def proj(cwd):
    return HOME / ".claude/projects" / str(cwd).replace("/", "-").replace(".", "-")


def run(argv, label, out, cwd, env=None, timeout=300):
    t = time.time()
    p = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, env=env or clean_env(), timeout=timeout)
    rec = {"label": label, "argv": argv, "returncode": p.returncode, "seconds": round(time.time() - t, 3), "stdout": p.stdout[-6000:], "stderr": p.stderr[-3000:]}
    (out / f"{label}.json").write_text(json.dumps(rec, indent=2) + "\n")
    return rec


class Pty:
    def __init__(self, argv, cwd, env, cols=120, rows=40):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        self.data = bytearray()

    def read(self, seconds, until=None):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            r, _, _ = select.select([self.master], [], [], 0.2)
            if r:
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
        if self.proc.poll() is None:
            os.write(self.master, b"\x03")
            self.read(0.5)
            os.write(self.master, b"\x03")
            self.read(1.5)
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


def child_models(transcript):
    models, lines = [], []
    for n, line in enumerate(transcript.open(), 1):
        rec = json.loads(line)
        if rec.get("type") == "assistant":
            m = (rec.get("message") or {}).get("model")
            if m:
                models.append(m)
                lines.append(n)
    return sorted(set(models)), lines


def gate_routing(args, out):
    cwd = args.cwd
    results = []
    for mode in ("candidate", "safe"):
        pre = [str(args.launcher)] + (["--renderpatch-safe"] if mode == "safe" else [])
        # Plain headless.
        sid = str(uuid.uuid4())
        argv = pre + ["--session-id", sid, "--model", "claude-sonnet-4-6", "--system-prompt", "Follow the routing test exactly. Only use the one Agent invocation requested.", "--tools", "Agent", "--allowedTools", "Agent", "--strict-mcp-config", "--output-format", "stream-json", "--verbose", "-p", 'Call the Agent tool exactly once with subagent_type="general-purpose", model="sonnet", description="plain routing collision probe", prompt="Reply exactly PLAIN_ROUTE_CHILD_291R_OK. Do not use tools." Do not supply name or team_name. Wait for its response, then reply exactly PLAIN_ROUTE_PARENT_291R_OK. Do not do any other work.']
        rec = run(argv, f"routing-plain-{mode}", out, cwd, timeout=400)
        kids = sorted((proj(cwd) / sid / "subagents").glob("agent-*.jsonl"))
        models, lines = child_models(kids[0]) if kids else ([], [])
        results.append({"mode": mode, "path": "plain-agent", "sessionId": sid, "exitCode": rec["returncode"], "childTranscript": str(kids[0]) if kids else None, "assistantLines": lines, "actualModels": models})
        # Named interactive teammate.
        sid = str(uuid.uuid4())
        argv = pre + ["--session-id", sid, "--model", "claude-sonnet-4-6", "--teammate-mode", "in-process", "--tools", "Agent,SendMessage", "--allowedTools", "Agent,SendMessage", "--strict-mcp-config"]
        t = Pty(argv, cwd, clean_env({"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}))
        t.read(10)
        t.submit('Call Agent exactly once with name="routeprobe", subagent_type="general-purpose", model="sonnet", description="named routing verification", prompt="Reply exactly NAMED_ROUTE_CHILD_291R_OK. Do not use tools." Do not omit name. Wait for its result, then reply exactly NAMED_ROUTE_PARENT_291R_OK. Do not do any other work.')
        # The PTY echoes the prompt (which contains the markers), so wait on
        # the child's own transcript and the parent's JSONL instead.
        deadline = time.monotonic() + 300
        parent_jsonl = proj(cwd) / f"{sid}.jsonl"
        while time.monotonic() < deadline:
            t.read(3)
            kids = sorted((proj(cwd) / sid / "subagents").glob("agent-arouteprobe-*.jsonl"))
            child_done = kids and "NAMED_ROUTE_CHILD_291R_OK" in kids[0].read_text()
            parent_done = parent_jsonl.exists() and any(
                '"type":"assistant"' in line and "NAMED_ROUTE_PARENT_291R_OK" in line
                for line in parent_jsonl.read_text().splitlines()
            )
            if child_done and parent_done:
                break
        t.read(5)
        t.submit("/exit")
        t.read(8)
        rc = t.finish()
        (out / f"routing-named-{mode}.ansi").write_bytes(bytes(t.data))
        kids = sorted((proj(cwd) / sid / "subagents").glob("agent-arouteprobe-*.jsonl"))
        models, lines = child_models(kids[0]) if kids else ([], [])
        results.append({"mode": mode, "path": "named-teammate", "sessionId": sid, "exitCode": rc, "childTranscript": str(kids[0]) if kids else None, "assistantLines": lines, "actualModels": models})
    ok = all(
        (r["actualModels"] == ["gpt-5.6-sol"]) if r["mode"] == "candidate" else (r["actualModels"] == ["claude-sonnet-4-6"])
        for r in results
    )
    summary = {"parentModel": "claude-sonnet-4-6", "requestedChildModel": "sonnet", "results": results, "pass": ok}
    (out / "routing-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def gate_context(args, out):
    res = {}
    for slot in ("fable", "opus", "sonnet", "haiku"):
        t = Pty([str(args.launcher), "--model", slot], args.cwd, clean_env())
        t.read(10)
        t.submit("/context")
        t.read(8)
        t.finish()
        (out / f"context-{slot}.ansi").write_bytes(bytes(t.data))
        m = re.findall(r"([0-9.]+k)\s*/\s*([0-9.]+[km])\s*tokens\s*\((\d+)%\)", t.text())
        res[slot] = m[-1] if m else None
    expected = {"fable": "1m", "opus": "1m", "sonnet": "372k", "haiku": "372k"}
    summary = {"slots": res, "pass": all(res[s] and res[s][1] == expected[s] for s in res)}
    (out / "context-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def gate_mod(args, out):
    fixture = args.repo / "verify/fixtures/mod-2.1.291"
    work = out / "mod-fixture"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(fixture, work)
    L = str(args.launcher)
    r = {
        "validate": run([L, "plugin", "validate", str(work)], "host-mod-validate", out, args.cwd),
        "test": run([L, "plugin", "test", str(work)], "host-mod-test", out, args.cwd),
        "command": run([L, "--plugin-dir", str(work), "-p", "/renderpatch-hello"], "host-mod-command", out, args.cwd),
    }
    t = Pty([L, "--plugin-dir", str(work)], args.cwd, clean_env())
    t.read(10)
    t.submit("/plugin")
    t.read(5)
    os.write(t.master, b"\x1b")
    t.read(1.5)
    t.submit("/renderpatch-hello")
    t.read(6)
    t.finish()
    (out / "host-mod-ui.ansi").write_bytes(bytes(t.data))
    marker = "RENDERPATCH_MOD_2_1_291"
    ui = t.text()
    summary = {
        "validate": r["validate"]["returncode"],
        "test": r["test"]["returncode"],
        "testPassFail": re.findall(r"(\d+) pass.*?(\d+) fail", r["test"]["stdout"] + r["test"]["stderr"], re.S)[-1:] ,
        "command": marker in r["command"]["stdout"],
        "uiCommand": marker in ui,
        "uiPluginActive": bool(re.search(r"1 mod|mod.{0,20}active|renderpatch", ui, re.I)),
    }
    summary["pass"] = summary["validate"] == 0 and summary["test"] == 0 and summary["command"] and summary["uiCommand"]
    (out / "mods-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def saved_model():
    p = HOME / ".claude/settings.json"
    try:
        return json.loads(p.read_text()).get("model")
    except Exception:
        return None


def gate_restore(args, out):
    before = saved_model()
    t = Pty([str(args.launcher), "--model", "opus"], args.cwd, clean_env())
    t.read(10)
    t.submit("/model gpt-5.6-sol")
    t.read(5)
    during = saved_model()
    rc = t.finish()
    time.sleep(1)
    after = saved_model()
    (out / "model-restore.ansi").write_bytes(bytes(t.data))
    summary = {"before": before, "during": during, "after": after, "exit": rc, "pass": after == before}
    (out / "model-restore-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def gate_env(args, out):
    names = ["BUN_OPTIONS", "RP_HOST_ENTRY", "CLAUDE_RENDERPATCH_ACTIVE", "CLAUDE_RENDERPATCH_TARGET", "CLAUDE_CODE_EXECPATH"]
    script = "; ".join(f'echo "{n}=${{{n}-<unset>}}"' for n in names)
    rec = run([str(args.launcher), "--model", "sonnet", "--tools", "Bash", "--allowedTools", "Bash", "--output-format", "json", "-p", f"Run exactly this Bash command once and then reply with its raw output only: {script}"], "bash-child-env-run", out, args.cwd)
    seen = {}
    try:
        text = json.loads(rec["stdout"]).get("result", "")
    except Exception:
        text = rec["stdout"]
    for n in names:
        m = re.search(n + r"=(\S+)", text)
        seen[n] = m.group(1) if m else None
    leaked = [n for n in names[:4] if seen[n] not in ("<unset>", None)]
    summary = {"bash": seen, "leaked": leaked, "execPathIsReleaseRuntime": str(seen.get("CLAUDE_CODE_EXECPATH", "")).endswith("/runtime/claude"), "exit": rec["returncode"]}
    summary["pass"] = rec["returncode"] == 0 and not leaked and seen["BUN_OPTIONS"] == "<unset>"
    (out / "bash-child-env.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def gate_tamper(args, out):
    rel = args.launcher.resolve().parent
    res = {}
    for case in ("graph", "host", "extra"):
        clone = out / f"tamper-{case}-clone"
        if clone.exists():
            subprocess.run(["chmod", "-R", "u+w", str(clone)])
            shutil.rmtree(clone)
        subprocess.run(["cp", "-cR", str(rel), str(clone)], check=True)
        subprocess.run(["chmod", "-R", "u+w", str(clone)], check=True)
        if case == "graph":
            p = clone / "graph/chunk-ebe4qw6e.js"
            p.write_text(p.read_text() + "\n// tamper\n")
        elif case == "host":
            p = clone / "host.mjs"
            p.write_text(p.read_text() + "\n// tamper\n")
        else:
            (clone / "unexpected-asset").write_text("x")
        # Restore the release's exact modes so the launcher reaches its hash
        # check instead of refusing on a writable-mode mismatch.
        manifest = json.loads((rel / "release-manifest.json").read_text())
        for relpath, meta in manifest["assets"].items():
            if (clone / relpath).exists():
                os.chmod(clone / relpath, meta["mode"])
        for name in ("claude-renderpatch-candidate",):
            os.chmod(clone / name, 0o555)
        os.chmod(clone / ".claude-renderpatch-release", 0o444)
        os.chmod(clone / "release-manifest.json", 0o444)
        if case == "extra":
            os.chmod(clone / "unexpected-asset", 0o444)
        for d in sorted((x for x in clone.rglob("*") if x.is_dir()), reverse=True):
            os.chmod(d, 0o555)
        os.chmod(clone, 0o555)
        r = run([str(clone / "claude-renderpatch-candidate"), "--version"], f"tamper-{case}", out, args.cwd)
        res[case] = {"rc": r["returncode"], "stderr": r["stderr"].strip()}
        subprocess.run(["chmod", "-R", "u+w", str(clone)])
        shutil.rmtree(clone)
    amb = run([str(args.launcher), "--version"], "reject-ambient-preload", out, args.cwd, env=clean_env({"BUN_OPTIONS": "--preload=/tmp/x.mjs"}))
    scrub = run([str(args.launcher), "--renderpatch-safe", "--version"], "safe-scrub-ambient", out, args.cwd, env=clean_env({"BUN_OPTIONS": "--preload=/tmp/x.mjs"}))
    res["ambient"] = {"rc": amb["returncode"], "stderr": amb["stderr"].strip()}
    res["safeScrub"] = {"rc": scrub["returncode"], "stdout": scrub["stdout"].strip()}
    expect = {"graph": "asset hash mismatch: graph/chunk-ebe4qw6e.js", "host": "asset hash mismatch: host.mjs", "extra": "unlisted asset: unexpected-asset"}
    res["pass"] = all(res[c]["rc"] == 1 and expect[c] in res[c]["stderr"] for c in expect) and res["ambient"]["rc"] == 1 and res["safeScrub"]["rc"] == 0
    (out / "tamper-summary.json").write_text(json.dumps(res, indent=2) + "\n")
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("launcher", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cwd", type=Path, default=Path("/tmp/rp-host-gates"))
    p.add_argument("--only", action="append", choices=["routing", "context", "mod", "restore", "env", "tamper"])
    a = p.parse_args()
    a.repo = Path(__file__).resolve().parents[1]
    a.cwd.mkdir(parents=True, exist_ok=True)
    a.cwd = a.cwd.resolve()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    gates = {"routing": gate_routing, "context": gate_context, "mod": gate_mod, "restore": gate_restore, "env": gate_env, "tamper": gate_tamper}
    passed = {}
    for name in a.only or list(gates):
        res = gates[name](a, out)
        passed[name] = res.get("pass")
        print(name, json.dumps(res)[:1500], flush=True)
    print(json.dumps(passed))


if __name__ == "__main__":
    main()
