#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the immutable Claude Code 2.1.318 Linux x64 host bridge.

Same architecture as the Darwin 2.1.318 host bridge: the verbatim official
Linux executable (npm @anthropic-ai/claude-code-linux-x64@2.1.318, SHA-256
pinned) is the host, and a --preload host.mjs evaluates a patched copy of its
own extracted module graph. Linux cannot use the 2.1.246 extract-and-run-on-
public-Bun method any more: >= 2.1.271 needs Bun.ant.CellSegmenter, which only
exists in Anthropic's embedded Bun.

Minified identifiers and chunk names differ between the Darwin and Linux
builds, so the unchanged Darwin recipes are replayed against the pinned Darwin
graph while translate_anchors_2_1_318_linux mirrors each edit onto the Linux
graph through the same strict fail-closed editor. A JSON translation log is
stored in the release for review.

Release layout (all hash-pinned by release-manifest.json):
  runtime/claude                 verbatim official executable
  graph/                         its extracted module graph with baked-in edits
  host.mjs                       trusted --preload host loader (same as Darwin)
  helpers/{verify-assets,trust-file}.py
  translation-log.json           every Darwin->Linux anchor/identifier decision
  claude-renderpatch-candidate   generated launcher
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from host_patches_2_1_318 import patch_graph, strict_editor
from host_patches_2_1_318_resume import patch_resume
from host_patches_2_1_318_teammate_view import patch_teammate_view
from host_patches_2_1_318_teammate_bg import patch_teammate_bg
from host_patches_2_1_318_server_prompts import patch_server_prompts
from host_patches_2_1_318_session_title import patch_session_title
from host_patches_2_1_318_mcp_bg import patch_mcp_bg
from translate_anchors_2_1_318_linux import make_wrapper, verify_alpha_equivalence

REPO = Path(__file__).resolve().parents[1]
VERSION = "2.1.318"
NATIVE_MODULES = {"clipboard-napi.node", "audio-capture.node"}
PLATFORM = "linux-x64"
D_PREFIX = "/@darwin-graph/"
L_PREFIX = "/@linux-graph/"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


linux_x = load_module("extract_linux", REPO / "tools/extract-source-linux-2.1.318.py")
darwin_x = load_module("extract_darwin", REPO / "tools/extract-source-darwin-2.1.318.py")
STOCK_SHA = linux_x.STOCK_SHA
STOCK_SIZE = linux_x.STOCK_SIZE

# The Linux entry's static helper closure. Each was compared against the
# reviewed Darwin helper (identifier-normalized token stream identical).
REVIEWED_LINUX = {
    "chunk-0993wma0.js", "chunk-vwtpw18x.js", "chunk-23jq4b96.js",
    "chunk-svdpxfd7.js", "chunk-pnaj1q5d.js", "chunk-kd978n4z.js",
    "chunk-mycxs6m3.js",
}
LINUX_ONLY_HELPERS = {
    # declarations + `cwd()` capture; normalize helpers are `return n`.
    "chunk-0993wma0.js": "91816c6b8fca90ddf9ac39903fe4fc869b12439db9ca932a11bbee0c462c5018",
}
REVIEWED_DARWIN = {
    "chunk-sr5zgxjs.js", "chunk-h58p4vvs.js", "chunk-kw79qzsb.js",
    "chunk-3na38vnk.js", "chunk-6c7y6v7r.js", "chunk-34713hc6.js",
    "chunk-bgsak306.js",
}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def texts_of(modules, root, prefix):
    import_paths = {
        r["name"]: r["name"] if r["loader"] == 13 else prefix + r["name"][len(root):]
        for r in modules
    }
    texts = {}
    for row in modules:
        if row["loader"] != 1:
            continue
        text = re.sub(r"^(?:// *@bun[^\n]*\n)+", "", row["content"].decode())
        if prefix in text:
            raise ValueError(f"neutral prefix already present in {row['name']}")
        text = re.sub(
            r"/\$bunfs/root/[A-Za-z0-9/._$@+\-]+",
            lambda m: import_paths.get(m[0], m[0]),
            text,
        )
        texts[row["name"][len(root):]] = text
    return texts


def structural(text, prefix):
    text = text.replace(prefix, "/R/")
    text = re.sub(r"chunk-[a-z0-9]{8}\.js", "chunk-H.js", text)
    return re.sub(r"(?<![\w$])[A-Za-z_$][\w$]*", "I", text)


