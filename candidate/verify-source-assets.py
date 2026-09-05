# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify an immutable source release without importing any release code."""

import hashlib
import json
import os
import stat
import sys
from pathlib import Path


def main():
    root = Path(sys.argv[1])
    marker = sys.argv[2]
    home = Path.home().resolve()
    uid = os.getuid()
    if not root.is_absolute() or home not in root.parents:
        raise ValueError("release must be below home")
    current = home
    for part in root.relative_to(home).parts:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
            raise ValueError(f"untrusted release directory: {current}")
    manifest = json.loads((root / "release-manifest.json").read_text())
    assets = manifest["assets"]
    allowed = set(assets) | {
        "release-manifest.json",
        ".claude-renderpatch-release",
        "claude-renderpatch-candidate",
    }
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        if info.st_uid != uid or stat.S_ISLNK(info.st_mode):
            raise ValueError(f"untrusted asset: {path}")
        if stat.S_ISDIR(info.st_mode):
            expected = 0o555
        elif stat.S_ISREG(info.st_mode):
            rel = path.relative_to(root).as_posix()
            if rel not in allowed:
                raise ValueError(f"unlisted asset: {rel}")
            expected = assets.get(rel, {}).get(
                "mode", 0o555 if rel == "claude-renderpatch-candidate" else 0o444
            )
        else:
            raise ValueError(f"not a regular asset: {path}")
        if stat.S_IMODE(info.st_mode) != expected:
            raise ValueError(f"asset mode mismatch: {path}")
    for rel, expected in assets.items():
        sub = Path(rel)
        if sub.is_absolute() or ".." in sub.parts:
            raise ValueError("unsafe manifest path")
        path = root / sub
        if not path.is_file():
            raise ValueError(f"missing asset: {rel}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError(f"asset hash mismatch: {rel}")
    if (root / ".claude-renderpatch-release").read_text().strip() != marker:
        raise ValueError("release marker mismatch")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"claude-renderpatch-candidate: {error}")
