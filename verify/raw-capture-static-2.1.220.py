#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Statically verify the six Claude Code 2.1.220 raw capture domains."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from semantic_bridge_2_1_220 import OUTPUT_NAME, VERSION, discover_patches

DEFAULT_STOCK = Path.home() / ".local/share/claude/versions" / VERSION
DEFAULT_BINARY = REPO / "patched" / OUTPUT_NAME
MANIFEST = REPO / "manifests" / "internal-sdk-2.1.220.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def region(patches: dict[str, object], name: str) -> bytes:
    patch = patches[name]
    return patch.new.rstrip(b" ")


def main() -> int:
    args = parse_args()
    stock = args.stock.expanduser().resolve().read_bytes()
    candidate = args.binary.expanduser().resolve().read_bytes()
    patch_list = discover_patches(stock)
    patches = {patch.name: patch for patch in patch_list}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    capture_domains = manifest["captureDomains"]
    require(len(capture_domains) == 6, "manifest no longer declares exactly d0-d5")
    expected_bitmaps = {
        domain["numericId"]: sum(1 << slot["index"] for slot in domain["slots"])
        for domain in capture_domains
    }
    require(
        expected_bitmaps
        == {0: 4194303, 1: 16777215, 2: 63, 3: 65535, 4: 65535, 5: 511},
        f"unexpected manifest bitmaps: {expected_bitmaps}",
    )

    require(
        candidate.count(
            b"function rpQ(...e){try{return globalThis.__rp?.q?.(...e)??e[1]}"
            b"catch{return e[1]}}"
        )
        == 1,
        "policy helper does not contain the collision-safe exact fallback",
    )
    require(
        candidate.count(
            b"function rpC(...e){try{globalThis.__rp?.c?.(...e)}catch{}}"
        )
        == 1,
        "capture helper does not swallow collision failures",
    )
    require(candidate.count(b"++rpG") == 4, "dynamic generations are not four monotonic lexical increments")

    d0 = region(patches, "subagent-routing-static-d0")
    d0_call = b"rpC(0,0,4194303,[HH,Ei,Hl,lo,n_,ww,JE,SZc,Wb,OH,tG,bZc,gYi,fro,cst,ite,Qrd,Jrd,Xrd,tO_,Cur,rO_])"
    require(d0.count(d0_call) == 1, "d0 slot order/bitmap differs from the manifest")
    require(d0.find(b"ts(),") < d0.find(d0_call), "d0 publishes before its initializer dependencies finish")

    d1 = region(patches, "repl-render-d4-static-d1")
    d1_call = b"rpC(1,0,~0>>>8,[xd,Qsr,Rhs,CXr,vUu,khs,Hms,Oms,_Xr,S3u,Ju_,Kpe,QHt,sM,Krl,w,gqe,SMe,R7,N5,M,lb,PAl,SEi])"
    require(d1.count(d1_call) == 1, "d1 slot order/bitmap differs from the manifest")
    require(
        d1.find(b"OGt={") < d1.find(b"rpS||(rpS=1,") < d1.find(d1_call),
        "d1 does not publish once from the initialized Ahl render scope",
    )

    d2 = region(patches, "app-provider-d2")
    require(
        d2.count(b"rpC(2,e,63,[h,sM,h.getState,h.setState,h.subscribe,Gae])") == 1,
        "d2 app-store slots or bitmap changed",
    )
    require(d2.count(b"rpC(2,e,0,null)") == 1, "d2 lacks matching-generation cleanup")
    require(
        d2.find(b"let e=++rpG") < d2.find(b"rpC(2,e,63") < d2.find(b"rpC(2,e,0,null)"),
        "d2 generation, publish, and cleanup are not lexically ordered",
    )

    d3 = region(patches, "renderer-messages-d3")
    d3_call = b"rpC(3,rp,65535,[e,Ee,Ue,at,Ze,te,ce,se,ze,nt,re,oe,l,u,H,L])"
    require(d3.count(d3_call) == 1, "d3 Messages slots or bitmap changed")
    require(d3.count(b"rpC(3,rp,0,null)") == 1, "d3 lacks matching-generation cleanup")
    require(
        d3.find(b"Ze=z_.useMemo") < d3.find(b"rp=++rpG") < d3.find(d3_call),
        "d3 does not publish after the final Messages stage exists",
    )
    require(b"[Re,Ce,g,ge,rp]" in d3, "d3 cleanup effect is not refreshed for every render generation")

    d4 = region(patches, "repl-render-d4-static-d1")
    d4_call = b"rpC(4,rp,65535,[at,Le,ug,lr,It,fr,Ot,Cr,yr,Dn,rU,_o,ee,Py,Gr,OGt])"
    require(d4.count(d4_call) == 1, "d4 REPL slots or bitmap changed")
    require(d4.count(b"rpC(4,rp,0,null)") == 1, "d4 lacks matching-generation cleanup")
    require(
        d4.find(b"OGt={") < d4.find(b"rp=++rpG") < d4.find(d4_call),
        "d4 publishes before the compact control props exist",
    )
    require(b"[Em,di,vn,ic,rp]" in d4, "d4 cleanup effect is not refreshed for every render generation")

    d5_payload = region(patches, "key-provider-d5-payload")
    require(
        d5_payload.count(b"d[24]=[++rpG,s,c,u,C,v,l,g,a,o]") == 1,
        "d5 payload does not preserve manager/bindings/ref slot order",
    )
    require(
        d5_payload.find(b"d[20]=s") < d5_payload.find(b"d[24]=[++rpG") < d5_payload.find(b"dgo.Provider"),
        "d5 payload is not assembled after the manager and before the provider",
    )
    require(
        d5_payload.count(b"kFe.cloneElement(x,{__rp:d[24]})") == 1,
        "d5 payload is not passed to the existing cZs lifecycle owner",
    )

    d5_lifecycle = region(patches, "key-provider-d5-lifecycle")
    require(d5_lifecycle.count(b"rpC(5,t,511,n)") == 1, "d5 publish bitmap or positional slice changed")
    require(d5_lifecycle.count(b"rpC(5,t,0,null)") == 1, "d5 lacks matching-generation cleanup")
    require(b"n[22]!==d" in d5_lifecycle and b"x=[d]" in d5_lifecycle, "d5 layout effect is not keyed to the cached provider generation")
    require(d5_lifecycle.count(b"useLayoutEffect") == 1, "d5 changed the existing layout-hook count")

    for domain in range(6):
        publish_prefix = f"rpC({domain},".encode()
        require(candidate.count(publish_prefix) >= 1, f"capture domain {domain} is absent")

    for domain in range(5):
        require(
            candidate.count(f"rpQ({domain},".encode()) == 1,
            f"policy domain {domain} is not present exactly once",
        )
    require(
        candidate.count(b"globalThis.__rp?.q?.(") == 1
        and candidate.count(b"globalThis.__rp?.c?.(") == 1,
        "a q/c site bypasses the collision-safe helpers",
    )

    print(f"verified physical bridge sites: {len(patch_list)}")
    print("raw captures: d0-d5 present with manifest slot order and bitmaps")
    print("static lifecycle: d0/d1 generation 0 after dependency initialization")
    print("dynamic lifecycle: four monotonic lexical generation increments")
    print("cleanup lifecycle: d2-d5 matching-generation bitmap-0/null clears")
    print("React hooks: no new d5 hook; existing layout effect remains exactly once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
