#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Measure the memory-vs-screen gap for the in_process_teammate subagent view.

Launches claude-renderpatch-candidate under a PTY with the pure-diagnostic
subagent-view-measure extension, sends a prompt that spawns a teammate, waits
while the teammate is actively producing output, then switches into the subagent
view WHILE IT IS RUNNING and captures the screen.

The extension logs, on the same line and at the same instant:

  * state.transcripts[taskId].messages.length   (memory truth)
  * every d3 Messages-pipeline stage length     (raw -> rendered)

The screen capture is what the user actually sees. Comparing the two answers the
question that four rounds of fixes never measured.

Two ways to trigger the view switch:

  --autoview   the extension flips viewingAgentTaskId itself, deterministically,
               as soon as a running non-idle teammate exists (default)
  --keys       send the real key sequence through the PTY instead

Nothing here writes to state.transcripts. This is measurement only.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

HOME = Path.home()
DEFAULT_EXTENSION = (
    HOME
    / "20-29-Development/21-Active-Projects/claude-code-renderpatch"
    / "candidate/subagent-view-measure.mjs"
)
DEFAULT_LOG = Path("/tmp/renderpatch-measure.log")

# A prompt that makes the teammate emit many separate messages, so the live
# window has something to be truncated from. Kept mechanical on purpose: the
# point is message COUNT, not content.
DEFAULT_PROMPT = (
    "Spawn one teammate named probe using the Agent tool with "
    "subagent_type general-purpose and run_in_background true. "
    "Its prompt must be exactly: "
    "'Run these one at a time, each as its own separate Bash tool call, "
    "never batched: echo M1; echo M2; echo M3; echo M4; echo M5; echo M6; "
    "echo M7; echo M8; echo M9; echo M10; echo M11; echo M12; echo M13; "
    "echo M14; echo M15; echo M16; echo M17; echo M18; echo M19; echo M20; "
    "echo M21; echo M22; echo M23; echo M24; echo M25; echo M26; echo M27; "
    "echo M28; echo M29; echo M30. After each one write a one-sentence note "
    "about what it printed before running the next.' "
    "After spawning it, do nothing else and do not wait for it."
)

ANSI = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][B0]|\x1b[=>]")


def set_size(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def drain(fd: int, seconds: float, sink: bytearray) -> bytes:
    chunk_all = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        timeout = min(0.2, max(0.0, deadline - time.monotonic()))
        try:
            readable, _, _ = select.select([fd], [], [], timeout)
        except OSError:
            break
        if not readable:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        sink.extend(chunk)
        chunk_all.extend(chunk)
    return bytes(chunk_all)


def plain(data: bytes) -> str:
    return ANSI.sub(b"", data).decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(HOME / ".local/bin/claude-renderpatch-candidate"))
    parser.add_argument("--extension", default=str(DEFAULT_EXTENSION))
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--cwd", default=str(HOME / "20-29-Development/21-Active-Projects/claude-code-renderpatch"))
    parser.add_argument("--rows", type=int, default=45)
    parser.add_argument("--cols", type=int, default=110)
    parser.add_argument("--startup-seconds", type=float, default=25.0)
    parser.add_argument("--work-seconds", type=float, default=75.0,
                        help="How long to let the teammate run before switching into its view")
    parser.add_argument("--view-seconds", type=float, default=25.0)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--autoview", action="store_true", default=True)
    parser.add_argument("--keys", dest="autoview", action="store_false",
                        help="Drive the view switch with real keystrokes instead")
    parser.add_argument("--out", type=Path, default=Path("/tmp/renderpatch-measure"))
    args = parser.parse_args()

    out: Path = args.out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    log: Path = args.log.expanduser().resolve()
    if log.exists():
        log.unlink()

    master, slave = os.openpty()
    set_size(slave, args.rows, args.cols)

    env = os.environ.copy()
    env["CLAUDE_RENDERPATCH_SUBAGENT_MEASURE_LOG"] = str(log)
    if args.autoview:
        env["CLAUDE_RENDERPATCH_SUBAGENT_MEASURE_AUTOVIEW"] = "1"
    env.pop("CLAUDE_CODE_NO_FLICKER", None)
    env.pop("CLAUDE_CODE_DISABLE_VIRTUAL_SCROLL", None)

    # This harness is normally launched from inside a Claude Code session, so the
    # child would inherit the parent's session identity. CLAUDE_CODE_CHILD_SESSION
    # in particular turns transcript persistence OFF (Zkt @227455484), which means
    # no sidechain JSONL and a measurement of the wrong thing. Scrub the inherited
    # session state so the child is a normal top-level Claude Code.
    for name in (
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDECODE",
        "CLAUDE_PID",
        "CLAUDE_CODE_EXECPATH",
        "AI_AGENT",
    ):
        env.pop(name, None)
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"

    process = subprocess.Popen(
        [args.binary, "--renderpatch-extension", args.extension],
        cwd=args.cwd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave)

    everything = bytearray()
    phases: dict[str, bytes] = {}
    try:
        phases["startup"] = drain(master, args.startup_seconds, everything)

        # Type, settle, then submit. A single write of text+CR can be consumed as
        # one paste-ish burst and left sitting in the composer, which is what the
        # first run of this harness did: the prompt appeared on screen but never ran.
        os.write(master, args.prompt.encode())
        drain(master, 3.0, everything)
        os.write(master, b"\r")
        drain(master, 3.0, everything)
        # The user's config has vim-style input and manual mode; if the buffer is
        # still non-empty the newline went into the composer instead of submitting.
        os.write(master, b"\x1b\r")
        phases["working"] = drain(master, args.work_seconds, everything)

        if not args.autoview:
            # Real path: open the task list, pick the teammate, foreground it.
            os.write(master, b"\x14")  # Ctrl+T task panel
            phases["tasks"] = drain(master, 4.0, everything)
            os.write(master, b"\x1b[B")  # down to the teammate row
            drain(master, 1.5, everything)
            os.write(master, b"f")  # foreground / view teammate
            phases["view"] = drain(master, args.view_seconds, everything)
        else:
            phases["view"] = drain(master, args.view_seconds, everything)
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            drain(master, 2.0, everything)
        try:
            os.close(master)
        except OSError:
            pass

    for name, data in phases.items():
        (out / f"{name}.ansi").write_bytes(data)
        (out / f"{name}.txt").write_text(plain(data), encoding="utf-8")
    (out / "all.ansi").write_bytes(bytes(everything))
    (out / "all.txt").write_text(plain(bytes(everything)), encoding="utf-8")

    print(f"captures: {out}")
    for name, data in phases.items():
        print(f"  {name:<9} {len(data):>9} bytes")
    print()
    if log.exists():
        print(f"--- extension log ({log}) ---")
        print(log.read_text(encoding="utf-8", errors="replace"))
    else:
        print(f"NO EXTENSION LOG at {log} -- the extension never activated", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
