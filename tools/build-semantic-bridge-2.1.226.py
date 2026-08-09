#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the Claude Code 2.1.226 eight-range internal SDK bridge."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from semantic_bridge_2_1_226 import (
    BUN_OFFSET,
    BUN_SIZE,
    EXPECTED_FILE_SIZE,
    EXPECTED_STOCK_SHA256,
    OUTPUT_NAME,
    VERSION,
    apply_patches,
    digest,
    discover_patches,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STOCK = Path.home() / ".local/share/claude/versions" / VERSION
DEFAULT_OUTPUT = REPO / "patched" / OUTPUT_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing disposable prototype output",
    )
    return parser.parse_args()


def run(
    command: list[str],
    *,
    capture_output: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        check=True,
        capture_output=capture_output,
        text=text,
    )


def verify_live_bun_range(stock: Path) -> None:
    result = run(["otool", "-l", str(stock)], capture_output=True, text=True)
    match = re.search(
        r"segname __BUN\n"
        r"(?:.*\n){1,5}?"
        r"\s*fileoff (\d+)\n"
        r"\s*filesize (\d+)",
        result.stdout,
    )
    if match is None:
        raise RuntimeError("could not parse live __BUN range from otool")
    actual = (int(match.group(1)), int(match.group(2)))
    expected = (BUN_OFFSET, BUN_SIZE)
    if actual != expected:
        raise RuntimeError(
            f"unexpected live __BUN range: expected {expected}, found {actual}"
        )


def trash_paths(paths: list[Path]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        subprocess.run(["trash", *existing], check=False)


def main() -> int:
    args = parse_args()
    stock = args.stock.expanduser().resolve()
    output = args.output.expanduser().resolve()

    if not stock.is_file():
        raise SystemExit(f"stock binary not found: {stock}")
    if output.exists() and not args.force:
        raise SystemExit(f"output already exists (pass --force to replace): {output}")

    stock_data = stock.read_bytes()
    actual_sha = digest(stock_data)
    if actual_sha != EXPECTED_STOCK_SHA256 or len(stock_data) != EXPECTED_FILE_SIZE:
        raise SystemExit(
            "stock identity mismatch:\n"
            f"  expected SHA:  {EXPECTED_STOCK_SHA256}\n"
            f"  actual SHA:    {actual_sha}\n"
            f"  expected size: {EXPECTED_FILE_SIZE}\n"
            f"  actual size:   {len(stock_data)}"
        )
    verify_live_bun_range(stock)

    patches = discover_patches(stock_data)
    patched_data = apply_patches(stock_data, patches)

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(prefix=f".{OUTPUT_NAME}.", dir=output.parent)
    os.close(temp_fd)
    temp_output = Path(temp_name)
    entitlements_fd, entitlements_name = tempfile.mkstemp(
        prefix=".bridge-entitlements.", dir=output.parent
    )
    os.close(entitlements_fd)
    entitlements = Path(entitlements_name)

    try:
        temp_output.write_bytes(patched_data)
        temp_output.chmod(0o755)

        with entitlements.open("wb") as handle:
            subprocess.run(
                ["codesign", "-d", "--entitlements", ":-", str(stock)],
                check=True,
                stdout=handle,
                stderr=subprocess.DEVNULL,
            )
        if entitlements.stat().st_size == 0:
            raise RuntimeError("stock entitlement extraction produced an empty file")

        # Exactly one signing pass after all byte edits and post-checks succeed.
        run(
            [
                "codesign",
                "--force",
                "--sign",
                "-",
                "--identifier",
                "com.anthropic.claude-code",
                "--entitlements",
                str(entitlements),
                str(temp_output),
            ]
        )
        run(["codesign", "--verify", "--strict", "--verbose=2", str(temp_output)])
        version_result = run(
            [str(temp_output), "--version"], capture_output=True, text=True
        )
        version_text = version_result.stdout.strip()
        if version_text != f"{VERSION} (Claude Code)":
            raise RuntimeError(f"unexpected --version output: {version_text!r}")

        if output.exists():
            trash_paths([output])
        os.replace(temp_output, output)
    finally:
        trash_paths([temp_output, entitlements])

    print(f"stock: {stock}")
    print(f"stock SHA-256: {actual_sha}")
    print(f"live __BUN: offset={BUN_OFFSET} size={BUN_SIZE}")
    print(f"bridge sites: {len(patches)}")
    for patch in patches:
        executable_length = len(patch.new.rstrip(b" "))
        print(
            f"  {patch.name}: offset={patch.offset} length={patch.length} "
            f"replacement-code={executable_length} padding={patch.length - executable_length}"
        )
    print(f"unchanged pre-sign length: {len(patched_data)}")
    print("codesign: strict verification passed")
    print(f"version: {version_text}")
    print(f"artifact: {output}")
    print(f"artifact SHA-256: {digest(output.read_bytes())}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        command = " ".join(error.cmd) if isinstance(error.cmd, list) else str(error.cmd)
        print(f"command failed ({error.returncode}): {command}", file=sys.stderr)
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise
