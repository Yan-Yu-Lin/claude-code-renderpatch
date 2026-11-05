"""PTY render check: answer a prompt, then Ctrl+O expand/collapse and resize.
Counts ED2/ED3/alt-screen bytes per phase for patched vs safe."""
import os, pty, re, select, sys, time, json, signal, fcntl, termios, struct

mode, cwd = sys.argv[1], sys.argv[2]
cand = os.path.expanduser("~/.local/share/claude-renderpatch/releases/2.1.318-host-linux-x64.5/claude-renderpatch-candidate")
env = dict(os.environ)
env.pop("CLAUDE_CODE_CHILD_SESSION", None)
env.update(CLAUDE_BRIDGE_BIN=cand, TERM="xterm-256color")
argv = ["claude-bridge"] + (["--renderpatch-safe"] if mode == "safe" else []) + [
    "Print the numbers 1 to 40, one per line, with the word ANCHOR before 1 and the word ENDMARK after 40. Nothing else."]
pid, fd = pty.fork()
if pid == 0:
    os.chdir(cwd); os.execvpe("claude-bridge", argv, env)
def size(rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0)); os.kill(pid, signal.SIGWINCH)
size(30, 100)
def pump(seconds, until=None):
    buf, end = b"", time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if fd in r:
            try: data = os.read(fd, 65536)
            except OSError: break
            if not data: break
            buf += data
            if b"\x1b[6n" in data: os.write(fd, b"\x1b[1;1R")
            if until and until in buf: end = min(end, time.time() + 2.5)
    return buf
def stats(b):
    return {"bytes": len(b), "ed2": b.count(b"\x1b[2J"), "ed3": b.count(b"\x1b[3J"),
            "alt": b.count(b"\x1b[?1049h"), "anchor": b.count(b"ANCHOR"), "end": b.count(b"ENDMARK")}
out = {"mode": mode}
first = pump(90, b"ENDMARK")
out["answer"] = stats(first)
os.write(fd, b"\x0f"); out["expand"] = stats(pump(4))
os.write(fd, b"\x0f"); out["collapse"] = stats(pump(4))
size(30, 80); out["resize"] = stats(pump(4))
print(json.dumps(out))
try:
    os.kill(pid, signal.SIGTERM); time.sleep(1); os.kill(pid, signal.SIGKILL)
except ProcessLookupError:
    pass
