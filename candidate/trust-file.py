"""Validate a sensitive user-owned file and every path component below home."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    if len(sys.argv) != 4:
        fail("usage: trust-file.py LABEL ABSOLUTE_PATH EXPECTED_MODE")
    label, raw_path, raw_mode = sys.argv[1:]
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        fail(f"{label} path must be absolute: {path}")
    path = Path(os.path.normpath(path))
    home = Path.home().resolve()
    if path == home or home not in path.parents:
        fail(f"{label} must live below the current user's home: {path}")
    try:
        expected_mode = int(raw_mode, 8)
    except ValueError:
        fail(f"{label} expected mode is invalid: {raw_mode}")

    uid = os.getuid()
    current = home
    for part in path.relative_to(home).parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            fail(f"{label} path component is missing: {current}")
        if stat.S_ISLNK(info.st_mode):
            fail(f"{label} path component must not be a symlink: {current}")
        if info.st_uid != uid:
            fail(f"{label} path component is not user-owned: {current}")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            fail(f"{label} path component is group/world writable: {current}")

    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        fail(f"{label} is not a regular file: {path}")
    actual_mode = stat.S_IMODE(info.st_mode)
    if actual_mode != expected_mode:
        fail(
            f"{label} mode must be {oct(expected_mode)}, found {oct(actual_mode)}: {path}"
        )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
