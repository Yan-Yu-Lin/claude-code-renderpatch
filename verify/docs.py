#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:")


def github_slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = "".join(char for char in text if char.isalnum() or char in " _-")
    return re.sub(r"[\s-]+", "-", text).strip("-")


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        base = github_slug(match.group(2))
        if not base:
            continue
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def iter_markdown_files(root: Path) -> list[Path]:
    files = [root / "README.md"]
    for directory in (root / "docs", root / "reference"):
        if directory.exists():
            files.extend(sorted(directory.rglob("*.md")))
    return [path for path in files if path.is_file()]


def check_link(source: Path, raw_target: str, anchor_cache: dict[Path, set[str]]) -> str | None:
    target = raw_target.strip()
    if not target or target.startswith(EXTERNAL_SCHEMES):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = unquote(target)
    if target.startswith("#"):
        destination = source
        anchor = target[1:]
    else:
        file_part, separator, anchor = target.partition("#")
        if Path(file_part).is_absolute():
            return None
        destination = (source.parent / file_part).resolve()
        if not separator:
            anchor = ""

    if not destination.exists():
        return f"missing file: {raw_target}"
    if anchor and destination.suffix.lower() == ".md":
        line_anchor = re.fullmatch(r"L(\d+)(?:-L(\d+))?", anchor, re.IGNORECASE)
        if line_anchor:
            start = int(line_anchor.group(1))
            end = int(line_anchor.group(2) or start)
            line_count = len(destination.read_text(encoding="utf-8").splitlines())
            if start < 1 or end < start or end > line_count:
                return f"invalid line anchor: {raw_target}"
            return None
        anchors = anchor_cache.setdefault(destination, markdown_anchors(destination))
        if anchor.lower() not in anchors:
            return f"missing anchor: {raw_target}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local Markdown links and anchors.")
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()

    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    files = iter_markdown_files(root)
    for source in files:
        text = source.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_PATTERN.finditer(line):
                error = check_link(source, match.group(1), anchor_cache)
                if error:
                    errors.append(f"{source.relative_to(root)}:{line_number}: {error}")

    if errors:
        print("Markdown link validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Validated {len(files)} Markdown files: all local links and anchors resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
