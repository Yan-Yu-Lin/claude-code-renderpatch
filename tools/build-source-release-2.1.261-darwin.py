#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build a separate, exact-version Claude Code Darwin source-graph bridge."""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

from source_patches_2_1_261 import patch_graph

REPO = Path(__file__).resolve().parents[1]
VERSION = "2.1.261"
BUILD = "internal-sdk-2.1.261-darwin-arm64.4"
BUN_SHA = "4c6a735e82bd9da8403f0ece106730ebe431f50a246826197bf51dc0680eb959"
spec = importlib.util.spec_from_file_location(
    "extract_darwin", REPO / "tools/extract-source-darwin.py"
)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)
STOCK_SHA = extractor.STOCK_SHA


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_release(output, identity):
    # A version-named executable makes the bootstrap's exact-target contract
    # explicit. The signed Bun and complete source graph are manifest-pinned.
    target = output / VERSION
    target.write_text(
        f'#!/bin/sh\nexec "{output}/runtime/bun" "{output}/graph/cli" "$@"\n'
    )
    (output / "helpers").mkdir()
    trust = (REPO / "candidate/trust-file.py").read_text()
    (output / "helpers/trust-file.py").write_text(
        "# /// script\n# dependencies = []\n# ///\n" + trust
    )
    shutil.copy2(
        REPO / "candidate/verify-source-assets.py", output / "helpers/verify-assets.py"
    )
    shutil.copy2(
        REPO / "candidate/diagnostic.mjs", output / "extensions/diagnostic.mjs"
    )
    (output / "manifests").mkdir()
    contract = json.loads((REPO / "manifests/internal-sdk-2.1.226.json").read_text())
    contract["bridgeBuildId"] = BUILD
    contract["contractStatus"] = "candidate"
    contract["target"] = {
        "product": "Claude Code",
        "version": VERSION,
        "platform": "darwin",
        "architecture": "arm64",
        "stockSha256": STOCK_SHA,
        "fileSize": 199241568,
    }
    contract["apiVersions"]["rawSlotApi"] = "2.1.261-darwin-arm64.1"

    # Historical offsets are invalid for the extracted graph; keep slot meanings.
    def strip_old(obj):
        if isinstance(obj, dict):
            return {
                k: strip_old(v)
                for k, v in obj.items()
                if k
                not in {
                    "observedSymbol",
                    "observedOffset",
                    "observedAssignmentOffset",
                    "observations",
                    "supplier",
                    "source",
                    "notes",
                    "functionOffset",
                    "placement",
                    "coLocation",
                }
            }
        if isinstance(obj, list):
            return [strip_old(v) for v in obj]
        return obj

    contract = strip_old(
        {
            k: contract[k]
            for k in [
                "schemaVersion",
                "contractId",
                "contractStatus",
                "bridgeBuildId",
                "target",
                "apiVersions",
                "rendezvous",
                "policyDomains",
                "captureDomains",
            ]
        }
    )
    contract["compatibility"] = {
        "exactTargetRequired": True,
        "rawSlotsRequireExactBridgeBuild": True,
    }
    contract["compatibility"]["notes"] = [
        "Source-graph release; no byte offsets apply. Current supplier mapping is in source_patches_2_1_261.py. Runtime API 2 and positional meanings retained; exact raw-slot identity is versioned."
    ]
    (output / "manifests" / f"internal-sdk-{VERSION}.json").write_text(
        json.dumps(contract, indent=2) + "\n"
    )
    assets = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            rel = path.relative_to(output).as_posix()
            assets[rel] = {
                "sha256": sha(path),
                "mode": 0o555 if rel in {VERSION, "runtime/bun"} else 0o444,
            }
    identity["assets"] = assets
    identity["releaseId"] = f"{VERSION}-internal-sdk-darwin-arm64-{sha(target)[:8]}"
    (output / "release-manifest.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n"
    )
    manifest_sha = sha(output / "release-manifest.json")
    constants = {
        "RELEASE_ID": identity["releaseId"],
        "TARGET_VERSION": VERSION,
        "BRIDGE_BUILD_ID": BUILD,
        "TARGET_SHA256": sha(target),
        "RELEASE_MANIFEST_SHA256": manifest_sha,
        "VERIFY_HELPER_SHA256": sha(output / "helpers/verify-assets.py"),
    }
    lines = (
        "\n".join(k + "=" + json.dumps(v) for k, v in constants.items())
        + '\nMARKER_CONTENT="$RELEASE_ID $RELEASE_MANIFEST_SHA256"\n'
    )
    launcher = (
        (REPO / "candidate/source-launcher-2.1.261.in")
        .read_text()
        .replace("@@RELEASE_CONSTANTS@@", lines)
    )
    (output / "claude-renderpatch-candidate").write_text(launcher)
    (output / ".claude-renderpatch-release").write_text(
        identity["releaseId"] + " " + manifest_sha + "\n"
    )
    for path in sorted(output.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
        else:
            path.chmod(
                0o555
                if path.relative_to(output).as_posix()
                in {VERSION, "runtime/bun", "claude-renderpatch-candidate"}
                else 0o444
            )
    output.chmod(0o555)
    print(f"release_id={identity['releaseId']}\nmanifest_sha256={manifest_sha}")


def build(stock, bun, output, development=False):
    if output.exists() and not (
        development and (output / ".development-build").is_file()
    ):
        raise ValueError("refusing to overwrite an existing release")
    if sha(bun) != BUN_SHA:
        raise ValueError("Bun 1.4.1 Darwin arm64 SHA-256 mismatch")
    if subprocess.check_output([str(bun), "--version"], text=True).strip() != "1.4.1":
        raise ValueError("requires Bun 1.4.1")
    modules = extractor.records(stock.read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    if development:
        (output / ".development-build").touch()
    paths = {
        r["name"]: output / "graph" / r["name"][len(extractor.ROOT) :] for r in modules
    }
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
        data = (
            patched[row["name"][len(extractor.ROOT) :]].encode()
            if row["loader"] == 1
            else row["content"]
        )
        path.write_bytes(data)
    (output / "runtime").mkdir(exist_ok=True)
    shutil.copy2(bun, output / "runtime/bun")
    bootstrap = (REPO / "preload/bootstrap-2.1.246-linux.mjs").read_text()
    bootstrap = (
        bootstrap.replace("internal-sdk-2.1.246-linux-x64.6", BUILD)
        .replace("2.1.246-linux-x64.1", "2.1.261-darwin-arm64.1")
        .replace("2.1.246", VERSION)
        .replace(
            "1a0a662dc1bb938eaec38545abce9a4a69113d7d7f7c5e1a553ea276617b906a",
            STOCK_SHA,
        )
        .replace("247905800", "199241568")
    )
    (output / "bootstrap.mjs").write_text(bootstrap)
    shutil.copytree(
        REPO / "preload/extensions", output / "extensions", dirs_exist_ok=True
    )
    identity = {
        "schemaVersion": 1,
        "targetVersion": VERSION,
        "platform": "darwin-arm64",
        "bridgeBuildId": BUILD,
        "stockSha256": STOCK_SHA,
        "bunVersion": "1.4.1",
        "moduleCount": len(modules),
        "semanticEdits": changes,
        "policyDomains": list(range(5)),
        "captureDomains": list(range(6)),
    }
    (output / VERSION).write_text(json.dumps(identity, indent=2) + "\n")
    if not development:
        package_release(output, identity)
        return
    identity_sha = sha(output / VERSION)
    # Development launcher deliberately permits test preloads; installed launcher
    # is generated separately after verification and rejects ambient metadata.
    (output / "run-safe").write_text(
        f'#!/bin/sh\nexec "{output}/runtime/bun" "{output}/graph/cli" "$@"\n'
    )
    (output / "run").write_text(f'''#!/bin/sh
export BUN_OPTIONS="--preload={output}/bootstrap.mjs"
export CLAUDE_RENDERPATCH_ACTIVE=1
export CLAUDE_RENDERPATCH_MODULE="{output}/extensions/default.mjs"
export CLAUDE_RENDERPATCH_TARGET="{output}/{VERSION}"
export CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID="{BUILD}"
export CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256="{identity_sha}"
export CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION="{VERSION}"
exec "{output}/runtime/bun" "{output}/graph/cli" "$@"
''')
    for name in ["run", "run-safe"]:
        (output / name).chmod(0o755)
    print(json.dumps(identity, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stock", type=Path, required=True)
    p.add_argument("--bun", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--development", action="store_true")
    a = p.parse_args()
    build(a.stock.resolve(), a.bun.resolve(), a.output.resolve(), a.development)
