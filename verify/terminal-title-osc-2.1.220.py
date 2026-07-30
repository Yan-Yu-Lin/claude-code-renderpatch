#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify stock-equivalent Claude Code 2.1.220 terminal-title OSC frames."""

from __future__ import annotations

import argparse
import fcntl
import os
import pty
import re
import select
import signal
import struct
import subprocess
import termios
import time
from dataclasses import dataclass
from pathlib import Path

VERSION = "2.1.220"
REPO = Path(__file__).resolve().parents[1]
DEFAULT_STOCK = Path.home() / ".local/share/claude/versions" / VERSION
DEFAULT_BINARY = REPO / "patched/claude-2.1.220-semantic-bridge-prototype"
BOOTSTRAP = REPO / "preload/bootstrap.mjs"
OSC_TITLE = re.compile(rb"\x1b\](?:0|2);(.*?)(?:\x07|\x1b\\)", re.DOTALL)
IDLE = "✳ Claude Code"
BUSY = ("⠂ Claude Code", "⠐ Claude Code")


@dataclass(frozen=True)
class Case:
    name: str
    command: tuple[str, ...]
    preload: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument(
        "--launcher",
        type=Path,
        help="optional packaged launcher; adds normal and safe cases",
    )
    parser.add_argument("--startup-seconds", type=float, default=5.0)
    parser.add_argument("--busy-seconds", type=float, default=12.0)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain(master: int, process: subprocess.Popen[bytes], seconds: float) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and process.poll() is None:
        ready, _, _ = select.select([master], [], [], 0.1)
        if not ready:
            continue
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            break
        output.extend(chunk)
    return bytes(output)


def clean_environment(preload: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    for name in tuple(env):
        if name == "BUN_OPTIONS" or name.startswith(
            ("CLAUDE_RENDERPATCH_", "CLAUDE_PRELOAD_")
        ):
            env.pop(name, None)
    if preload is not None:
        env["BUN_OPTIONS"] = f"--preload={preload}"
    env["TERM"] = "xterm-256color"
    return env


def capture(case: Case, startup_seconds: float, busy_seconds: float) -> list[str]:
    master, slave = pty.openpty()
    fcntl.ioctl(
        slave,
        termios.TIOCSWINSZ,
        struct.pack("HHHH", 40, 120, 0, 0),
    )
    process = subprocess.Popen(
        list(case.command),
        cwd="/tmp",
        env=clean_environment(case.preload),
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    try:
        output = bytearray(drain(master, process, startup_seconds))
        require(process.poll() is None, f"{case.name}: exited before prompt")
        os.write(master, b"Say only OK.\r")
        output.extend(drain(master, process, busy_seconds))
        if process.poll() is None:
            os.write(master, b"\x03\x03")
            output.extend(drain(master, process, 3.0))
        payloads: list[str] = []
        for match in OSC_TITLE.finditer(bytes(output)):
            try:
                payloads.append(match.group(1).decode("utf-8"))
            except UnicodeDecodeError as error:
                raise AssertionError(
                    f"{case.name}: title payload is not valid UTF-8: {match.group(1)!r}"
                ) from error
        return payloads
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        os.close(master)


def animation_signature(case: Case, payloads: list[str]) -> tuple[str, ...]:
    require(payloads, f"{case.name}: emitted no OSC title payloads")
    require(
        all("â" not in payload for payload in payloads),
        f"{case.name}: emitted UTF-8 mojibake in a title payload",
    )
    require(
        all(not any("\x80" <= character <= "\x9f" for character in payload) for payload in payloads),
        f"{case.name}: emitted a C1 control character in a title payload",
    )

    start = payloads.index(IDLE)
    busy_start = next(
        (
            index
            for index in range(start + 1, len(payloads))
            if payloads[index] in BUSY
        ),
        None,
    )
    require(busy_start is not None, f"{case.name}: emitted no busy title frames")
    busy_end = next(
        (
            index
            for index in range(busy_start, len(payloads))
            if payloads[index] not in BUSY
        ),
        len(payloads),
    )
    frames = payloads[busy_start:busy_end]
    require(
        set(frames) == set(BUSY),
        f"{case.name}: unexpected busy title payloads: {sorted(set(frames))!r}",
    )
    require(frames[0] == BUSY[0], f"{case.name}: busy animation started on the wrong frame")
    require(
        all(frame == BUSY[index % 2] for index, frame in enumerate(frames)),
        f"{case.name}: busy title frames did not alternate exactly",
    )
    return (IDLE, *BUSY)


def main() -> int:
    args = parse_args()
    stock = args.stock.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    require(stock.is_file(), f"stock binary not found: {stock}")
    require(binary.is_file(), f"candidate binary not found: {binary}")

    cases = [
        Case("stock-direct", (str(stock),)),
        Case("candidate-direct", (str(binary),)),
        Case("candidate-bootstrap", (str(binary),), BOOTSTRAP),
    ]
    if args.launcher is not None:
        launcher = args.launcher.expanduser().resolve()
        require(launcher.is_file(), f"candidate launcher not found: {launcher}")
        cases.extend(
            [
                Case("candidate-normal", (str(launcher),)),
                Case("candidate-safe", (str(launcher), "--renderpatch-safe")),
            ]
        )

    signatures: dict[str, tuple[str, ...]] = {}
    frame_counts: dict[str, int] = {}
    for case in cases:
        payloads = capture(case, args.startup_seconds, args.busy_seconds)
        signatures[case.name] = animation_signature(case, payloads)
        frame_counts[case.name] = sum(payload in BUSY for payload in payloads)

    stock_signature = signatures["stock-direct"]
    require(
        all(signature == stock_signature for signature in signatures.values()),
        f"candidate title signature differs from stock: {signatures!r}",
    )

    print(f"stock title signature: {stock_signature!r}")
    for case in cases:
        print(
            f"{case.name}: idle={IDLE!r} busy={BUSY!r} "
            f"busy_frames={frame_counts[case.name]} utf8=clean"
        )
    print("terminal-title OSC matrix passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
