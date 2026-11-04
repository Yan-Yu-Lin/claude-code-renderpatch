#!/usr/bin/env python3
"""Print a compact lead + teammate + helper timeline for 2.1.318 gates.

Usage: teammate-bg-timeline-2.1.318.py <session-or-project-dir>
"""

import glob
import json
import os
import sys

ROOT = os.path.abspath(sys.argv[1])


def files(pattern):
    return sorted(set(glob.glob(os.path.join(ROOT, pattern), recursive=True)))


def identity(path):
    if "/subagents/" not in path:
        return "LEAD"
    meta_path = path[:-6] + ".meta.json"
    try:
        with open(meta_path) as handle:
            meta = json.load(handle)
    except (OSError, json.JSONDecodeError):
        meta = {}
    return meta.get("name") or meta.get("description") or os.path.basename(path)[6:-6]


def rows(path):
    try:
        with open(path) as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass
    except OSError:
        return


paths = files("*.jsonl") + files("subagents/*.jsonl") + files("*/subagents/*.jsonl")
timeline = []
for path in paths:
    who = identity(path)
    for record in rows(path):
        timestamp = record.get("timestamp", "")[11:23]
        kind = record.get("type")
        if kind == "queue-operation":
            content = record.get("content") or ""
            if "task-notification" in content:
                start = content.find("<summary>")
                end = content.find("</summary>", start)
                summary = content[start + 9 : end] if start >= 0 and end >= 0 else content[:100]
                timeline.append((timestamp, who, f"QUEUE {record.get('operation')}: {summary[:120]}"))
            continue
        if kind == "attachment":
            attachment = record.get("attachment") or {}
            if attachment.get("type") == "queued_command":
                prompt = attachment.get("prompt") or ""
                start = prompt.find("<summary>")
                end = prompt.find("</summary>", start)
                summary = prompt[start + 9 : end] if start >= 0 and end >= 0 else prompt[:100]
                timeline.append((timestamp, who, f"GOT queued_command: {summary[:120]}"))
            continue
        content = (record.get("message") or {}).get("content")
        if isinstance(content, str):
            if "task-notification" in content or "teammate-message" in content or "Another Claude" in content:
                timeline.append((timestamp, who, "USER: " + " ".join(content.split())[:150]))
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool = block.get("name")
                value = block.get("input") or {}
                if tool == "SendMessage":
                    timeline.append((timestamp, who, f"SendMessage -> {value.get('to')}: {str(value.get('message'))[:100]}"))
                elif tool == "Agent":
                    timeline.append((timestamp, who, f"Agent bg={value.get('run_in_background')} desc={value.get('description')}"))
                elif tool == "Bash" and value.get("run_in_background"):
                    timeline.append((timestamp, who, f"Bash BG desc={value.get('description')}"))
                elif tool == "TaskStop":
                    timeline.append((timestamp, who, f"TaskStop {value.get('task_id')}"))
            elif block.get("type") == "tool_result":
                value = block.get("content")
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                if "Async agent launched" in text or "running in background" in text:
                    timeline.append((timestamp, who, "  -> background launch returned"))
            elif block.get("type") == "text" and kind == "user":
                text = block.get("text", "")
                if "task-notification" in text or "teammate-message" in text:
                    timeline.append((timestamp, who, "USER: " + " ".join(text.split())[:150]))

for row in sorted(timeline):
    print(*row)
