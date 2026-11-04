#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 2.1.318 upstream-behavior gates required by the port.

Gates:
  tool-search  actual deferred MCP ToolSearch and subsequent tool call through
               the launcher's CLIProxyAPI route, without ENABLE_TOOL_SEARCH
  idle-compact live proxy proof of a 1h cache write plus exact-source targeted
               runtime checks of the 90%-of-cache-life idle compactor
  nested-agent -p/SDK-style nested Agent call defaults to foreground and the
               outer child receives the inner result before returning
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

HOME = Path.home()
SEARCH_MARKER = "RP_MCP_TOOL_SEARCH_2_1_318"


def clean_env(extra=None):
    rejected = {
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_ENTRYPOINT",
        "ENABLE_TOOL_SEARCH",
        "CLAUDE_CODE_FORK_SUBAGENT",
        "CLAUDE_CODE_SLEEP_COMPACT",
        "CLAUDE_CODE_SLEEP_COMPACT_AFTER_MS",
        "CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS",
    }
    env = {key: value for key, value in os.environ.items() if key not in rejected}
    env["TERM"] = "xterm-256color"
    env["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    env["UV_CACHE_DIR"] = "/Volumes/111360128 Lin Yan Yu/DevCache/uv"
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def project_dir(cwd):
    return HOME / ".claude/projects" / str(cwd).replace("/", "-").replace(".", "-")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def trash_path(path):
    if path.exists() or path.is_symlink():
        subprocess.run(["trash", str(path)], check=True)


def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def run(argv, label, out, cwd, *, timeout=500, env=None):
    started = time.time()
    proc = subprocess.run(
        [str(value) for value in argv],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env or clean_env(),
        timeout=timeout,
    )
    record = {
        "label": label,
        "argv": [str(value) for value in argv],
        "returncode": proc.returncode,
        "seconds": round(time.time() - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    write_json(out / f"{label}.json", record)
    return record


def parse_single_json(stdout):
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("stdout contained no JSON")
    return json.loads(lines[-1])


def find_unique_source(graph, anchors):
    matches = []
    for path in graph.glob("*.js"):
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            # Bun also embeds compressed file-loader assets with .js suffixes.
            continue
        if all(anchor in text for anchor in anchors):
            matches.append((path, text))
    if len(matches) != 1:
        raise RuntimeError(f"expected one source matching {anchors!r}, found {[str(path) for path, _ in matches]}")
    return matches[0]


def source_record(path, text, anchors):
    return {
        "path": str(path),
        "sha256": sha256_text(text),
        "anchors": {anchor: text.count(anchor) for anchor in anchors},
    }


def assistant_tool_sequence(stdout):
    sequence = []
    for line_number, line in enumerate(stdout.splitlines(), 1):
        try:
            record = json.loads(line)
        except Exception:
            continue
        if record.get("type") != "assistant":
            continue
        for block in (record.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") in ("tool_use", "server_tool_use", "mcp_tool_use"):
                name = block.get("name") or block.get("tool_name")
                if isinstance(name, str):
                    sequence.append({"line": line_number, "name": name, "id": block.get("id"), "input": block.get("input")})
    return sequence


def gate_tool_search(args, out, sources):
    work = out / "tool-search-project"
    trash_path(work)
    work.mkdir(parents=True)
    server_log = out / "tool-search-server.jsonl"
    trash_path(server_log)
    config = work / "mcp.json"
    write_json(config, {"mcpServers": {"rpverify": {
        "type": "stdio",
        "command": sys.executable,
        "args": [
            str(args.mcp_fixture),
            "--mode", "tool-search",
            "--log", str(server_log),
            "--ballast-tools", "0",
            "--description-bytes", "256",
        ],
    }}})
    prompt = (
        'Use ToolSearch exactly once with query "select:mcp__rpverify__search_probe". '
        'After ToolSearch returns the schema, call mcp__rpverify__search_probe exactly once with '
        f'{{"tag":"actual-proxy-search"}}. Then reply exactly {SEARCH_MARKER}.'
    )
    record = run(
        [args.launcher,
         "--setting-sources", "project,local",
         "--model", "opus",
         "--permission-mode", "default",
         "--mcp-config", config,
         "--strict-mcp-config",
         "--allowedTools", "ToolSearch,mcp__rpverify__search_probe",
         "--output-format", "stream-json",
         "--verbose",
         "-p", prompt],
        "tool-search-proxy",
        out,
        work,
        timeout=700,
        env=clean_env(),
    )
    sequence = assistant_tool_sequence(record["stdout"])
    names = [item["name"] for item in sequence]
    search_positions = [index for index, name in enumerate(names) if name in ("ToolSearch", "tool_search")]
    probe_positions = [index for index, name in enumerate(names) if name == "mcp__rpverify__search_probe"]
    events = read_jsonl(server_log) if server_log.exists() else []
    list_events = [event for event in events if event.get("event") == "tools_list"]
    probe_calls = [event for event in events if event.get("event") == "tool_call" and event.get("name") == "search_probe"]
    mode_source = sources["toolSearchMode"]
    threshold_source = sources["toolSearchThreshold"]
    source_ok = (
        mode_source["text"].count('function xce(){') == 1
        and mode_source["text"].count('return"tst-auto"') >= 1
        and mode_source["text"].count('return"tst"') >= 2
        and threshold_source["text"].count('var Qet=10') == 1
        and threshold_source["text"].count('async function z7r(') == 1
    )
    summary = {
        "source": {
            "mode": source_record(mode_source["path"], mode_source["text"], ("function xce(){", 'return"tst-auto"')),
            "threshold": source_record(threshold_source["path"], threshold_source["text"], ("var Qet=10", "async function z7r(")),
        },
        "environmentOverrides": {name: clean_env().get(name) for name in ("ENABLE_TOOL_SEARCH",)},
        "assistantToolSequence": sequence,
        "toolsListCounts": [event.get("count") for event in list_events],
        "probeCalls": len(probe_calls),
        "markerInOutput": SEARCH_MARKER in record["stdout"],
        "returncode": record["returncode"],
    }
    summary["pass"] = (
        source_ok
        and "ENABLE_TOOL_SEARCH" not in clean_env()
        and record["returncode"] == 0
        and len(search_positions) == 1
        and len(probe_positions) == 1
        and search_positions[0] < probe_positions[0]
        and len(probe_calls) == 1
        and bool(list_events)
        and max(event.get("count", 0) for event in list_events) == 1
        and SEARCH_MARKER in record["stdout"]
    )
    write_json(out / "tool-search-summary.json", summary)
    return summary


def idle_runtime_script(fragment):
    prelude = r'''
const events = [];
let timer = null;
let compactCalls = 0;
let summarizeCalls = 0;
let summaryValue = null;
let state = {
  now: 1000,
  hostEligible: true,
  autoCompact: true,
  idleCompact: true,
  precompute: true,
  swap: true,
  ttlMs: 3600000,
  lastRequestAt: 500,
  tokens: 220000,
  allowed: true,
  expiresAt: 3600000,
  cache: {warm: true, lastRequest: {ttl: "1h"}, lastActivityAt: 0, expiresAt: 3600000},
};
const i = {CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS: undefined};
const POr = "";
const Fu = () => state.autoCompact;
const gOt = () => state.idleCompact;
const roo = () => state.precompute;
const e$ = () => state.swap;
const $7 = () => state.ttlMs;
const cx = 3600000;
const sde = () => state.cache;
const O2 = () => state.lastRequestAt;
const Hi = () => ({status: state.allowed ? "allowed" : "blocked"});
const xTe = () => state.expiresAt;
const mVe = () => state.tokens;
const WB = () => state.hostEligible;
const We = () => false;
const l = (event, fields) => events.push({kind: "telemetry", event, fields});
const p = (value) => value;
const g = (event, fields) => events.push({kind: "success", event, fields});
const c = (event, fields) => events.push({kind: "cancel", event, fields});
const m = (event, fields) => events.push({kind: "failure", event, fields});
const a = (error) => events.push({kind: "error", error: String(error)});
const realSetImmediate = globalThis.setImmediate;
Date.now = () => state.now;
globalThis.setTimeout = (fn, delay, ...args) => {
  timer = {fn, delay, args, unref() {}};
  return timer;
};
globalThis.clearTimeout = (handle) => {
  if (timer === handle) timer = null;
};
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
async function settle() {
  await Promise.resolve();
  await new Promise((resolve) => realSetImmediate(resolve));
  await new Promise((resolve) => realSetImmediate(resolve));
}
'''
    tests = r'''
async function fireScheduled() {
  const scheduled = timer;
  assert(scheduled !== null, "expected an armed timer");
  timer = null;
  state.now = 3240000;
  scheduled.fn(...scheduled.args);
  await settle();
  return scheduled.delay;
}

const hostCompactor = new grn();
hostCompactor.host = {
  refusal: async () => "started",
  compact: async () => {
    compactCalls += 1;
    return {tokensBefore: state.tokens, tokensAfter: 50000};
  },
};
hostCompactor.arm(900, () => ({kind: "precomputed-summary"}));
await settle();
assert(timer !== null, "1h warm cache did not arm");
assert(timer.delay === 3239000, `unexpected 90% timer delay: ${timer.delay}`);
const armedDelayMs = await fireScheduled();
assert(compactCalls === 1, `host compact called ${compactCalls} times`);

state.now = 1000;
state.ttlMs = 300000;
state.cache = {warm: true, lastRequest: {ttl: "5m"}, lastActivityAt: 0, expiresAt: 300000};
timer = null;
const fiveMinute = new grn();
fiveMinute.host = hostCompactor.host;
fiveMinute.arm(900, () => ({kind: "summary"}));
await settle();
assert(timer === null, "5m cache incorrectly armed idle compaction");

state.now = 1000;
state.ttlMs = 3600000;
state.cache = {warm: true, lastRequest: {ttl: "1h"}, lastActivityAt: 0, expiresAt: 3600000};
state.idleCompact = false;
timer = null;
compactCalls = 0;
const disabled = new grn();
disabled.host = hostCompactor.host;
disabled.arm(900, () => ({kind: "summary"}));
await settle();
await fireScheduled();
assert(compactCalls === 0, "idleCompaction=false still compacted");
assert(events.some((event) => event.event === "tengu_idle_compact_fired" && event.fields?.outcome === "idle_compaction_off"), "disabled outcome not reported");

state.now = 1000;
state.idleCompact = true;
timer = null;
const summarized = new grn();
summarized.summarize = async (value) => {
  summarizeCalls += 1;
  summaryValue = value;
  return {tokensBefore: state.tokens, tokensAfter: 45000};
};
summarized.arm(900, () => ({kind: "precomputed-summary", text: "summary-only"}));
await settle();
await fireScheduled();
assert(summarizeCalls === 1, `summary path called ${summarizeCalls} times`);
assert(summaryValue?.kind === "precomputed-summary", "summary path did not receive the prepared summary");

console.log(JSON.stringify({
  armedDelayMs,
  compactCallsAfterDisabledCase: compactCalls,
  summarizeCalls,
  summaryValue,
  events,
}));
'''
    return prelude + "\n" + fragment + "\n" + tests


def run_idle_targeted_runtime(source, out, cwd):
    text = source["text"]
    start = text.index("var u4o=200000")
    end = text.index("var f3t=", start)
    fragment = text[start:end]
    script = idle_runtime_script(fragment)
    started = time.time()
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=clean_env(),
        timeout=60,
    )
    try:
        payload = parse_single_json(proc.stdout)
    except Exception:
        payload = None
    record = {
        "argv": ["node", "--input-type=module", "-e", "<exact extracted idle-compactor fragment plus deterministic fake-clock harness>"],
        "returncode": proc.returncode,
        "seconds": round(time.time() - started, 3),
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-6000:],
        "sourceFragmentSha256": sha256_text(fragment),
        "sourceFragmentBytes": len(fragment.encode()),
        "payload": payload,
    }
    write_json(out / "idle-compaction-targeted-runtime.json", record)
    return record


def gate_idle_compact(args, out, sources):
    marker = "IDLE_COMPACTION_PROXY_318_OK"
    live = run(
        [args.launcher,
         "--setting-sources", "project,local",
         "--model", "opus",
         "--permission-mode", "default",
         "--strict-mcp-config",
         "--tools", "",
         "--output-format", "json",
         "-p", f"Reply exactly {marker}."],
        "idle-compaction-proxy-cache",
        out,
        args.cwd,
        timeout=500,
        env=clean_env(),
    )
    try:
        payload = parse_single_json(live["stdout"])
    except Exception:
        payload = {}
    cache_creation = ((payload.get("usage") or {}).get("cache_creation") or {})
    idle_source = sources["idleCompaction"]
    source_text = idle_source["text"]
    source_ok = all(
        source_text.count(anchor) == 1
        for anchor in (
            "var u4o=200000,c4o=1e5,f4o=0.9,p4o=60000",
            'if($7()!==cx)return"not_one_hour"',
            'if(!sde().warm||n>p4o)return"lapsed"',
            'if(r<mrn())return"small"',
            'if(Hi().status!=="allowed")return"near_limit"',
            "class grn{",
        )
    )
    targeted = run_idle_targeted_runtime(idle_source, out, args.cwd)
    targeted_payload = targeted.get("payload") or {}
    summary = {
        "source": source_record(
            idle_source["path"],
            source_text,
            (
                "var u4o=200000,c4o=1e5,f4o=0.9,p4o=60000",
                'if($7()!==cx)return"not_one_hour"',
                "class grn{",
            ),
        ),
        "proxy": {
            "returncode": live["returncode"],
            "result": payload.get("result"),
            "cacheCreation": cache_creation,
            "modelUsage": sorted((payload.get("modelUsage") or {}).keys()),
        },
        "targetedRuntime": targeted,
    }
    summary["pass"] = (
        source_ok
        and live["returncode"] == 0
        and payload.get("result", "").strip() == marker
        and cache_creation.get("ephemeral_1h_input_tokens", 0) > 0
        and cache_creation.get("ephemeral_5m_input_tokens", 0) == 0
        and targeted["returncode"] == 0
        and targeted_payload.get("armedDelayMs") == 3239000
        and targeted_payload.get("summarizeCalls") == 1
        and (targeted_payload.get("summaryValue") or {}).get("kind") == "precomputed-summary"
    )
    write_json(out / "idle-compaction-summary.json", summary)
    return summary


def tool_result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return json.dumps(content, sort_keys=True)


def nested_foreground_evidence(transcripts, inner_marker):
    matches = []
    for path in transcripts:
        records = read_jsonl(path)
        uses = {}
        results = {}
        for record in records:
            message = record.get("message") or {}
            content = message.get("content")
            if not isinstance(content, list):
                continue
            if record.get("type") == "assistant":
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Agent":
                        uses[block.get("id")] = block
            if record.get("type") == "user":
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        results[block.get("tool_use_id")] = tool_result_text(block)
        for tool_use_id, block in uses.items():
            input_value = block.get("input") or {}
            if inner_marker not in json.dumps(input_value, sort_keys=True):
                continue
            result = results.get(tool_use_id)
            matches.append({
                "transcript": str(path),
                "toolUseId": tool_use_id,
                "input": input_value,
                "result": result,
                "runInBackgroundPresent": "run_in_background" in input_value,
                "innerMarkerInResult": result is not None and inner_marker in result,
                "spawnedTextInResult": result is not None and bool(re.search(r"spawned successfully|running in the background|task id", result, re.I)),
            })
    return matches


def gate_nested_agent(args, out, sources):
    session_id = str(uuid.uuid4())
    inner = "NESTED_318_INNER_OK"
    outer = "NESTED_318_OUTER_OK"
    parent = "NESTED_318_PARENT_OK"
    prompt = (
        'Call Agent exactly once with subagent_type="general-purpose", description="outer nested foreground gate", '
        'prompt="Call Agent exactly once with subagent_type=\\"general-purpose\\", '
        'description=\\"inner nested foreground gate\\", '
        f'prompt=\\"Reply exactly {inner}. Do not use tools.\\". Do not set run_in_background. '
        f'Wait for the inner Agent result, verify it contains {inner}, then reply exactly {outer}." '
        f"Do not set run_in_background. Wait for the outer Agent result, verify it contains {outer}, then reply exactly {parent}."
    )
    record = run(
        [args.launcher,
         "--setting-sources", "project,local",
         "--session-id", session_id,
         "--model", "haiku",
         "--permission-mode", "default",
         "--tools", "Agent",
         "--allowedTools", "Agent",
         "--strict-mcp-config",
         "--output-format", "stream-json",
         "--verbose",
         "-p", prompt],
        "nested-agent-print-sdk",
        out,
        args.cwd,
        timeout=900,
        env=clean_env(),
    )
    transcript_root = project_dir(args.cwd) / session_id / "subagents"
    transcripts = sorted(transcript_root.rglob("agent-*.jsonl")) if transcript_root.exists() else []
    evidence = nested_foreground_evidence(transcripts, inner)
    source = sources["nestedAgent"]
    source_ok = (
        source["text"].count('var jpr="tengu_fork_subagent_enabled"') == 1
        and source["text"].count('let n=i.CLAUDE_CODE_FORK_SUBAGENT===!0?"env":"default"') == 1
        and source["text"].count('function DAt(){if(!Nhe())return!1;return jfn()==="env"||!RR()}') == 1
    )
    matched = evidence[0] if len(evidence) == 1 else None
    summary = {
        "source": source_record(
            source["path"],
            source["text"],
            (
                'var jpr="tengu_fork_subagent_enabled"',
                'let n=i.CLAUDE_CODE_FORK_SUBAGENT===!0?"env":"default"',
                'function DAt(){if(!Nhe())return!1;return jfn()==="env"||!RR()}',
            ),
        ),
        "sessionId": session_id,
        "transcripts": [str(path) for path in transcripts],
        "foregroundEvidence": evidence,
        "returncode": record["returncode"],
        "parentMarkerInOutput": parent in record["stdout"],
        "outerMarkerInOutput": outer in record["stdout"],
    }
    summary["pass"] = (
        source_ok
        and "CLAUDE_CODE_FORK_SUBAGENT" not in clean_env()
        and record["returncode"] == 0
        and len(transcripts) >= 2
        and len(evidence) == 1
        and matched is not None
        and not matched["runInBackgroundPresent"]
        and matched["innerMarkerInResult"]
        and not matched["spawnedTextInResult"]
        and outer in record["stdout"]
        and parent in record["stdout"]
    )
    write_json(out / "nested-agent-summary.json", summary)
    return summary


def discover_sources(graph):
    tool_mode_path, tool_mode_text = find_unique_source(graph, ("function xce(){", 'return"tst-auto"'))
    tool_threshold_path, tool_threshold_text = find_unique_source(graph, ("var Qet=10", "async function z7r("))
    idle_path, idle_text = find_unique_source(
        graph,
        (
            "var u4o=200000,c4o=1e5,f4o=0.9,p4o=60000",
            'if($7()!==cx)return"not_one_hour"',
            "class grn{",
        ),
    )
    nested_path, nested_text = find_unique_source(
        graph,
        (
            'var jpr="tengu_fork_subagent_enabled"',
            'let n=i.CLAUDE_CODE_FORK_SUBAGENT===!0?"env":"default"',
            'function DAt(){if(!Nhe())return!1;return jfn()==="env"||!RR()}',
        ),
    )
    return {
        "toolSearchMode": {"path": tool_mode_path, "text": tool_mode_text},
        "toolSearchThreshold": {"path": tool_threshold_path, "text": tool_threshold_text},
        "idleCompaction": {"path": idle_path, "text": idle_text},
        "nestedAgent": {"path": nested_path, "text": nested_text},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("launcher", type=Path)
    parser.add_argument("--graph", type=Path, help="Patched release graph; defaults to launcher sibling graph/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, default=Path("/tmp/rp-new-version-gates-2.1.318"))
    parser.add_argument("--only", action="append", choices=("tool-search", "idle-compact", "nested-agent"))
    args = parser.parse_args()
    args.launcher = args.launcher.resolve()
    args.graph = (args.graph or args.launcher.parent / "graph").resolve()
    args.repo = Path(__file__).resolve().parents[1]
    args.mcp_fixture = args.repo / "verify/fixtures/mcp-2.1.318.py"
    args.cwd.mkdir(parents=True, exist_ok=True)
    args.cwd = args.cwd.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sources = discover_sources(args.graph)
    gates = {
        "tool-search": gate_tool_search,
        "idle-compact": gate_idle_compact,
        "nested-agent": gate_nested_agent,
    }
    passed = {}
    for name in args.only or gates:
        result = gates[name](args, out, sources)
        passed[name] = result.get("pass") is True
        print(name, json.dumps(result, sort_keys=True)[:2000], flush=True)
    write_json(out / "new-version-gates-summary.json", passed)
    print(json.dumps(passed, sort_keys=True))
    if not all(passed.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
