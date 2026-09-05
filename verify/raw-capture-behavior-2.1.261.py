#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Live-smoke the six raw capture domains with a metadata-only trusted stub."""

from __future__ import annotations

import argparse
import json
import os
import pty
import select
import signal
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION = "2.1.261"
OUTPUT_NAME = "claude-2.1.261-semantic-bridge"
DEFAULT_BINARY = REPO / "patched" / OUTPUT_NAME
FIXTURE_PARENT = REPO / "patched" / "raw-capture-fixtures"
EXPECTED = {
    0: (0, 4194303, 22),
    1: (0, 3194879, 22),
    2: (None, 63, 6),
    3: (None, 65535, 16),
    4: (None, 65535, 16),
    5: (None, 511, 9),
}
EXPECTED_STATIC_DEFINED = {0: 22, 1: 17}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument(
        "--bootstrap", type=Path, help="Defaults to bootstrap.mjs beside the entry"
    )
    parser.add_argument("--startup-seconds", type=float, default=5.0)
    parser.add_argument("--shutdown-seconds", type=float, default=4.0)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_stub(path: Path) -> None:
    path.write_text(
        "import {appendFileSync} from 'node:fs';\n"
        "const log=process.env.RAW_CAPTURE_LOG;\n"
        "const current=new Map;\n"
        "const record=event=>appendFileSync(log,JSON.stringify(event)+'\\n');\n"
        "const facade=Object.freeze({\n"
        "q(_id,fallback){return fallback},\n"
        "c(id,generation,bitmap,slots){\n"
        "if(!Number.isInteger(id)||id<0||id>5)return;\n"
        "if(!Number.isSafeInteger(generation)||generation<0)return;\n"
        "if(!Number.isSafeInteger(bitmap)||bitmap<0)return;\n"
        "if(slots===null){if(bitmap!==0)return;const prior=current.get(id);"
        "const matched=prior?.generation===generation;if(matched)current.delete(id);"
        "record({event:'clear',id,generation,bitmap,matched});return}\n"
        "if(!Array.isArray(slots))return;const prior=current.get(id);"
        "if(prior&&generation<prior.generation)return;"
        "const definedCount=slots.reduce((count,value)=>count+(value!==void 0),0);"
        "current.set(id,{generation,bitmap,slotCount:slots.length});"
        "record({event:prior?'replace':'publish',id,generation,bitmap,slotCount:slots.length,definedCount})}\n"
        "});\n"
        "Object.defineProperty(globalThis,'__rp',{value:facade,enumerable:false,writable:false,configurable:false});\n"
        "record({event:'loaded'});\n",
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


def drain(master: int, process: subprocess.Popen[bytes], seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and process.poll() is None:
        ready, _, _ = select.select([master], [], [], 0.1)
        if not ready:
            continue
        try:
            if not os.read(master, 65536):
                return
        except OSError:
            return


def run_candidate(
    binary: Path,
    preload: Path | None,
    log_path: Path | None,
    startup: float,
    shutdown: float,
) -> int:
    env = os.environ.copy()
    env.pop("BUN_OPTIONS", None)
    env.pop("RAW_CAPTURE_LOG", None)
    if preload is not None:
        env["BUN_OPTIONS"] = f"--preload={preload}"
    if log_path is not None:
        env["RAW_CAPTURE_LOG"] = str(log_path)
    env.setdefault("TERM", "xterm-256color")

    master, slave = pty.openpty()
    process = subprocess.Popen(
        [str(binary)],
        cwd=Path.home(),
        env=env,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    try:
        drain(master, process, startup)
        if process.poll() is None:
            os.write(master, b"\x03\x03")
            drain(master, process, shutdown)
        if process.poll() is None:
            try:
                process.send_signal(signal.SIGKILL)
            except ProcessLookupError:
                pass
        return process.wait(timeout=5)
    finally:
        os.close(master)


def validate_events(events: list[dict[str, object]]) -> None:
    require(
        events and events[0] == {"event": "loaded"}, "trusted stub did not load first"
    )
    publications = [
        event for event in events if event.get("event") in {"publish", "replace"}
    ]
    clears = [event for event in events if event.get("event") == "clear"]

    by_domain: dict[int, list[dict[str, object]]] = {domain: [] for domain in EXPECTED}
    for event in publications:
        domain = event.get("id")
        if isinstance(domain, int) and domain in by_domain:
            by_domain[domain].append(event)

    require(
        all(by_domain.values()),
        f"live startup missed capture domains: {[d for d, items in by_domain.items() if not items]}",
    )
    for domain, (static_generation, bitmap, slot_count) in EXPECTED.items():
        first = by_domain[domain][0]
        require(first.get("bitmap") == bitmap, f"d{domain} live bitmap mismatch")
        require(
            first.get("slotCount") == slot_count, f"d{domain} live slot count mismatch"
        )
        generation = first.get("generation")
        if static_generation is not None:
            require(
                generation == static_generation, f"d{domain} static generation changed"
            )
            require(
                first.get("definedCount") == EXPECTED_STATIC_DEFINED[domain],
                f"d{domain} static publication has unexpected defined slots",
            )
        else:
            require(
                isinstance(generation, int) and generation > 0,
                f"d{domain} dynamic generation is invalid",
            )

        generations = [event["generation"] for event in by_domain[domain]]
        require(
            generations == sorted(set(generations)),
            f"d{domain} live generations are not strictly increasing: {generations}",
        )

    require(
        len(by_domain[0]) == 1 and len(by_domain[1]) == 1,
        "static captures published more than once",
    )
    require(
        any(len(by_domain[domain]) > 1 for domain in (3, 4)),
        "render captures did not replace on rerender",
    )

    latest_seen: dict[int, int] = {}
    stale_safe = False
    for event in events:
        domain = event.get("id")
        generation = event.get("generation")
        if not isinstance(domain, int) or not isinstance(generation, int):
            continue
        if event.get("event") in {"publish", "replace"}:
            latest_seen[domain] = generation
        elif event.get("event") == "clear" and event.get("matched") is False:
            require(
                latest_seen.get(domain, -1) > generation,
                f"d{domain} rejected clear was not stale",
            )
            stale_safe = True
    require(stale_safe, "live render did not exercise a stale generation-safe clear")
    require(
        all(event.get("bitmap") == 0 for event in clears),
        "a live clear used a nonzero bitmap",
    )


def run_stub_contract_test(fixture_root: Path, stub: Path) -> None:
    script = fixture_root / "stub-contract.mjs"
    script.write_text(
        "import assert from 'node:assert/strict';\n"
        f"await import({json.dumps(str(stub))});\n"
        "const c=globalThis.__rp.c;\n"
        "c(3,101,65535,new Array(16));\n"
        "c(3,102,65535,new Array(16));\n"
        "c(3,101,0,null);\n"
        "c(3,102,0,null);\n"
        "c(3,103,1,null);\n"
        "assert.equal(globalThis.__rp.q(9,false),false);\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["RAW_CAPTURE_LOG"] = str(fixture_root / "contract.jsonl")
    subprocess.run(["bun", str(script)], check=True, env=env, capture_output=True)
    contract_events = [
        json.loads(line)
        for line in (fixture_root / "contract.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    require(
        contract_events[-2]["matched"] is False,
        "stale contract clear removed a newer capture",
    )
    require(
        contract_events[-1]["matched"] is True,
        "matching contract clear did not remove its capture",
    )


def main() -> int:
    args = parse_args()
    binary = args.binary.expanduser().resolve()
    require(binary.is_file(), f"candidate not found: {binary}")

    fixture_root = FIXTURE_PARENT / f"run-{int(time.time())}-{os.getpid()}"
    fixture_root.mkdir(parents=True, exist_ok=False)
    log_path = fixture_root / "events.jsonl"
    stub = fixture_root / "capture-stub.mjs"
    noncallable_stub = fixture_root / "collision-noncallable.mjs"
    throwing_stub = fixture_root / "collision-throwing.mjs"
    getter_stub = fixture_root / "collision-getter.mjs"
    write_stub(stub)
    write_collision_stub(noncallable_stub, "noncallable")
    write_collision_stub(throwing_stub, "throwing")
    write_collision_stub(getter_stub, "getter")
    run_stub_contract_test(fixture_root, stub)

    stock_safe_startup = min(args.startup_seconds, 2.5)
    stock_safe_shutdown = min(args.shutdown_seconds, 2.0)
    no_preload_exit = run_candidate(
        binary, None, None, stock_safe_startup, stock_safe_shutdown
    )
    bootstrap_exit = run_candidate(
        binary,
        args.bootstrap or binary.parent / "bootstrap.mjs",
        None,
        stock_safe_startup,
        stock_safe_shutdown,
    )
    noncallable_exit = run_candidate(
        binary, noncallable_stub, None, stock_safe_startup, stock_safe_shutdown
    )
    throwing_exit = run_candidate(
        binary, throwing_stub, None, stock_safe_startup, stock_safe_shutdown
    )
    getter_exit = run_candidate(
        binary, getter_stub, None, stock_safe_startup, stock_safe_shutdown
    )
    clean_exits = {0, 130}
    require(
        no_preload_exit in clean_exits,
        f"patched no-preload PTY exited {no_preload_exit}",
    )
    require(
        bootstrap_exit in clean_exits, f"bootstrap-only PTY exited {bootstrap_exit}"
    )
    require(
        noncallable_exit in clean_exits,
        f"non-callable q/c collision escaped into Claude Code: {noncallable_exit}",
    )
    require(
        throwing_exit in clean_exits,
        f"throwing q/c collision escaped into Claude Code: {throwing_exit}",
    )
    require(
        getter_exit in clean_exits,
        f"throwing q/c getter collision escaped into Claude Code: {getter_exit}",
    )

    exit_code = run_candidate(
        binary,
        stub,
        log_path,
        args.startup_seconds,
        args.shutdown_seconds,
    )
    events = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    validate_events(events)

    publications = [
        event for event in events if event.get("event") in {"publish", "replace"}
    ]
    clears = [event for event in events if event.get("event") == "clear"]
    print(f"patched no-preload PTY exit code: {no_preload_exit}")
    print(f"bootstrap-only PTY exit code: {bootstrap_exit}")
    print(f"non-callable q/c collision PTY exit code: {noncallable_exit}")
    print(f"throwing q/c collision PTY exit code: {throwing_exit}")
    print(f"throwing q/c getter collision PTY exit code: {getter_exit}")
    print(f"trusted-stub PTY exit code: {exit_code} (forced shutdown is allowed)")
    print(f"capture publications/replacements: {len(publications)}")
    print(f"generation-safe clears observed: {len(clears)}")
    print("live domains: d0,d1,d2,d3,d4,d5")
    print(
        "logged fields: event, domain, generation, bitmap, slot/defined counts, clear match only"
    )
    print(f"fixtures: {fixture_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
