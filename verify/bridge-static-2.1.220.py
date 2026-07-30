#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Statically verify the signed Claude Code 2.1.220 internal SDK bridge."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from semantic_bridge_2_1_220 import (
    BUN_END,
    BUN_OFFSET,
    EXPECTED_FILE_SIZE,
    EXPECTED_STOCK_SHA256,
    OUTPUT_NAME,
    VERSION,
    digest,
    discover_patches,
)

DEFAULT_STOCK = Path.home() / ".local/share/claude/versions" / VERSION
DEFAULT_BINARY = REPO / "patched" / OUTPUT_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    args = parse_args()
    stock_path = args.stock.expanduser().resolve()
    binary_path = args.binary.expanduser().resolve()
    stock = stock_path.read_bytes()
    candidate = binary_path.read_bytes()

    require(digest(stock) == EXPECTED_STOCK_SHA256, "stock SHA-256 mismatch")
    require(len(stock) == EXPECTED_FILE_SIZE, "stock length mismatch")
    require(
        len(candidate) >= BUN_END,
        "signed candidate is shorter than the complete live __BUN section",
    )

    patches = discover_patches(stock)
    for patch in patches:
        require(candidate.count(patch.old) == 0, f"{patch.name}: stock anchor remains")
        require(
            candidate.count(patch.new) == 1,
            f"{patch.name}: expected exactly one replacement",
        )
        require(
            candidate[patch.offset : patch.end] == patch.new,
            f"{patch.name}: replacement is not at its verified live offset",
        )

    allowed = [range(patch.offset, patch.end) for patch in patches]
    bun_diff_offsets = [
        offset
        for offset, (before, after) in enumerate(
            zip(stock[BUN_OFFSET:BUN_END], candidate[BUN_OFFSET:BUN_END], strict=True),
            start=BUN_OFFSET,
        )
        if before != after
    ]
    require(bun_diff_offsets, "candidate __BUN section is unchanged")
    unexpected = [
        offset
        for offset in bun_diff_offsets
        if not any(offset in patch_range for patch_range in allowed)
    ]
    require(
        not unexpected,
        f"unexpected __BUN changes outside bridge ranges: {unexpected[:20]}",
    )
    for patch in patches:
        require(
            any(
                offset in range(patch.offset, patch.end) for offset in bun_diff_offsets
            ),
            f"{patch.name}: replacement range contains no changed bytes",
        )

    q_snippets = {
        0: b"rpQ(0,0,l)",
        1: b"rpQ(1,!1,t,n)",
        2: b"rpQ(2,!1,!0)",
        3: b"rpQ(3,",
        4: b"rpQ(4,",
    }
    for domain, snippet in q_snippets.items():
        require(
            candidate.count(snippet) == 1,
            f"policy domain {domain}: expected one bridge query",
        )
    require(
        candidate.count(
            b"function rpQ(...e){try{return globalThis.__rp?.q?.(...e)??e[1]}"
            b"catch{return e[1]}}"
        )
        == 1,
        "policy collision helper is absent or does not return the exact fallback",
    )
    require(
        candidate.count(
            b"function rpC(...e){try{globalThis.__rp?.c?.(...e)}catch{}}"
        )
        == 1,
        "capture collision helper is absent or can propagate a collision error",
    )
    require(
        candidate.count(b"globalThis.__rp?.q?.(") == 1,
        "a policy site bypasses the collision helper",
    )
    require(
        candidate.count(b"globalThis.__rp?.c?.(") == 1,
        "a capture site bypasses the collision helper",
    )

    messages_query = candidate.find(q_snippets[0])
    pre_cap = candidate.find(b"te=re||H?0:Xhf(e,ce,2*oe)")
    transcript_gate = candidate.find(b"&&!u&&!re,{collapsedBase:Ue")
    final_cap = candidate.find(b"Xhf(at,se,oe)")
    require(
        messages_query < pre_cap < transcript_gate < final_cap,
        "Messages query is not before transcript truncation and both caps",
    )
    require(
        candidate.count(b"u||=!!(1&K),H||=!!(2&K)") == 1,
        "Messages bitmask is not folded once into both effective locals",
    )

    require(
        candidate.count(
            b'case"clearTerminal":s+=a.altScreen?Oms():_Xr(a.viewportRows);break;'
        )
        == 1,
        "stock Hms clear serializer changed or disappeared",
    )
    reset_region = next(
        patch.new for patch in patches if patch.name == "renderer-reset"
    )
    require(
        b"let s=(n||=!!rpQ(1,!1,t,n))?0:" in reset_region,
        "reset authorization does not atomically feed row-zero selection",
    )
    require(
        b"altScreen:n,viewportRows:e.viewport.height" in reset_region,
        "reset authorization does not reach the existing serializer intent field",
    )

    toggle_region = next(
        patch.new for patch in patches if patch.name == "renderer-toggle-redraw"
    )
    require(
        b'M("tengu_toggle_transcript"' in toggle_region,
        "toggle telemetry was not preserved",
    )
    require(
        b"setTimeout(oFS,50)" in toggle_region,
        "toggle redraw is not binary-owned at 50ms",
    )

    context_region = next(
        patch.new for patch in patches if patch.name == "provider-context-window"
    )
    for fragment in (
        b"Wb(e)",
        b"Cye.header",
        b"tG(e)",
        b"OH(e)",
        b"fro(e)",
        b"Z.CLAUDE_CODE_MAX_CONTEXT_TOKENS",
        b'.startsWith("claude-")',
        b"rpQ(3,",
    ):
        require(
            fragment in context_region,
            f"context fallback fragment missing: {fragment!r}",
        )

    routing_region = next(
        patch.new for patch in patches if patch.name == "subagent-routing-static-d0"
    )
    require(
        routing_region.count(b"rpQ(4,") == 1,
        "first explicit routing gate is not bridged exactly once",
    )
    require(
        routing_region.count(b"if(Xrd(_,r))return r") == 1,
        "second default/frontmatter Xrd gate was not preserved exactly once",
    )
    require(
        b"Jrd(Ei(t))" in routing_region,
        "downstream explicit alias resolution changed",
    )

    subprocess.run(
        ["codesign", "--verify", "--strict", "--verbose=2", str(binary_path)],
        check=True,
    )
    version = subprocess.run(
        [str(binary_path), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    require(version == f"{VERSION} (Claude Code)", "candidate --version mismatch")

    print(f"stock SHA-256: {digest(stock)}")
    print(f"candidate SHA-256: {digest(candidate)}")
    print(f"candidate size: {len(candidate)}")
    print(f"verified bridge sites: {len(patches)}")
    for patch in patches:
        print(f"  {patch.name}: offset={patch.offset} length={patch.length}")
    print(f"changed __BUN byte positions: {len(bun_diff_offsets)}")
    print("policy queries: domains 0,1,2,3,4 exactly once")
    print("reset consolidation: CXr row-zero plus stock Hms serializer intent")
    print("codesign: strict verification passed")
    print(f"version: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
