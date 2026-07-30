#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behaviorally verify the Claude Code 2.1.220 internal SDK policy plane."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from semantic_bridge_2_1_220 import (
    OUTPUT_NAME,
    VERSION,
    discover_patches,
)

DEFAULT_STOCK = Path.home() / ".local/share/claude/versions" / VERSION
DEFAULT_BINARY = REPO / "patched" / OUTPUT_NAME
BOOTSTRAP = REPO / "preload" / "bootstrap.mjs"
FIXTURE_PARENT = REPO / "patched" / "bridge-fixtures"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument(
        "--session",
        type=Path,
        help="optional disposable source JSONL for live PTY Ctrl+O/resize tests",
    )
    parser.add_argument("--startup-seconds", type=float, default=3.0)
    parser.add_argument("--phase-seconds", type=float, default=4.0)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_stub(path: Path, mode: str, log_path: Path) -> None:
    policy = (
        "return fallback;"
        if mode == "fallback"
        else "return id===0?3:id===1||id===2?true:id===3?372000:id===4?false:fallback;"
    )
    path.write_text(
        "import {appendFileSync} from 'node:fs';\n"
        f"const log={json.dumps(str(log_path))};\n"
        "appendFileSync(log,JSON.stringify({event:'loaded'})+'\\n');\n"
        "const facade=Object.freeze({\n"
        "q(id,fallback,...payload){appendFileSync(log,JSON.stringify({event:'q',id,fallback,payload})+'\\n');"
        f"{policy}" + "},\n"
        "c(){}\n"
        "});\n"
        "Object.defineProperty(globalThis,'__rp',{value:facade,enumerable:false,writable:false,configurable:false});\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_collision_stub(path: Path, mode: str) -> None:
    if mode == "noncallable":
        facade = "Object.freeze({q:1,c:1})"
    elif mode == "throwing":
        facade = "Object.freeze({q(){throw Error('q collision')},c(){throw Error('c collision')}})"
    else:
        facade = "Object.freeze({get q(){throw Error('q getter collision')},get c(){throw Error('c getter collision')}})"
    path.write_text(
        f"const facade={facade};\n"
        "Object.defineProperty(globalThis,'__rp',{value:facade,enumerable:false,"
        "writable:false,configurable:false});\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def extract_functions(stock: bytes, candidate: bytes) -> dict[str, str]:
    patches = {patch.name: patch for patch in discover_patches(stock)}
    reset = candidate[
        patches["renderer-reset"].offset : patches["renderer-reset"].end
    ].decode("utf-8")
    context = candidate[
        patches["provider-context-window"].offset : patches[
            "provider-context-window"
        ].end
    ].decode("utf-8")
    routing = candidate[
        patches["subagent-routing-static-d0"].offset : patches[
            "subagent-routing-static-d0"
        ].end
    ].decode("utf-8")
    return {
        "reset": reset[: reset.index("function vUu")],
        "context": context[: context.index("function TZc")],
        "routing": routing[: routing.index("function Qrd")],
    }


def run_semantic_tests(fixture_root: Path, stock: bytes, candidate: bytes) -> None:
    functions = extract_functions(stock, candidate)
    script = fixture_root / "semantic-tests.mjs"
    script.write_text(
        "import assert from 'node:assert/strict';\n"
        "const clearFacade=()=>{try{delete globalThis.__rp}catch{} };\n"
        "const getterFacade=()=>Object.defineProperty({},'q',{get(){throw Error('getter collision')}});\n"
        "class khs{constructor(cursor,width){this.cursor={...cursor};this.viewportWidth=width;this.diff=[]}}\n"
        "function vUu(builder,frame,start){builder.diff.push({type:'sliceProbe',start});return builder}\n"
        + functions["reset"]
        + "\n"
        "const frame={screen:{height:100},viewport:{height:30,width:80}};\n"
        "function resetCall(facade,alt=false){clearFacade();if(facade)globalThis.__rp=facade;return CXr(frame,'resize',{},alt,20,{})}\n"
        "let reset=resetCall(null);assert.equal(reset[0].altScreen,false);assert.equal(reset[1].start,20);\n"
        "reset=resetCall({q:(id,fallback)=>fallback});assert.equal(reset[0].altScreen,false);assert.equal(reset[1].start,20);\n"
        "reset=resetCall({q:1});assert.equal(reset[0].altScreen,false);assert.equal(reset[1].start,20);\n"
        "reset=resetCall({q(){throw Error('collision')}});assert.equal(reset[0].altScreen,false);assert.equal(reset[1].start,20);\n"
        "reset=resetCall(getterFacade());assert.equal(reset[0].altScreen,false);assert.equal(reset[1].start,20);\n"
        "let resetCalls=[];reset=resetCall({q:(...args)=>(resetCalls.push(args),true)});"
        "assert.equal(reset[0].altScreen,true);assert.equal(reset[1].start,0);"
        "assert.deepEqual(resetCalls,[[1,false,'resize',false]]);\n"
        "reset=resetCall(null,true);assert.equal(reset[0].altScreen,true);assert.equal(reset[1].start,0);\n"
        "function messages(u,H,l,facade){clearFacade();if(facade)globalThis.__rp=facade;"
        "let K=0,Y=(K=rpQ(0,0,l)|0,u||=!!(K&1),H||=!!(K&2));return{u,H,Y,K}}\n"
        "assert.deepEqual(messages(false,false,'prompt',null),{u:false,H:false,Y:false,K:0});\n"
        "assert.deepEqual(messages(true,false,'transcript',null),{u:true,H:false,Y:false,K:0});\n"
        "assert.deepEqual(messages(false,false,'prompt',{q:()=>3}),{u:true,H:true,Y:true,K:3});\n"
        "assert.deepEqual(messages(false,false,'prompt',{q:()=>2}),{u:false,H:true,Y:true,K:2});\n"
        "assert.deepEqual(messages(false,false,'prompt',{q:1}),{u:false,H:false,Y:false,K:0});\n"
        "assert.deepEqual(messages(false,false,'prompt',{q(){throw Error('collision')}}),{u:false,H:false,Y:false,K:0});\n"
        "assert.deepEqual(messages(false,false,'prompt',getterFacade()),{u:false,H:false,Y:false,K:0});\n"
        "let scheduled=[];let oFS=()=>scheduled.push('redraw');let setTimeout=(fn,delay)=>{scheduled.push(delay);fn()};\n"
        "function toggle(Pui,facade){clearFacade();if(facade)globalThis.__rp=facade;"
        'Pui!=="transcript"&&rpQ(2,!1,!0)&&setTimeout(oFS,50)}\n'
        "toggle('prompt',null);assert.deepEqual(scheduled,[]);\n"
        "toggle('prompt',{q:(id,f)=>f});assert.deepEqual(scheduled,[]);\n"
        "toggle('prompt',{q:()=>true});assert.deepEqual(scheduled,[50,'redraw']);scheduled=[];\n"
        "toggle('prompt',{q:1});assert.deepEqual(scheduled,[]);\n"
        "toggle('prompt',{q(){throw Error('collision')}});assert.deepEqual(scheduled,[]);\n"
        "toggle('prompt',getterFacade());assert.deepEqual(scheduled,[]);\n"
        "let exitCalls=0;toggle('transcript',{q:()=>{exitCalls++;return true}});"
        "assert.equal(exitCalls,0);assert.deepEqual(scheduled,[]);\n"
        "let ctx={};const Wb=()=>!!ctx.wb,Cye={header:'1m'},tG=()=>!!ctx.tg,OH=()=>!!ctx.oh,"
        "fro=()=>ctx.fro??null,Z={CLAUDE_CODE_MAX_CONTEXT_TOKENS:undefined},lo=x=>x,Ei=x=>x,_er=200000;\n"
        + functions["context"]
        + "\n"
        "function contextCall(next,facade){ctx={...next};Z.CLAUDE_CODE_MAX_CONTEXT_TOKENS=ctx.env;"
        "clearFacade();if(facade)globalThis.__rp=facade;return SZc(ctx.model??'claude-sonnet-5',ctx.headers)}\n"
        "assert.equal(contextCall({wb:true}),1e6);"
        "assert.equal(contextCall({headers:['1m'],tg:true}),1e6);"
        "assert.equal(contextCall({oh:true}),1e6);"
        "assert.equal(contextCall({fro:333333}),333333);"
        "assert.equal(contextCall({model:'kimi-k3',env:444444}),444444);"
        "assert.equal(contextCall({model:'claude-sonnet-5'}),200000);\n"
        "let contextArgs;assert.equal(contextCall({model:'kimi-k3',env:444444},{q:(...a)=>(contextArgs=a,262144)}),262144);"
        "assert.deepEqual(contextArgs,[3,444444,'kimi-k3']);\n"
        "assert.equal(contextCall({model:'kimi-k3',env:444444},{q:1}),444444);\n"
        "assert.equal(contextCall({model:'kimi-k3',env:444444},{q(){throw Error('collision')}}),444444);\n"
        "assert.equal(contextCall({model:'kimi-k3',env:444444},getterFacade()),444444);\n"
        "const HH=()=> 'default-parent',rO_=()=>{},Qs=x=>String(x),"
        "Hl=()=>true,Fzn=()=>null,n_=()=> 'firstParty',kot=(p)=>p,Jrd=x=>'resolved:'+x,"
        "tO_=()=> 'inherit',Xrd=(requested,parent)=>requested==='opus'&&parent.includes('opus');"
        "Z.CLAUDE_CODE_SUBAGENT_MODEL=undefined;\n" + functions["routing"] + "\n"
        "clearFacade();assert.equal(ite(undefined,'claude-opus-parent','opus'), 'claude-opus-parent');\n"
        "globalThis.__rp={q:1};assert.equal(ite(undefined,'claude-opus-parent','opus'),'claude-opus-parent');\n"
        "globalThis.__rp={q(){throw Error('collision')}};assert.equal(ite(undefined,'claude-opus-parent','opus'),'claude-opus-parent');\n"
        "globalThis.__rp=getterFacade();assert.equal(ite(undefined,'claude-opus-parent','opus'),'claude-opus-parent');\n"
        "let routeArgs;globalThis.__rp={q:(...a)=>(routeArgs=a,false)};"
        "assert.equal(ite(undefined,'claude-opus-parent','opus'),'resolved:opus');"
        "assert.deepEqual(routeArgs,[4,true,'opus','claude-opus-parent']);\n"
        "routeArgs=undefined;assert.equal(ite('opus','claude-opus-parent',undefined),'claude-opus-parent');"
        "assert.equal(routeArgs,undefined);\n"
        "console.log('semantic bridge behavior tests passed');\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bun", str(script)], check=True, capture_output=True, text=True
    )
    print(result.stdout.strip())


def run_version_path(binary: Path, preload: Path | None, log: Path | None) -> str:
    env = os.environ.copy()
    env.pop("BUN_OPTIONS", None)
    if preload is not None:
        env["BUN_OPTIONS"] = f"--preload={preload}"
    result = subprocess.run(
        [str(binary), "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    version = result.stdout.strip()
    require(version == f"{VERSION} (Claude Code)", f"unexpected version: {version!r}")
    if log is not None:
        events = [json.loads(line) for line in log.read_text().splitlines()]
        require(
            events == [{"event": "loaded"}], "--version unexpectedly queried policy"
        )
    return version


def run_pty_variant(
    name: str,
    binary: Path,
    session: Path,
    output_dir: Path,
    startup_seconds: float,
    phase_seconds: float,
    preload: Path | None,
) -> dict[str, object]:
    env = os.environ.copy()
    env.pop("BUN_OPTIONS", None)
    if preload is not None:
        env["BUN_OPTIONS"] = f"--preload={preload}"
    command = [
        "uv",
        "run",
        str(REPO / "verify" / "pty-harness.py"),
        str(binary),
        "--session",
        str(session),
        "--startup-seconds",
        str(startup_seconds),
        "--phase-seconds",
        str(phase_seconds),
        "--output-dir",
        str(output_dir),
    ]
    result = subprocess.run(
        command, check=True, capture_output=True, text=True, env=env
    )
    print(f"\n{name}\n{result.stdout.strip()}")
    return json.loads((output_dir / "summary.json").read_text())


def ed3_by_phase(summary: dict[str, object]) -> dict[str, int]:
    phases = summary["phases"]
    assert isinstance(phases, list)
    return {str(phase["phase"]): int(phase["ed3"]) for phase in phases}


def main() -> int:
    args = parse_args()
    stock_path = args.stock.expanduser().resolve()
    binary_path = args.binary.expanduser().resolve()
    stock = stock_path.read_bytes()
    candidate = binary_path.read_bytes()
    discover_patches(stock)

    fixture_root = FIXTURE_PARENT / f"run-{int(time.time())}-{os.getpid()}"
    fixture_root.mkdir(parents=True, exist_ok=False)
    fallback_stub = fixture_root / "fallback.mjs"
    bridge_stub = fixture_root / "bridge-on.mjs"
    noncallable_stub = fixture_root / "collision-noncallable.mjs"
    throwing_stub = fixture_root / "collision-throwing.mjs"
    getter_stub = fixture_root / "collision-getter.mjs"
    fallback_log = fixture_root / "fallback.jsonl"
    bridge_log = fixture_root / "bridge-on.jsonl"
    write_stub(fallback_stub, "fallback", fallback_log)
    write_stub(bridge_stub, "bridge", bridge_log)
    write_collision_stub(noncallable_stub, "noncallable")
    write_collision_stub(throwing_stub, "throwing")
    write_collision_stub(getter_stub, "getter")

    run_semantic_tests(fixture_root, stock, candidate)
    print(f"no-preload version: {run_version_path(binary_path, None, None)}")
    print(f"bootstrap-only version: {run_version_path(binary_path, BOOTSTRAP, None)}")
    print(
        "fallback-preload version: "
        f"{run_version_path(binary_path, fallback_stub, fallback_log)}"
    )
    print(
        "bridge-preload version: "
        f"{run_version_path(binary_path, bridge_stub, bridge_log)}"
    )
    print(
        "noncallable-collision version: "
        f"{run_version_path(binary_path, noncallable_stub, None)}"
    )
    print(
        "throwing-collision version: "
        f"{run_version_path(binary_path, throwing_stub, None)}"
    )
    print(
        "getter-collision version: "
        f"{run_version_path(binary_path, getter_stub, None)}"
    )

    if args.session is None:
        print("PTY behavior: skipped (pass --session with a disposable source JSONL)")
        print(f"fixtures: {fixture_root}")
        return 0

    source_session = args.session.expanduser().resolve()
    require(source_session.is_file(), f"session JSONL not found: {source_session}")

    def session_copy(name: str) -> Path:
        path = fixture_root / f"session-{name}.jsonl"
        shutil.copy2(source_session, path)
        return path

    # Reset logs after the --version preload checks.
    fallback_log.write_text("", encoding="utf-8")
    bridge_log.write_text("", encoding="utf-8")
    summaries = {
        "stock": run_pty_variant(
            "stock",
            stock_path,
            session_copy("stock"),
            fixture_root / "pty-stock",
            args.startup_seconds,
            args.phase_seconds,
            None,
        ),
        "patched-no-preload": run_pty_variant(
            "patched-no-preload",
            binary_path,
            session_copy("no-preload"),
            fixture_root / "pty-no-preload",
            args.startup_seconds,
            args.phase_seconds,
            None,
        ),
        "patched-bootstrap-only": run_pty_variant(
            "patched-bootstrap-only",
            binary_path,
            session_copy("bootstrap-only"),
            fixture_root / "pty-bootstrap-only",
            args.startup_seconds,
            args.phase_seconds,
            BOOTSTRAP,
        ),
        "patched-fallback": run_pty_variant(
            "patched-fallback",
            binary_path,
            session_copy("fallback"),
            fixture_root / "pty-fallback",
            args.startup_seconds,
            args.phase_seconds,
            fallback_stub,
        ),
        "patched-collision-noncallable": run_pty_variant(
            "patched-collision-noncallable",
            binary_path,
            session_copy("collision-noncallable"),
            fixture_root / "pty-collision-noncallable",
            args.startup_seconds,
            args.phase_seconds,
            noncallable_stub,
        ),
        "patched-collision-throwing": run_pty_variant(
            "patched-collision-throwing",
            binary_path,
            session_copy("collision-throwing"),
            fixture_root / "pty-collision-throwing",
            args.startup_seconds,
            args.phase_seconds,
            throwing_stub,
        ),
        "patched-collision-getter": run_pty_variant(
            "patched-collision-getter",
            binary_path,
            session_copy("collision-getter"),
            fixture_root / "pty-collision-getter",
            args.startup_seconds,
            args.phase_seconds,
            getter_stub,
        ),
        "patched-bridge": run_pty_variant(
            "patched-bridge",
            binary_path,
            session_copy("bridge"),
            fixture_root / "pty-bridge",
            args.startup_seconds,
            args.phase_seconds,
            bridge_stub,
        ),
    }
    stock_ed3 = ed3_by_phase(summaries["stock"])
    no_preload_ed3 = ed3_by_phase(summaries["patched-no-preload"])
    bootstrap_ed3 = ed3_by_phase(summaries["patched-bootstrap-only"])
    fallback_ed3 = ed3_by_phase(summaries["patched-fallback"])
    noncallable_ed3 = ed3_by_phase(summaries["patched-collision-noncallable"])
    throwing_ed3 = ed3_by_phase(summaries["patched-collision-throwing"])
    getter_ed3 = ed3_by_phase(summaries["patched-collision-getter"])
    bridge_ed3 = ed3_by_phase(summaries["patched-bridge"])
    require(
        no_preload_ed3 == stock_ed3,
        f"patched-without-preload changed ED3 behavior: stock={stock_ed3} patched={no_preload_ed3}",
    )
    require(
        bootstrap_ed3 == stock_ed3,
        "bootstrap-only preload changed ED3 behavior: "
        f"stock={stock_ed3} bootstrap={bootstrap_ed3}",
    )
    require(
        fallback_ed3 == stock_ed3,
        f"fallback preload changed ED3 behavior: stock={stock_ed3} fallback={fallback_ed3}",
    )
    require(
        noncallable_ed3 == stock_ed3,
        "non-callable q/c collision changed ED3 behavior: "
        f"stock={stock_ed3} collision={noncallable_ed3}",
    )
    require(
        throwing_ed3 == stock_ed3,
        "throwing q/c collision changed ED3 behavior: "
        f"stock={stock_ed3} collision={throwing_ed3}",
    )
    require(
        getter_ed3 == stock_ed3,
        "throwing q/c getter collision changed ED3 behavior: "
        f"stock={stock_ed3} collision={getter_ed3}",
    )
    for phase in ("expand", "collapse", "resize"):
        require(bridge_ed3[phase] >= 1, f"bridge-on {phase} emitted no destructive ED3")

    fallback_events = [
        json.loads(line) for line in fallback_log.read_text().splitlines() if line
    ]
    bridge_events = [
        json.loads(line) for line in bridge_log.read_text().splitlines() if line
    ]
    require(
        any(event.get("id") == 0 for event in fallback_events),
        "fallback did not query Messages",
    )
    bridge_domains = {
        event.get("id") for event in bridge_events if event.get("event") == "q"
    }
    require(
        {0, 1, 2}.issubset(bridge_domains),
        f"bridge PTY missing renderer domains: {bridge_domains}",
    )

    print("\nPTY assertions passed")
    print(f"  stock ED3: {stock_ed3}")
    print(f"  patched no-preload ED3: {no_preload_ed3}")
    print(f"  patched bootstrap-only ED3: {bootstrap_ed3}")
    print(f"  patched fallback ED3: {fallback_ed3}")
    print(f"  patched non-callable collision ED3: {noncallable_ed3}")
    print(f"  patched throwing collision ED3: {throwing_ed3}")
    print(f"  patched throwing-getter collision ED3: {getter_ed3}")
    print(f"  patched bridge ED3: {bridge_ed3}")
    print(
        f"  bridge queried domains: {sorted(domain for domain in bridge_domains if isinstance(domain, int))}"
    )
    print(f"fixtures and captures: {fixture_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