def check_entry(ltexts, dtexts):
    entry = ltexts["cli"]
    body = entry[entry.index("\n", entry.index("// Version: " + VERSION)) + 1:]
    first = 'process.env.NoDefaultCurrentDirectoryInExePath="1";'
    if entry.count(first) != 1:
        raise ValueError("expected exactly one embedded entry host trap statement")
    static = re.findall(r'import(?:\{[^}]*\}from)?"([^"]+)";', body[: body.index(first)])
    if {Path(p).name for p in static} != REVIEWED_LINUX or len(static) != 7:
        raise ValueError(f"embedded entry static closure changed: {static}")
    # Six helpers are token-for-token the reviewed Darwin helpers (identifiers
    # normalized). The seventh is the cwd capture helper, whose macOS NFC/
    # realpath normalizers compile to identity functions on Linux; it was
    # reviewed separately and is pinned by exact content hash.
    dshapes = [structural(dtexts[n], D_PREFIX) for n in REVIEWED_DARWIN]
    unmatched = []
    for name in sorted(REVIEWED_LINUX):
        shape = structural(ltexts[name], L_PREFIX)
        if shape in dshapes:
            dshapes.remove(shape)
        else:
            unmatched.append(name)
    pinned = {name: hashlib.sha256(ltexts[name].encode()).hexdigest() for name in unmatched}
    if pinned != LINUX_ONLY_HELPERS:
        raise ValueError(f"Linux entry helpers differ from the reviewed set: {pinned}")
    for name in REVIEWED_LINUX:
        if re.search(r'import(?:\{[^}]*\}from)?"[^"]*chunk-', ltexts[name]):
            raise ValueError(f"unreviewed transitive entry import in {name}")
    head = re.sub(r'import(?:\{[^}]*\}from)?"[^"]+";', "", body[: body.index(first)])
    if top_level_non_declarations(head):
        raise ValueError("embedded entry runs code before the host trap statement")


def top_level_non_declarations(source):
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


