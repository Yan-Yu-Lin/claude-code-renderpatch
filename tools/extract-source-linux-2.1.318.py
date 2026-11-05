#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Extract the exact official 2.1.318 Linux x64 Bun module graph.

Same record layout as the Darwin extractor; the payload lives in the ELF
section named `.bun` instead of the Mach-O `__BUN` segment.
"""

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

VERSION = "2.1.318"
STOCK_SHA = "708c77b204db30086ff6f1ed34577bda03e1be74ced80557cbf7b54249ebf0bd"
STOCK_SIZE = 337814032
NPM_PACKAGE = "@anthropic-ai/claude-code-linux-x64@2.1.318"
NPM_INTEGRITY = "sha512-GX+7CUng2R5f7SsA2w0LaXlH2f62fRCFD/Z2SUexoeH3B0KfulKQt5DtY9NeD2Yp3VEBz6/k/xWSbGPUi6NV2A=="
ROOT = "/$bunfs/root/"


def bun_section(stock):
    if stock[:4] != b"\x7fELF" or stock[4] != 2 or stock[5] != 1:
        raise ValueError("expected little-endian ELF64")
    shoff = struct.unpack_from("<Q", stock, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", stock, 0x3A)
    def header(i):
        return struct.unpack_from("<IIQQQQIIQQ", stock, shoff + i * shentsize)
    strtab = header(shstrndx)
    names = stock[strtab[4] : strtab[4] + strtab[5]]
    found = []
    for i in range(shnum):
        h = header(i)
        name = names[h[0] : names.index(b"\0", h[0])].decode()
        if name == ".bun":
            found.append(stock[h[4] : h[4] + h[5]])
    if len(found) != 1:
        raise ValueError(f"expected exactly one .bun section, found {len(found)}")
    return found[0]


def records(stock):
    if hashlib.sha256(stock).hexdigest() != STOCK_SHA or len(stock) != STOCK_SIZE:
        raise ValueError("stock SHA/size mismatch")
    section = bun_section(stock)
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
    import_paths = {
        r["name"]: r["name"] if r["loader"] == 13 else str(paths[r["name"]])
        for r in modules
    }
    for r in modules:
        path = paths[r["name"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = r["content"]
        if r["loader"] == 1:
            text = re.sub(r"^(?:// *@bun[^\n]*\n)+", "", data.decode())
            text = re.sub(
                r"/\$bunfs/root/[A-Za-z0-9/._$@+\-]+",
                lambda m: import_paths.get(m[0], m[0]),
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
