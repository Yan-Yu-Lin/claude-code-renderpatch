#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the immutable Claude Code 2.1.318 Darwin host bridge.

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

from host_patches_2_1_318 import patch_graph
from host_patches_2_1_318_resume import patch_resume
from host_patches_2_1_318_teammate_view import patch_teammate_view
from host_patches_2_1_318_teammate_bg import patch_teammate_bg

REPO = Path(__file__).resolve().parents[1]
VERSION = "2.1.318"
TEAM_ID = "Q6L2SF6YDW"
FILE_SIZE = 319598464
NATIVE_MODULES = {"audio-capture.node", "computer-use-input.node", "computer-use-swift.node"}
spec = importlib.util.spec_from_file_location(
    "extract_darwin", REPO / "tools/extract-source-darwin-2.1.318.py"
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


def top_level_non_declarations(source):
    """Return top-level text that is not a function declaration.

    Scans balanced braces while skipping string, template and regex-free
    minified code; sufficient for the entry prologue, which the builder
    requires to contain only `function name(...){...}` declarations.
    """
    rest, i = [], 0
    while i < len(source):
        match = re.match(r"\s*function\s+[\w$]+\s*\([^)]*\)\s*\{", source[i:])
        if not match:
            rest.append(source[i:])
            break
        i += match.end()
        depth, quote = 1, None
        while depth and i < len(source):
            ch = source[i]
            if quote:
                if ch == "\\":
                    i += 1
                elif ch == quote:
                    quote = None
            elif ch in "\"'`":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
    return "".join(rest).strip()


def build(stock, output, revision=1, mcp_background=False):
    """Build the complete core port, optionally adding the separately gated MCP recipe."""
    if revision < 1:
        raise ValueError("revision must be positive")
    build_id = f"host-{VERSION}-darwin-arm64.{revision}"
    baked = ["full-redraw", "explicit-subagent-model-routing",
             "resumable-stopped-agents", "teammate-transcript-view",
             "teammate-background-work"]
    if mcp_background:
        baked.extend(["mcp-owner-background", "mcp-background-now"])
    if output.exists():
        raise ValueError("refusing to overwrite an existing release")
    if sha(stock) != STOCK_SHA or stock.stat().st_size != FILE_SIZE:
        raise ValueError("official 2.1.318 executable SHA-256/size mismatch")
    subprocess.run(["codesign", "--verify", "--strict", str(stock)], check=True)
    if team_id(stock) != TEAM_ID:
        raise ValueError("official executable is not signed by Anthropic")
    modules = extractor.records(stock.read_bytes())
    natives = {r["name"][len(extractor.ROOT) :] for r in modules if r["name"].endswith(".node")}
    if natives != NATIVE_MODULES:
        raise ValueError(f"unexpected native modules: {sorted(natives)}")

    graph = output / "graph"
    paths = {r["name"]: graph / r["name"][len(extractor.ROOT) :] for r in modules}
    # Bun's compiled text loader returns a string from require(). Requiring an
    # extracted .txt/.md instead returns a module namespace, which breaks Mods'
    # state-library source compiler. Keep all loader-13 references in the exact
    # signed host; the extracted copies remain in the hash-verified asset set.
    import_paths = {
        r["name"]: r["name"] if r["loader"] == 13 else str(paths[r["name"]])
        for r in modules
    }
    texts = {}
    for row in modules:
        if row["loader"] != 1:
            continue
        text = re.sub(r"^(?:// *@bun[^\n]*\n)+", "", row["content"].decode())
        text = re.sub(
            r"/\$bunfs/root/[A-Za-z0-9/._$@+\-]+",
            lambda m: import_paths.get(m[0], m[0]),
            text,
        )
        texts[row["name"][len(extractor.ROOT) :]] = text
    # host.mjs stops the embedded entry at its first statement; require that
    # statement to be the trapped env write and the entry to run no other code
    # before it (every earlier top-level item is an import or a declaration).
    entry = texts["cli"]
    body = entry[entry.index("\n", entry.index("// Version: " + VERSION)) + 1 :]
    first = 'process.env.NoDefaultCurrentDirectoryInExePath="1";'
    if entry.count(first) != 1:
        raise ValueError("expected exactly one embedded entry host trap statement")
    # Reviewed complete static closure: declarations/constants, plus cwd/realpath
    # capture only. The seventh helper is upstream's storage-mode latch.
    static_imports = re.findall(r'import(?:\{[^}]*\}from)?"([^"]+)";', body[: body.index(first)])
    reviewed = {"chunk-sr5zgxjs.js", "chunk-h58p4vvs.js", "chunk-kw79qzsb.js",
                "chunk-3na38vnk.js", "chunk-6c7y6v7r.js", "chunk-34713hc6.js",
                "chunk-bgsak306.js"}
    if {Path(p).name for p in static_imports} != reviewed or len(static_imports) != 7:
        raise ValueError("embedded entry static closure changed")
    for name in reviewed:
        if re.search(r'import(?:\{[^}]*\}from)?"[^\"]*chunk-', texts[name]):
            raise ValueError(f"unreviewed transitive entry import in {name}")
    head = re.sub(r'import(?:\{[^}]*\}from)?"[^"]+";', "", body[: body.index(first)])
    if top_level_non_declarations(head):
        raise ValueError("embedded entry runs code before the host trap statement")
    def extra_patches(result, edit):
        patch_resume(result, edit)
        patch_teammate_view(result, edit)
        patch_teammate_bg(result, edit)
        if mcp_background:
            from host_patches_2_1_318_mcp_bg import patch_mcp_bg
            patch_mcp_bg(result, edit)

    patched, changes = patch_graph(texts, extra_patches)
    output.mkdir(parents=True)
    for row in modules:
        path = paths[row["name"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        rel = row["name"][len(extractor.ROOT) :]
        path.write_bytes(patched[rel].encode() if row["loader"] == 1 else row["content"])

    (output / "runtime").mkdir()
    shutil.copy2(stock, output / "runtime/claude")
    shutil.copy2(REPO / "preload/host-2.1.318.mjs", output / "host.mjs")
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
        "bridgeBuildId": build_id,
        "stockSha256": STOCK_SHA,
        "stockTeamId": TEAM_ID,
        "moduleCount": len(modules),
        "semanticEdits": changes,
        "bakedIn": baked,
        "hostLoaderSha256": assets["host.mjs"]["sha256"],
        "assets": assets,
    }
    identity["releaseId"] = f"{VERSION}-host-darwin-arm64-{identity['hostLoaderSha256'][:4]}{sha(output / 'graph/cli')[:4]}"
    (output / "release-manifest.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    manifest_sha = sha(output / "release-manifest.json")
    constants = {
        "RELEASE_ID": identity["releaseId"],
        "TARGET_VERSION": VERSION,
        "BRIDGE_BUILD_ID": build_id,
        "BAKED_IN": ",".join(baked),
        "TARGET_SHA256": STOCK_SHA,
        "TARGET_TEAM_ID": TEAM_ID,
        "RELEASE_MANIFEST_SHA256": manifest_sha,
        "VERIFY_HELPER_SHA256": assets["helpers/verify-assets.py"]["sha256"],
    }
    lines = (
        "\n".join(k + "=" + json.dumps(v) for k, v in constants.items())
        + '\nMARKER_CONTENT="$RELEASE_ID $RELEASE_MANIFEST_SHA256"\n'
    )
    launcher = (REPO / "candidate/host-launcher-2.1.318.in").read_text().replace(
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
    p.add_argument("--revision", type=int, default=1)
    p.add_argument("--mcp-background", action="store_true")
    a = p.parse_args()
    build(a.stock.resolve(), a.output.resolve(), a.revision, a.mcp_background)
