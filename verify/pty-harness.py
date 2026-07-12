#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exercise Claude Code transcript expansion, collapse, and resize in a PTY.

The harness launches a selected Claude binary at a fixed terminal size, resumes an
existing session, captures startup output, sends Ctrl+O twice, changes the PTY width,
and captures each phase separately. It never submits a user prompt. The child is
terminated at the end rather than asking Claude Code to alter the resumed session.

Example:

    ./verify/pty-harness.py \
      ~/.local/bin/claude-full-redraw \
      --session ca8cbb9d-7eca-45b6-a389-7d9c1fbf5101 \
      --anchor "I started another fish shell" \
      --anchor "wait what?"

Verified 2.1.203 reference, using a large 855-record session at 100x30 -> 80x30:

    known-good v1 expand-only:
      startup   ~87,600 bytes
      expand   ~369,700 bytes
      collapse   ~2,665 bytes, 29 LF bytes, no ED3
      resize    ~12,353 bytes, no ED3

    full-redraw v2:
      startup  ~152,963 bytes
      expand   ~768,607 bytes, one ED2 and one ED3
      collapse ~153,015 bytes, one ED2 and one ED3
      resize   ~150,373 bytes, one ED2 and one ED3

Absolute byte counts vary with session content, terminal dimensions, Claude Code
version, status UI, and timing. The important signals are:

* expand, collapse, and resize are all large replays rather than tiny viewport diffs;
* each authoritative phase contains ED2 (ESC[2J) and ED3 (ESC[3J);
* anchors from old portions of the loaded transcript appear in collapse and resize;
* expanded-only raw tool details disappear after collapse.

WARNING: resuming a real session can update non-message session metadata. Use a backed
up/test session. No prompt text is sent by this harness.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from dataclasses import asdict, dataclass


@dataclass
class PhaseResult:
    phase: str
    bytes: int
    lf_bytes: int
    ed2: int
    ed3: int
    anchors: dict[str, bool]
    output: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", help="Claude executable to test")
    parser.add_argument(
        "--session",
        required=True,
        help="Session UUID/path accepted by `claude --resume`",
    )
    parser.add_argument(
        "--cwd",
        default=str(Path.home()),
        help="Working directory for Claude (default: home directory)",
    )
    parser.add_argument("--rows", type=int, default=30)
    parser.add_argument("--cols", type=int, default=100)
    parser.add_argument("--resize-cols", type=int, default=80)
    parser.add_argument(
        "--startup-seconds",
        type=float,
        default=9.0,
        help="Capture time before sending Ctrl+O",
    )
    parser.add_argument(
        "--phase-seconds",
        type=float,
        default=15.0,
        help="Capture time for expand, collapse, and resize",
    )
    parser.add_argument(
        "--anchor",
        action="append",
        default=[],
        help="Old transcript string expected in full replays; repeatable",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/claude-renderpatch-pty"),
        help="Directory for raw ANSI captures and summary.json",
    )
    parser.add_argument(
        "--inherit-render-env",
        action="store_true",
        help="Do not remove fullscreen/virtual-scroll override variables",
    )
    return parser.parse_args()


def set_size(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def collect(fd: int, seconds: float) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        timeout = min(0.2, max(0.0, deadline - time.monotonic()))
        readable, _, _ = select.select([fd], [], [], timeout)
        if not readable:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def main() -> int:
    args = parse_args()
    binary = str(Path(args.binary).expanduser().resolve())
    cwd = str(Path(args.cwd).expanduser().resolve())
    output_dir: Path = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        print(f"Not an executable file: {binary}", file=sys.stderr)
        return 2

    master, slave = pty.openpty()
    set_size(slave, args.rows, args.cols)

    env = os.environ.copy()
    if not args.inherit_render_env:
        # Exercise the classic/main-screen path without accidental shell overrides.
        env.pop("CLAUDE_CODE_NO_FLICKER", None)
        env.pop("CLAUDE_CODE_DISABLE_VIRTUAL_SCROLL", None)

    process = subprocess.Popen(
        [binary, "--resume", args.session],
        cwd=cwd,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave)

    captures: list[tuple[str, bytes]] = []
    try:
        captures.append(("startup", collect(master, args.startup_seconds)))

        os.write(master, b"\x0f")  # Ctrl+O: enter/expand transcript
        captures.append(("expand", collect(master, args.phase_seconds)))

        os.write(master, b"\x0f")  # Ctrl+O: exit/collapse transcript
        captures.append(("collapse", collect(master, args.phase_seconds)))

        set_size(master, args.rows, args.resize_cols)
        os.killpg(process.pid, signal.SIGWINCH)
        captures.append(("resize", collect(master, args.phase_seconds)))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            collect(master, 0.5)
        try:
            os.close(master)
        except OSError:
            pass

    results: list[PhaseResult] = []
    for phase, data in captures:
        output_path = output_dir / f"{phase}.ansi"
        output_path.write_bytes(data)
        anchor_results = {
            anchor: anchor.encode("utf-8") in data for anchor in args.anchor
        }
        results.append(
            PhaseResult(
                phase=phase,
                bytes=len(data),
                lf_bytes=data.count(b"\n"),
                ed2=data.count(b"\x1b[2J"),
                ed3=data.count(b"\x1b[3J"),
                anchors=anchor_results,
                output=str(output_path),
            )
        )

    summary = {
        "binary": binary,
        "session": args.session,
        "cwd": cwd,
        "initial_size": {"rows": args.rows, "cols": args.cols},
        "resized_to": {"rows": args.rows, "cols": args.resize_cols},
        "returncode": process.poll(),
        "phases": [asdict(result) for result in results],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"binary: {binary}")
    print(f"captures: {output_dir}")
    print(
        f"{'phase':<10} {'bytes':>10} {'LF':>8} {'ED2':>5} {'ED3':>5}  anchors"
    )
    for result in results:
        anchors = ", ".join(
            f"{name}={'yes' if found else 'NO'}"
            for name, found in result.anchors.items()
        )
        print(
            f"{result.phase:<10} {result.bytes:>10} {result.lf_bytes:>8} "
            f"{result.ed2:>5} {result.ed3:>5}  {anchors}"
        )

    # Do not impose hard byte thresholds: sessions and versions vary. Return a
    # failure only for clearly missing output or failed requested anchors in the
    # two phases that should contain the complete collapsed frame.
    if any(result.bytes == 0 for result in results):
        print("FAIL: one or more phases produced no output", file=sys.stderr)
        return 1
    for result in results:
        if result.phase in {"collapse", "resize"} and not all(
            result.anchors.values()
        ):
            print(
                f"FAIL: old-history anchor missing during {result.phase}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
