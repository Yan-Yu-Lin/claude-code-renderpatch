#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the immutable Claude Code 2.1.281 Darwin host bridge.

Release layout (all hash-pinned by release-manifest.json):
  runtime/claude                 verbatim official executable (Anthropic-signed)
  graph/                         its extracted module graph with baked-in edits
  host.mjs                       trusted --preload host loader
  helpers/{verify-assets,trust-file}.py
  claude-renderpatch-candidate   generated launcher
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

from host_patches_2_1_281 import patch_graph

REPO = Path(__file__).resolve().parents[1]
VERSION = "2.1.281"
BUILD = "host-2.1.281-darwin-arm64.1"
TEAM_ID = "Q6L2SF6YDW"
FILE_SIZE = 220931760
NATIVE_MODULES = {"audio-capture.node", "computer-use-input.node", "computer-use-swift.node"}
spec = importlib.util.spec_from_file_location(
    "extract_darwin", REPO / "tools/extract-source-darwin-2.1.281.py"
)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)
STOCK_SHA = extractor.STOCK_SHA


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def team_id(path):
    info = subprocess.run(
        ["codesign", "-dv", str(path)], capture_output=True, text=True
    ).stderr
    match = re.search(r"^TeamIdentifier=(\S+)$", info, re.M)
    return match[1] if match else None


def build(stock, output):
    if output.exists():
        raise ValueError("refusing to overwrite an existing release")
    if sha(stock) != STOCK_SHA or stock.stat().st_size != FILE_SIZE:
        raise ValueError("official 2.1.281 executable SHA-256/size mismatch")
    subprocess.run(["codesign", "--verify", "--strict", str(stock)], check=True)
    if team_id(stock) != TEAM_ID:
        raise ValueError("official executable is not signed by Anthropic")
    modules = extractor.records(stock.read_bytes())
    natives = {r["name"][len(extractor.ROOT) :] for r in modules if r["name"].endswith(".node")}
    if natives != NATIVE_MODULES:
        raise ValueError(f"unexpected native modules: {sorted(natives)}")

    output.mkdir(parents=True)
    graph = output / "graph"
    paths = {r["name"]: graph / r["name"][len(extractor.ROOT) :] for r in modules}
    texts = {}
    for row in modules:
        if row["loader"] != 1:
            continue
        text = re.sub(r"^(?:// *@bun[^\n]*\n)+", "", row["content"].decode())
        text = re.sub(
            r"/\$bunfs/root/[A-Za-z0-9/._$@+\-]+",
            lambda m: str(paths.get(m[0], m[0])),
            text,
        )
        texts[row["name"][len(extractor.ROOT) :]] = text
    patched, changes = patch_graph(texts)
    for row in modules:
        path = paths[row["name"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        rel = row["name"][len(extractor.ROOT) :]
        path.write_bytes(patched[rel].encode() if row["loader"] == 1 else row["content"])

    (output / "runtime").mkdir()
    shutil.copy2(stock, output / "runtime/claude")
    shutil.copy2(REPO / "preload/host-2.1.281.mjs", output / "host.mjs")
    (output / "helpers").mkdir()
    trust = (REPO / "candidate/trust-file.py").read_text()
    (output / "helpers/trust-file.py").write_text(
        "# /// script\n# dependencies = []\n# ///\n" + trust
    )
    shutil.copy2(REPO / "candidate/verify-source-assets.py", output / "helpers/verify-assets.py")

    executables = {"runtime/claude"}
    assets = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            rel = path.relative_to(output).as_posix()
            assets[rel] = {"sha256": sha(path), "mode": 0o555 if rel in executables else 0o444}
    identity = {
        "schemaVersion": 2,
        "architecture": "official-executable-host",
        "targetVersion": VERSION,
        "platform": "darwin-arm64",
        "bridgeBuildId": BUILD,
        "stockSha256": STOCK_SHA,
        "stockTeamId": TEAM_ID,
        "moduleCount": len(modules),
        "semanticEdits": changes,
        "bakedIn": ["full-redraw", "explicit-subagent-model-routing"],
        "hostLoaderSha256": assets["host.mjs"]["sha256"],
        "assets": assets,
    }
    identity["releaseId"] = f"{VERSION}-host-darwin-arm64-{identity['hostLoaderSha256'][:4]}{sha(output / 'graph/cli')[:4]}"
    (output / "release-manifest.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    manifest_sha = sha(output / "release-manifest.json")
    constants = {
        "RELEASE_ID": identity["releaseId"],
        "TARGET_VERSION": VERSION,
        "BRIDGE_BUILD_ID": BUILD,
        "TARGET_SHA256": STOCK_SHA,
        "TARGET_TEAM_ID": TEAM_ID,
        "RELEASE_MANIFEST_SHA256": manifest_sha,
        "VERIFY_HELPER_SHA256": assets["helpers/verify-assets.py"]["sha256"],
    }
    lines = (
        "\n".join(k + "=" + json.dumps(v) for k, v in constants.items())
        + '\nMARKER_CONTENT="$RELEASE_ID $RELEASE_MANIFEST_SHA256"\n'
    )
    launcher = (REPO / "candidate/host-launcher-2.1.281.in").read_text().replace(
        "@@RELEASE_CONSTANTS@@", lines
    )
    (output / "claude-renderpatch-candidate").write_text(launcher)
    (output / ".claude-renderpatch-release").write_text(f"{identity['releaseId']} {manifest_sha}\n")
    for path in sorted(output.rglob("*"), reverse=True):
        rel = path.relative_to(output).as_posix()
        if path.is_dir():
            path.chmod(0o555)
        else:
            path.chmod(0o555 if rel in executables | {"claude-renderpatch-candidate"} else 0o444)
    output.chmod(0o555)
    print(json.dumps({k: v for k, v in identity.items() if k != "assets"}, indent=2))
    print(f"manifest_sha256={manifest_sha}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stock", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    build(a.stock.resolve(), a.output.resolve())