def translate(linux_modules, darwin_stock, revision, mcp_background):
    root = linux_x.ROOT
    ltexts = texts_of(linux_modules, root, L_PREFIX)
    dmodules = darwin_x.records(darwin_stock.read_bytes())
    dtexts = texts_of(dmodules, root, D_PREFIX)
    check_entry(ltexts, dtexts)

    lresult = dict(ltexts)
    lchanged = {}
    lstrict = strict_editor(lresult, lchanged)
    log = []

    def extra_patches(result, edit):
        patch_resume(result, edit)
        patch_teammate_view(result, edit)
        patch_teammate_bg(result, edit)
        if mcp_background:
            patch_mcp_bg(result, edit)
        if revision >= 4:
            patch_server_prompts(result, edit)
        if revision >= 5:
            patch_session_title(result, edit)

    wrap = make_wrapper(dtexts, lresult, D_PREFIX, L_PREFIX, lstrict, log)
    dresult, dchanged = patch_graph(dtexts, extra_patches, wrap)
    widths = verify_alpha_equivalence(dresult, lresult, log)
    print(json.dumps({"alpha_checked": len(widths), "min_context": min(widths),
                      "median_context": sorted(widths)[len(widths) // 2]}))
    return lresult, lchanged, dchanged, log


def build(stock, darwin_stock, output, revision, mcp_background, translate_only=None):
    build_id = f"host-{VERSION}-{PLATFORM}.{revision}"
    baked = ["full-redraw", "explicit-subagent-model-routing",
             "resumable-stopped-agents", "teammate-transcript-view",
             "teammate-background-work"]
    if mcp_background:
        baked.extend(["mcp-owner-background", "mcp-background-now"])
    if revision >= 4:
        baked.append("block-server-prompt-injection")
    if revision >= 5:
        baked.append("essential-traffic-session-title")
    if sha(stock) != STOCK_SHA or stock.stat().st_size != STOCK_SIZE:
        raise ValueError("official 2.1.318 linux-x64 executable SHA-256/size mismatch")
    modules = linux_x.records(stock.read_bytes())
    natives = {r["name"][len(linux_x.ROOT):] for r in modules if r["name"].endswith(".node")}
    if natives != NATIVE_MODULES:
        raise ValueError(f"unexpected native modules: {sorted(natives)}")

    patched, lchanged, dchanged, log = translate(modules, darwin_stock, revision, mcp_background)
    # Darwin import-list edits become appended import declarations on Linux.
    import_edits = sum(1 for r in log if "linux_append" in r and "old" in r)
    if sum(lchanged.values()) + import_edits != sum(dchanged.values()):
        raise ValueError(f"edit count mismatch linux={sum(lchanged.values())}+{import_edits} darwin={sum(dchanged.values())}")
    if any("linux_new" not in r and "linux_append" not in r and "linux_extra" not in r for r in log):
        raise ValueError("untranslated record in log")
    summary = {"linux_edits": sum(lchanged.values()), "linux_import_edits": import_edits,
               "darwin_edits": sum(dchanged.values()),
               "linux_chunks": len(lchanged), "darwin_chunks": len(dchanged)}
    if translate_only is not None:
        translate_only.write_text(json.dumps({"summary": summary, "log": log}, indent=1))
        print(json.dumps(summary))
        return

    if output.exists():
        raise ValueError("refusing to overwrite an existing release")
    graph = output / "graph"
    final = str(graph) + "/"
    output.mkdir(parents=True)
    for row in modules:
        rel = row["name"][len(linux_x.ROOT):]
        path = graph / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if row["loader"] == 1:
            path.write_bytes(patched[rel].replace(L_PREFIX, final).encode())
        else:
            path.write_bytes(row["content"])
    leftovers = [p for p in graph.rglob("*.js") if L_PREFIX.encode() in p.read_bytes() or D_PREFIX.encode() in p.read_bytes()]
    if leftovers:
        raise ValueError(f"neutral prefixes left in {leftovers[:3]}")

    (output / "runtime").mkdir()
    shutil.copy2(stock, output / "runtime/claude")
    shutil.copy2(REPO / "preload/host-2.1.318.mjs", output / "host.mjs")
    (output / "helpers").mkdir()
    shutil.copy2(REPO / "candidate/trust-file.py", output / "helpers/trust-file.py")
    shutil.copy2(REPO / "candidate/verify-source-assets.py", output / "helpers/verify-assets.py")
    (output / "translation-log.json").write_text(json.dumps({"summary": summary, "log": log}, indent=1))

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
        "platform": PLATFORM,
        "bridgeBuildId": build_id,
        "stockSha256": STOCK_SHA,
        "stockNpmPackage": linux_x.NPM_PACKAGE,
        "stockNpmIntegrity": linux_x.NPM_INTEGRITY,
        "recipeSourceSha256": darwin_x.STOCK_SHA,
        "moduleCount": len(modules),
        "semanticEdits": lchanged,
        "bakedIn": baked,
        "hostLoaderSha256": assets["host.mjs"]["sha256"],
        "assets": assets,
    }
    identity["releaseId"] = f"{VERSION}-host-{PLATFORM}-{identity['hostLoaderSha256'][:4]}{sha(graph / 'cli')[:4]}"
    (output / "release-manifest.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    manifest_sha = sha(output / "release-manifest.json")
    constants = {
        "RELEASE_ID": identity["releaseId"],
        "TARGET_VERSION": VERSION,
        "BRIDGE_BUILD_ID": build_id,
        "BAKED_IN": ",".join(baked),
        "TARGET_SHA256": STOCK_SHA,
        "RELEASE_MANIFEST_SHA256": manifest_sha,
        "VERIFY_HELPER_SHA256": assets["helpers/verify-assets.py"]["sha256"],
        "TRUST_HELPER_SHA256": assets["helpers/trust-file.py"]["sha256"],
    }
    lines = (
        "\n".join(k + "=" + json.dumps(v) for k, v in constants.items())
        + '\nMARKER_CONTENT="$RELEASE_ID $RELEASE_MANIFEST_SHA256"\n'
    )
    launcher = (REPO / "candidate/host-launcher-2.1.318-linux.in").read_text().replace(
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
    p.add_argument("--stock", type=Path, required=True, help="official linux-x64 2.1.318 claude")
    p.add_argument("--darwin-stock", type=Path, required=True, help="official darwin-arm64 2.1.318 claude (recipe source)")
    p.add_argument("--output", type=Path)
    p.add_argument("--revision", type=int, default=1)
    p.add_argument("--mcp-background", action="store_true")
    p.add_argument("--translate-only", type=Path, help="write the translation log here and stop")
    a = p.parse_args()
    if a.translate_only is None and a.output is None:
        p.error("--output is required unless --translate-only is given")
    build(a.stock.resolve(), a.darwin_stock.resolve(), a.output.resolve() if a.output else None,
          a.revision, a.mcp_background, a.translate_only)
