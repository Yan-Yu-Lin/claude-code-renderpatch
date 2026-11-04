#!/usr/bin/env python3
"""Deterministic stdio MCP fixture for Claude Code 2.1.318 verification."""

import argparse
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

ENV_NAMES = (
    "BUN_OPTIONS",
    "RP_HOST_ENTRY",
    "CLAUDE_RENDERPATCH_ACTIVE",
    "CLAUDE_RENDERPATCH_MODULE",
    "CLAUDE_RENDERPATCH_USER_MODULE",
    "CLAUDE_RENDERPATCH_TARGET",
    "CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID",
    "CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256",
    "CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION",
    "CLAUDE_PRELOAD_TARGET",
    "CLAUDE_PRELOAD_VERSIONS_DIR",
    "CLAUDE_PRELOAD_BOOTSTRAP",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_CODE_CHILD_SESSION",
)
ENV_MARKER = "RP_MCP_ENV_2_1_318"
SEARCH_MARKER = "RP_MCP_TOOL_SEARCH_2_1_318"
NAP_MARKER = "RP_MCP_NAP_2_1_318"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("basic", "tool-search"), default="basic")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--ballast-tools", type=int, default=64)
    parser.add_argument("--description-bytes", type=int, default=8192)
    return parser.parse_args()


ARGS = parse_args()
SEND_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
CANCELLED = {}


def selected_env():
    return {name: os.environ.get(name, "<unset>") for name in ENV_NAMES}


def log(event, **fields):
    record = {
        "event": event,
        "wallTime": time.time(),
        "monotonic": time.monotonic(),
        **fields,
    }
    with LOG_LOCK:
        ARGS.log.parent.mkdir(parents=True, exist_ok=True)
        with ARGS.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def send(message):
    with SEND_LOCK:
        sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def text_result(request_id, text, *, is_error=False):
    send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                **({"isError": True} if is_error else {}),
            },
        }
    )


def padded_description(prefix):
    target = max(len(prefix), ARGS.description_bytes)
    unit = " deterministic deferred-tool ballast 2.1.318"
    return (prefix + unit * ((target - len(prefix)) // len(unit) + 1))[:target]


def tool_list():
    if ARGS.mode == "tool-search":
        tools = [
            {
                "name": "search_probe",
                "description": padded_description(
                    f"Return exactly {SEARCH_MARKER}. Use this only after loading it through ToolSearch."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"tag": {"type": "string"}},
                    "required": ["tag"],
                    "additionalProperties": False,
                },
            }
        ]
        for index in range(ARGS.ballast_tools):
            tools.append(
                {
                    "name": f"ballast_{index:03d}",
                    "description": padded_description(
                        f"Unused verification ballast tool number {index:03d}. Never call this tool."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "additionalProperties": False,
                    },
                }
            )
        return tools
    return [
        {
            "name": "env_report",
            "description": "Return selected child-process environment variables for host isolation verification.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "nap",
            "description": (
                "Wait for seconds, report progress, optionally send the "
                "claudecode/backgroundNow progress marker, then return a deterministic marker."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "minimum": 0, "maximum": 600},
                    "tag": {"type": "string"},
                    "progress_every_s": {"type": "number", "minimum": 0.05, "maximum": 60},
                    "background_after_s": {"type": "number", "minimum": 0, "maximum": 600},
                },
                "required": ["seconds", "tag"],
                "additionalProperties": False,
            },
        },
    ]


def progress(token, elapsed, total, tag, marker=False):
    params = {
        "progressToken": token,
        "progress": elapsed,
        "total": total,
        "message": f"{NAP_MARKER} {tag} elapsed={elapsed:.3f}",
    }
    if marker:
        params["_meta"] = {"claudecode/backgroundNow": True}
    send({"jsonrpc": "2.0", "method": "notifications/progress", "params": params})
    log("progress", tag=tag, elapsed=elapsed, marker=marker)


def run_nap(request):
    request_id = request["id"]
    params = request.get("params") or {}
    arguments = params.get("arguments") or {}
    seconds = float(arguments["seconds"])
    tag = str(arguments["tag"])
    interval = float(arguments.get("progress_every_s", 0.25))
    background_after = arguments.get("background_after_s")
    background_after = None if background_after is None else float(background_after)
    token = (params.get("_meta") or {}).get("progressToken")
    cancelled = CANCELLED.setdefault(str(request_id), threading.Event())
    started = time.monotonic()
    next_progress = started + interval
    marker_sent = False
    log(
        "nap_start",
        requestId=request_id,
        tag=tag,
        seconds=seconds,
        progressToken=token,
        backgroundAfter=background_after,
    )
    try:
        while True:
            now = time.monotonic()
            elapsed = now - started
            if cancelled.is_set():
                log("nap_cancelled", requestId=request_id, tag=tag, elapsed=elapsed)
                text_result(request_id, f"{NAP_MARKER} CANCELLED {tag}", is_error=True)
                return
            if elapsed >= seconds:
                break
            marker_due = background_after is not None and not marker_sent and elapsed >= background_after
            if token is not None and (now >= next_progress or marker_due):
                progress(token, elapsed, seconds, tag, marker=marker_due)
                marker_sent = marker_sent or marker_due
                next_progress = now + interval
            time.sleep(min(0.05, max(0.001, seconds - elapsed)))
        elapsed = time.monotonic() - started
        log("nap_complete", requestId=request_id, tag=tag, elapsed=elapsed, markerSent=marker_sent)
        text_result(request_id, f"{NAP_MARKER} DONE {tag} after {elapsed:.3f}s")
    except Exception as error:
        log("nap_error", requestId=request_id, tag=tag, error=repr(error), trace=traceback.format_exc())
        text_result(request_id, f"{NAP_MARKER} ERROR {tag}: {error}", is_error=True)
    finally:
        CANCELLED.pop(str(request_id), None)


def handle(request):
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    log("request", method=method, requestId=request_id)
    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "renderpatch-verify-2.1.318", "version": "1.0.0"},
                },
            }
        )
    elif method == "tools/list":
        tools = tool_list()
        log("tools_list", count=len(tools), mode=ARGS.mode)
        send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}})
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        log("tool_call", requestId=request_id, name=name, arguments=arguments)
        if name == "env_report" and ARGS.mode == "basic":
            text_result(request_id, ENV_MARKER + " " + json.dumps(selected_env(), sort_keys=True))
        elif name == "search_probe" and ARGS.mode == "tool-search":
            text_result(request_id, f"{SEARCH_MARKER} {arguments.get('tag', '')}".rstrip())
        elif name == "nap" and ARGS.mode == "basic":
            threading.Thread(target=run_nap, args=(request,), daemon=True).start()
        else:
            text_result(request_id, f"unknown fixture tool: {name}", is_error=True)
    elif method == "notifications/cancelled":
        cancelled_id = str(params.get("requestId"))
        event = CANCELLED.get(cancelled_id)
        if event is not None:
            event.set()
        log("cancel", requestId=cancelled_id, reason=params.get("reason"))
    elif request_id is not None:
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})


log("startup", mode=ARGS.mode, pid=os.getpid(), env=selected_env())
for raw_line in sys.stdin:
    try:
        message = json.loads(raw_line)
        if isinstance(message, dict):
            handle(message)
    except Exception as error:
        log("input_error", error=repr(error), raw=raw_line[:500], trace=traceback.format_exc())
