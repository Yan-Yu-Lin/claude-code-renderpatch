#!/usr/bin/env python3
"""Deterministic stdio MCP fixture for owner-routing and backgroundNow gates.

Only this fixture's timed calls are affected. Log records bind the wire request,
Claude tool-use ID, progress marker, cancellation, and result to monotonic times.
"""
import argparse
import datetime
import json
import sys
import threading
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--log", type=Path, required=True)
args = parser.parse_args()
args.log.parent.mkdir(parents=True, exist_ok=True)
output_lock = threading.Lock()
state_lock = threading.Lock()
calls = {}


def log(event, **fields):
    row = {"event": event, "monotonic": time.monotonic(),
           "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), **fields}
    with state_lock, args.log.open("a") as stream:
        stream.write(json.dumps(row) + "\n")


def send(message):
    with output_lock:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        sys.stdout.flush()


def run_nap(request, cancelled):
    request_id = request["id"]
    params = request.get("params", {})
    values = params.get("arguments", {})
    seconds = float(values.get("seconds", 10))
    marker_after = float(values.get("marker_after_s", -1))
    tag = str(values.get("tag", ""))
    meta = params.get("_meta", {})
    token = meta.get("progressToken")
    started = time.monotonic()
    marker_sent = False
    log("started", requestId=request_id, toolUseId=meta.get("claudecode/toolUseId"),
        tag=tag, seconds=seconds, markerAfter=marker_after)
    try:
        while True:
            elapsed = time.monotonic() - started
            if cancelled.is_set():
                log("cancelled", requestId=request_id, tag=tag, elapsed=elapsed)
                return
            if marker_after >= 0 and not marker_sent and elapsed >= marker_after:
                marker_sent = True
                if token is not None:
                    send({"method": "notifications/progress", "params": {
                        "progressToken": token, "progress": elapsed, "total": seconds,
                        "message": "fixture requests background now",
                        "_meta": {"claudecode/backgroundNow": True}}})
                    log("marker", requestId=request_id, tag=tag, elapsed=elapsed)
            if elapsed >= seconds:
                text = f"MCP_RESULT_{tag}"
                log("completed", requestId=request_id, tag=tag, elapsed=elapsed, result=text)
                send({"id": request_id, "result": {"content": [{"type": "text", "text": text}]}})
                return
            if token is not None:
                send({"method": "notifications/progress", "params": {
                    "progressToken": token, "progress": elapsed, "total": seconds,
                    "message": "fixture still running"}})
            delay = min(1.0, seconds - elapsed)
            if marker_after >= 0 and not marker_sent:
                delay = min(delay, max(0, marker_after - elapsed))
            cancelled.wait(delay)
    finally:
        with state_lock:
            calls.pop(request_id, None)


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        send({"id": request_id, "result": {
            "protocolVersion": request["params"]["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "bridge-background-fixture", "version": "2.1.318"}}})
    elif method == "tools/list":
        send({"id": request_id, "result": {"tools": [{
            "name": "nap", "description": "Wait seconds, then return MCP_RESULT_<tag>. Optional marker_after_s requests client backgrounding at that time; -1 disables the marker.",
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
            "inputSchema": {"type": "object", "properties": {
                "seconds": {"type": "number", "minimum": 0, "maximum": 120},
                "tag": {"type": "string"},
                "marker_after_s": {"type": "number", "minimum": -1, "maximum": 120}},
                "required": ["seconds", "tag"], "additionalProperties": False}}]}})
    elif method == "tools/call":
        event = threading.Event()
        with state_lock:
            calls[request_id] = event
        threading.Thread(target=run_nap, args=(request, event), daemon=True).start()
    elif method == "notifications/cancelled":
        with state_lock:
            event = calls.get(request.get("params", {}).get("requestId"))
        if event is not None:
            event.set()
    elif request_id is not None:
        send({"id": request_id, "result": {}})
