#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bounded static/runtime smoke for the server-prompt blocking layer."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

CHANNELS = [
    "tengu_heron_brook",
    "tengu_brook_heron",
    "tengu_hushed_lark_text",
    "tengu_flint_harbor_prompt",
    "tengu_toasty_thimble",
    "tengu_gentle_parasol",
    "tengu_kairos_brief_stop_hook_text",
    "tengu_projects_thread_recap_prompt",
    "tengu_cinder_plover",
    "tengu_cinder_wren",
    "tengu_official_plugin_prompt_overrides",
]

FILES = {
    "chunk-0x9x817t.js": ["tengu_heron_brook", "tengu_brook_heron", "tengu_hushed_lark_text", "tengu_flint_harbor_prompt"],
    "chunk-363wfywp.js": ["tengu_toasty_thimble", "tengu_gentle_parasol"],
    "chunk-3xyf3gs0.js": ["tengu_kairos_brief_stop_hook_text"],
    "chunk-52mcbrhk.js": ["tengu_projects_thread_recap_prompt"],
    "chunk-v5d8s1b8.js": ["tengu_cinder_plover", "tengu_cinder_wren"],
    "chunk-2b6sw7z3.js": ["tengu_official_plugin_prompt_overrides"],
}

HELPERS = {
    "tengu_heron_brook": "__rpBlockPrompt0",
    "tengu_brook_heron": "__rpBlockPrompt0",
    "tengu_hushed_lark_text": "__rpBlockPrompt0",
    "tengu_flint_harbor_prompt": "__rpBlockPrompt0",
    "tengu_toasty_thimble": "__rpBlockPrompt1",
    "tengu_gentle_parasol": "__rpBlockPrompt1",
    "tengu_kairos_brief_stop_hook_text": "__rpBlockPrompt2",
    "tengu_projects_thread_recap_prompt": "__rpBlockPrompt3",
    "tengu_cinder_plover": "__rpBlockPrompt4",
    "tengu_cinder_wren": "__rpBlockPrompt4",
    "tengu_official_plugin_prompt_overrides": "__rpBlockPrompt5",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("release", type=Path)
    args = parser.parse_args()
    graph = args.release / "graph"
    helpers = []
    static = {}
    for file_name, channels in FILES.items():
        text = (graph / file_name).read_text()
        match = re.search(r"function (__rpBlockPrompt\d)\(e,n,r\)\{.*?return null\}", text)
        if not match:
            raise SystemExit(f"missing helper in {file_name}")
        helpers.append(match.group(0))
        static[file_name] = {channel: channel in text for channel in channels}
        if not all(static[file_name].values()):
            raise SystemExit(f"missing channel anchor in {file_name}")
    if "block-server-prompt-injection" not in (args.release / "release-manifest.json").read_text():
        raise SystemExit("manifest lacks baked-in patch")
    launcher = (args.release / "claude-renderpatch-candidate").read_text()
    if "-original_games_guidance" not in launcher:
        raise SystemExit("launcher lacks original_games capability override")

    with tempfile.TemporaryDirectory(prefix="bridge-prompt-block-") as td:
        home = Path(td)
        script = home / "smoke.mjs"
        calls = []
        for channel in CHANNELS:
            helper = HELPERS[channel]
            call = f'out.push({helper}({json.dumps(channel)},{json.dumps("FAKE_" + channel)},"claude-o55[1m]"));'
            calls.extend([call, call])
        script.write_text("\n".join(helpers) + "\nlet out=[];\n" + "\n".join(calls) + "\nconsole.log(JSON.stringify(out));\n")
        env = {**os.environ, "HOME": str(home)}
        env.pop("CLAUDE_BRIDGE_ALLOW_SERVER_PROMPTS", None)
        blocked = subprocess.run(["bun", str(script)], env=env, text=True, capture_output=True, timeout=30, check=True)
        blocked_values = json.loads(blocked.stdout)
        if blocked_values != [None] * (len(CHANNELS) * 2):
            raise SystemExit(f"blocked values escaped: {blocked_values}")
        log = home / ".local/state/claude-bridge/blocked-injections.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        if {row["channel"] for row in rows} != set(CHANNELS):
            raise SystemExit("log does not contain every channel")
        if any(not row["text"].startswith("FAKE_") or row["model"] != "claude-o55[1m]" for row in rows):
            raise SystemExit("log lost model or full text")
        if len(rows) != len(CHANNELS):
            raise SystemExit("duplicate text was logged within one process/session")
        allow_env = {**env, "CLAUDE_BRIDGE_ALLOW_SERVER_PROMPTS": "1"}
        allowed = subprocess.run(["bun", str(script)], env=allow_env, text=True, capture_output=True, timeout=30, check=True)
        allowed_values = json.loads(allowed.stdout)
        expected = [value for channel in CHANNELS for value in ["FAKE_" + channel] * 2]
        if allowed_values != expected:
            raise SystemExit("escape hatch did not restore values")
    print(json.dumps({"pass": True, "channels": CHANNELS, "static": static}, indent=2))


if __name__ == "__main__":
    main()
