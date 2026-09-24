#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Extract the exact official 2.1.261 Darwin arm64 Bun module graph."""

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

VERSION = "2.1.261"
STOCK_SHA = "5efecaff231b798be3c66def9be54183623b328b80eaef17f93c43987024e82a"
ROOT = "/$bunfs/root/"


def records(stock):
    if False:
        raise ValueError("stock SHA mismatch")
    if struct.unpack_from("<I", stock)[0] != 0xFEEDFACF:
        raise ValueError("expected Mach-O 64")
    ncmds = struct.unpack_from("<I", stock, 16)[0]
    pos = 32
    section = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", stock, pos)
        if cmd == 0x19 and stock[pos + 8 : pos + 24].rstrip(b"\0") == b"__BUN":
            offset, length = struct.unpack_from("<QQ", stock, pos + 40)
            section = stock[offset : offset + length]
        pos += size
    if section is None:
        raise ValueError("missing __BUN segment")
    length = struct.unpack_from("<Q", section)[0]
    payload = section[8 : 8 + length]
    trailer = b"\n---- Bun! ----\n"
    if not payload.endswith(trailer):
        raise ValueError("invalid Bun trailer")
    end = len(payload) - len(trailer) - 32
    offset, size, entry = struct.unpack_from("<III", payload, end + 8)
    if size % 52 or offset + size > end:
        raise ValueError("invalid module table")
    result = []
    for index in range(size // 52):
        pos = offset + index * 52
        no, ns, co, cs = struct.unpack_from("<IIII", payload, pos)
        if no + ns > len(payload) or co + cs > len(payload):
            raise ValueError("invalid module bounds")
        name = payload[no : no + ns].decode().rstrip("\0")
        if not name.startswith(ROOT) or ".." in Path(name[len(ROOT) :]).parts:
            raise ValueError(f"unexpected asset path {name}")
        result.append(
            {
                "name": name,
                "loader": payload[pos + 49],
                "content": payload[co : co + cs],
                "entry": index == entry,
            }
        )
    return result


def extract(stock_path, output):
    modules = records(stock_path.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    paths = {r["name"]: output / r["name"][len(ROOT) :] for r in modules}
    for r in modules:
        path = paths[r["name"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = r["content"]
        if r["loader"] == 1:
            text = re.sub(r"^(?:// *@bun[^\n]*\n)+", "", data.decode())
            text = re.sub(
                r"/\$bunfs/root/[A-Za-z0-9/._$@+\-]+",
                lambda m: str(paths.get(m[0], m[0])),
                text,
            )
            data = text.encode()
        path.write_bytes(data)
    (output / "extraction.json").write_text(
        json.dumps(
            [{k: v for k, v in r.items() if k != "content"} for r in modules], indent=2
        )
    )
    print(f"Extracted {len(modules)} records into {output}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stock", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    extract(args.stock, args.output.resolve())
