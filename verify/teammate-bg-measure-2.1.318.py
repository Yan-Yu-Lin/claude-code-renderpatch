#!/usr/bin/env python3
"""Measure owner routing in one Claude project/session directory.

Usage: teammate-bg-measure-2.1.318.py <session-or-project-dir>
Prints task completion enqueue events and the lead/agent conversations that
actually received task-notifications or SubagentHandback messages.
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1])


def files(pattern):
    return sorted(set(glob.glob(os.path.join(ROOT, pattern), recursive=True)))


lead_files = files("*.jsonl")
sub_files = files("subagents/*.jsonl") + files("*/subagents/*.jsonl")


def metadata_path(path):
    return path[:-6] + ".meta.json"


def who(path):
    if "/subagents/" not in path:
        return "LEAD"
    try:
        with open(metadata_path(path)) as handle:
            meta = json.load(handle)
    except (OSError, json.JSONDecodeError):
        meta = {}
    label = meta.get("name") or "helper:" + meta.get("description", "?")
    parent = meta.get("parentAgentId")
    return label + (f" (parent {parent})" if parent else "")


def text_of(record):
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


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


print("## enqueue (task finished) times")
for path in lead_files:
    for record in rows(path):
        if record.get("type") != "queue-operation" or record.get("operation") != "enqueue":
            continue
        content = record.get("content") or ""
        timestamp = record.get("timestamp", "")[11:23]
        if "<task-notification>" in content:
            summary = re.search(r"<summary>(.*?)</summary>", content, re.S)
            print(timestamp, "ENQUEUE", summary.group(1) if summary else "?")
        elif "hand-back" in content:
            sender = re.search(r'from="([^"]+)"', content)
            print(timestamp, "ENQUEUE hand-back", sender.group(1) if sender else "?")

print("\n## who saw task-notifications / hand-backs")
for path in lead_files + sub_files:
    owner = who(path)
    for record in rows(path):
        timestamp = record.get("timestamp", "")[11:23]
        if record.get("type") == "attachment":
            attachment = record.get("attachment") or {}
            if attachment.get("type") != "queued_command":
                continue
            prompt = attachment.get("prompt") or ""
            if "<task-notification>" not in prompt and "hand-back" not in prompt:
                continue
            summary = re.search(r"<summary>(.*?)</summary>", prompt, re.S)
            print(timestamp, owner, "ATTACH", summary.group(1) if summary else "HAND-BACK")
            continue
        if record.get("type") != "user":
            continue
        text = text_of(record)
        if "<task-notification>" in text:
            summary = re.search(r"<summary>(.*?)</summary>", text, re.S)
            print(timestamp, owner, "USER", summary.group(1) if summary else "?")
        elif "Subagent hand-back" in text:
            report = text.split("The report follows:", 1)[-1]
            print(timestamp, owner, "USER HAND-BACK", re.sub(r"\s+", " ", report)[:120])
