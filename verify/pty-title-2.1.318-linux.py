"""Run claude-bridge in a PTY with an initial prompt; report OSC 0/2 titles."""
import os, pty, re, select, sys, time, json, signal

mode = sys.argv[1]  # "patched" or "safe"
cwd = sys.argv[2]
cand = os.path.expanduser("~/.local/share/claude-renderpatch/releases/2.1.318-host-linux-x64.5/claude-renderpatch-candidate")
env = dict(os.environ)
env.pop("CLAUDE_CODE_CHILD_SESSION", None)
env["CLAUDE_BRIDGE_BIN"] = cand
env["TERM"] = "xterm-256color"
env["COLUMNS"], env["LINES"] = "100", "30"
argv = ["claude-bridge"] + (["--renderpatch-safe"] if mode == "safe" else []) + ["Why is the sky blue? Answer in one short sentence."]
pid, fd = pty.fork()
if pid == 0:
    os.chdir(cwd)
    os.execvpe("claude-bridge", argv, env)
import fcntl, termios, struct
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
buf = b""
deadline = time.time() + float(sys.argv[3] if len(sys.argv) > 3 else 60)
answered = None
while time.time() < deadline:
    r, _, _ = select.select([fd], [], [], 0.5)
    if fd in r:
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        buf += data
        # answer terminal queries minimally (cursor position / DA)
        if b"\x1b[6n" in data:
            os.write(fd, b"\x1b[1;1R")
        if b"trust" in data.lower() and b"Yes" in data and answered is None:
            os.write(fd, b"\r"); answered = time.time()
    titles = re.findall(rb"\x1b\][02];([^\x07\x1b]*)(?:\x07|\x1b\\)", buf)
    if any(t and t not in (b"Claude Code",) and not t.endswith(b"Claude Code") for t in titles) and time.time() > deadline - 1e9:
        if len(set(titles)) >= 2:
            break
titles = [t.decode("utf-8", "replace") for t in re.findall(rb"\x1b\][02];([^\x07\x1b]*)(?:\x07|\x1b\\)", buf)]
print(json.dumps({"mode": mode, "bytes": len(buf), "titles": list(dict.fromkeys(titles)),
                  "ed2": buf.count(b"\x1b[2J"), "ed3": buf.count(b"\x1b[3J"),
                  "altscreen": buf.count(b"\x1b[?1049h")}, ensure_ascii=False))
try:
    os.kill(pid, signal.SIGTERM); time.sleep(1); os.kill(pid, signal.SIGKILL)
except ProcessLookupError:
    pass
