#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exercise a synthetic long transcript; never submit an inference prompt."""

import argparse
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import time
import uuid
from pathlib import Path


def collect(fd, seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        ready, _, _ = select.select(
            [fd], [], [], min(0.1, max(0, deadline - time.monotonic()))
        )
        if ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data.extend(chunk)
            # Reply to cursor-position queries as a basic terminal emulator.
            if b"\x1b[6n" in chunk:
                os.write(fd, b"\x1b[1;1R")
    return bytes(data)


def fixture(path):
    sid = str(uuid.uuid4())
    parent = None
    rows = []
    for i in range(70):
        for role in ["user", "assistant"]:
            uid = str(uuid.uuid4())
            content = [
                {
                    "type": "text",
                    "text": f"RP_{role.upper()}_{i:03d} "
                    + (
                        "A long renderer fixture line with enough words to wrap at both tested terminal widths. "
                        * 2
                    ),
                }
            ]
            msg = {"role": role, "content": content}
            if role == "assistant":
                if i == 35:
                    content.insert(
                        0,
                        {
                            "type": "thinking",
                            "thinking": "RP_EXPANDED_ONLY_DETAIL: synthetic transcript detail for folding verification.",
                            "signature": "",
                        },
                    )
                msg.update(
                    id="msg_" + uid,
                    type="message",
                    model="claude-opus-5",
                    stop_reason="end_turn",
                    usage={"input_tokens": 10, "output_tokens": 10},
                )
            rows.append(
                {
                    "uuid": uid,
                    "parentUuid": parent,
                    "isSidechain": False,
                    "type": role,
                    "sessionId": sid,
                    "cwd": str(Path.home()),
                    "version": "2.1.261",
                    "timestamp": f"2026-09-06T00:{i // 60:02d}:{i % 60:02d}.000Z",
                    "message": msg,
                }
            )
            parent = uid
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("binary", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--startup", type=float, default=8)
    p.add_argument("--seconds", type=float, default=3)
    p.add_argument("--assert-render", action="store_true")
    p.add_argument("--extension", type=Path)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    session = out / "session.jsonl"
    fixture(session)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env.pop("CLAUDECODE", None)
    cmd = [
        str(args.binary.resolve()),
        "--resume",
        str(session),
        "--settings",
        str(Path.home() / ".claude/claude-mix-settings.json"),
    ]
    if args.extension:
        cmd.extend(["--renderpatch-extension", str(args.extension.resolve())])
    proc = subprocess.Popen(
        cmd,
        cwd=Path.home(),
        env=env,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    captures = []
    try:
        captures.append(("startup", collect(master, args.startup)))
        for name, key in [
            ("expand", b"\x0f"),
            ("collapse", b"\x0f"),
            ("resize", None),
            ("expand_again", b"\x0f"),
            ("collapse_again", b"\x0f"),
        ]:
            if key:
                os.write(master, key)
            else:
                fcntl.ioctl(
                    master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 80, 0, 0)
                )
                os.killpg(proc.pid, signal.SIGWINCH)
            captures.append((name, collect(master, args.seconds)))
    finally:
        if proc.poll() is None:
            os.write(master, b"\x03\x03")
            collect(master, 1)
        if proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        os.close(master)
    results = []
    for name, data in captures:
        (out / (name + ".ansi")).write_bytes(data)
        results.append(
            {
                "phase": name,
                "bytes": len(data),
                "ed2": data.count(b"\x1b[2J"),
                "ed3": data.count(b"\x1b[3J"),
                "altScreen": b"\x1b[?1049h" in data,
                "first": b"RP_USER_000" in data,
                "last": b"RP_ASSISTANT_069" in data,
                "expandedDetail": b"RP_EXPANDED_ONLY_DETAIL" in data,
            }
        )
    summary = {"returncode": proc.returncode, "phases": results}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if args.assert_render:
        for row in results[1:]:
            assert (
                row["ed2"]
                and row["ed3"]
                and row["first"]
                and row["last"]
                and not row["altScreen"]
            ), row
            assert row["expandedDetail"] == row["phase"].startswith("expand"), row


if __name__ == "__main__":
    main()
