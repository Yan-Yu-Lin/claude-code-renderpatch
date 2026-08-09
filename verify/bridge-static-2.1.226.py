#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Statically verify the signed Claude Code 2.1.226 internal SDK bridge."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from semantic_bridge_2_1_226 import (
    BUN_END,
    BUN_OFFSET,
    EXPECTED_FILE_SIZE,
    EXPECTED_STOCK_SHA256,
    OUTPUT_NAME,
    VERSION,
    digest,
    discover_patches,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    stock_path = Path.home() / ".local/share/claude/versions" / VERSION
    binary_path = REPO / "patched" / OUTPUT_NAME
    stock = stock_path.read_bytes()
    candidate = binary_path.read_bytes()
    require(digest(stock) == EXPECTED_STOCK_SHA256, "stock SHA mismatch")
    require(len(stock) == EXPECTED_FILE_SIZE, "stock size mismatch")
    require(len(candidate) >= BUN_END, "candidate is shorter than live __BUN")

    patches = discover_patches(stock)
    require(len(patches) == 8, "expected eight co-located physical bridge ranges")
    for patch in patches:
        require(candidate.count(patch.old) == 0, f"{patch.name}: stock range remains")
        require(candidate.count(patch.new) == 1, f"{patch.name}: replacement count")
        require(candidate[patch.offset : patch.end] == patch.new, f"{patch.name}: offset")

    allowed = [range(patch.offset, patch.end) for patch in patches]
    changed = [
        offset
        for offset, (before, after) in enumerate(
            zip(stock[BUN_OFFSET:BUN_END], candidate[BUN_OFFSET:BUN_END], strict=True),
            start=BUN_OFFSET,
        )
        if before != after
    ]
    require(changed, "candidate __BUN is unchanged")
    require(
        all(any(offset in patch_range for patch_range in allowed) for offset in changed),
        "candidate changes bytes outside declared bridge ranges",
    )

    for domain in range(5):
        require(candidate.count(f"rpQ({domain},".encode()) == 1, f"q{domain} count")
    for domain in range(6):
        require(candidate.count(f"rpC({domain},".encode()) >= 1, f"d{domain} absent")
    require(candidate.count(b"globalThis.__rp?.q?.(") == 1, "q bypasses helper")
    require(candidate.count(b"globalThis.__rp?.c?.(") == 1, "c bypasses helper")
    require(
        candidate.count(
            b"function rpQ(...e){try{return globalThis.__rp?.q?.(...e)??e[1]}catch{return e[1]}}"
        )
        == 1,
        "q helper lost exact fallback",
    )
    require(
        candidate.count(b"function rpC(...e){try{globalThis.__rp?.c?.(...e)}catch{}}") == 1,
        "c helper can leak collision failures",
    )

    reset = next(p.new for p in patches if p.name == "renderer-reset")
    require(b"let s=(n||=!!rpQ(1,!1,t,n))?0:" in reset, "q1 row-zero gate")
    require(b"altScreen:n,viewportRows:e.viewport.height" in reset, "q1 serializer intent")
    require(
        candidate.count(b'case"clearTerminal":s+=a.altScreen?AUs():ehn(a.viewportRows);break;') == 1,
        "stock clear serializer changed",
    )

    toggle = next(p.new for p in patches if p.name == "renderer-toggle-redraw")
    require(b'L("tengu_toggle_transcript"' in toggle, "toggle telemetry missing")
    require(b"setTimeout(gSv,50)" in toggle, "q2 redraw timing changed")

    context = next(p.new for p in patches if p.name == "provider-context-window")
    for fragment in (b"ES(e)", b"dz.header", b"mz(e)", b"U1(e)", b"tri(e)", b"rpQ(3,"):
        require(fragment in context, f"context fallback missing {fragment!r}")

    routing = next(p.new for p in patches if p.name == "subagent-routing-static-d0")
    require(routing.count(b"rpQ(4,") == 1, "explicit routing gate count")
    require(b"if(XDp(d,t))return t" in routing, "frontmatter/default family gate changed")
    require(b"Ffa(ns(n))" in routing, "explicit alias resolver changed")
    require(
        b"rpC(0,0,4194303,[jD,ns,vc,Eo,Jy,BT,hC,Qmf,ES,U1,mz,Xmf,SHs,tri,sTt,fse,QDp,Ffa,XDp,V$b,LIr,K$b])"
        in routing,
        "d0 slot contract changed",
    )

    repl = next(p.new for p in patches if p.name == "repl-render-d4-static-d1")
    require(
        b"rpC(1,0,3194879,[Kp,Svr,T4s,lhn,ivd,v4s,kUs,AUs,ehn,nEd,Ywy,Vwy,Gwy,C$,,E,,,,,L,Te])"
        in repl,
        "d1 slot contract changed",
    )
    require(b"rpC(2,rp,63,[Ge,C$,Ge.getState,Ue,Ge.subscribe,Tfe])" in repl, "d2 slot contract")
    require(b"rpC(4,rp,65535,[Ge,Ue,wE,hr,zr,jt,ct,lr,er,Jo,CI,en,ue,Xd,cs,AI])" in repl, "d4 slot contract")
    require(b"rpC(2,rp,0,null),rpC(4,rp,0,null)" in repl, "d2/d4 cleanup")

    messages = next(p.new for p in patches if p.name == "renderer-messages-d3")
    require(messages.count(b"rpC(3,") == 2, "d3 publish/cleanup count")
    require(b"rpC(3,pe,0,null)" in messages, "d3 cleanup missing")

    payload = next(p.new for p in patches if p.name == "key-provider-d5-payload")
    require(b"d[24]=[++rpG,s,c,u,C,v,l,g,a,o]" in payload, "d5 payload slot order")
    lifecycle = next(p.new for p in patches if p.name == "key-provider-d5-lifecycle")
    require(b"rpC(5,e,511,n)" in lifecycle, "d5 publication")
    require(b"rpC(5,t,0,null)" in lifecycle, "d5 cleanup")
    require(lifecycle.count(b"useLayoutEffect") == 1, "d5 hook count changed")

    subprocess.run(["codesign", "--verify", "--strict", str(binary_path)], check=True)
    version = subprocess.run(
        [str(binary_path), "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    require(version == f"{VERSION} (Claude Code)", "candidate version mismatch")
    print(f"stock SHA-256: {digest(stock)}")
    print(f"candidate SHA-256: {digest(candidate)}")
    print(f"verified physical ranges: {len(patches)}")
    print(f"changed __BUN byte positions: {len(changed)}")
    print("policy domains q0-q4 and capture domains d0-d5 verified")
    print("codesign and version verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
