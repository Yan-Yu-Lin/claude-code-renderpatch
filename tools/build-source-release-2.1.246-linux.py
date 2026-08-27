#!/usr/bin/env python3
"""Build an immutable Linux source-graph release from stock Claude Code 2.1.246."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
from pathlib import Path

VERSION = "2.1.246"
BRIDGE_BUILD_ID = "internal-sdk-2.1.246-linux-x64.6"
EXPECTED_STOCK_SHA256 = "1a0a662dc1bb938eaec38545abce9a4a69113d7d7f7c5e1a553ea276617b906a"
EXPECTED_STOCK_SIZE = 247_905_800
TRAILER = b"\n---- Bun! ----\n"
BUN_OFFSET = 86_872_064
BUN_SIZE = 160_976_213
MODULE_RECORD_SIZE = 52
OFFSET_STRUCT_SIZE = 32
PATH_PATTERN = re.compile(r"/\$bunfs/root/[A-Za-z0-9/._$@+\-]+")
ROOT_PREFIX = "/$bunfs/root/"
JS_LOADER = 1
NAPI_LOADER = 10

MODULES = {
    "context": "_668.js",
    "reset": "_483.js",
    "key_manager": "_481.js",
    "routing": "_441.js",
    "key_lifecycle": "_236.js",
    "messages": "_104.js",
    "repl": "_26.js",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one source anchor, found {count}")
    return text.replace(old, new, 1)


def parse_modules(stock: bytes) -> tuple[list[dict[str, object]], int]:
    section = stock[BUN_OFFSET : BUN_OFFSET + BUN_SIZE]
    if len(section) != BUN_SIZE:
        raise ValueError("stock binary has a truncated .bun section")
    payload_size = int.from_bytes(section[:8], "little")
    if payload_size + 8 > len(section):
        raise ValueError(".bun payload exceeds section")
    payload = section[8 : 8 + payload_size]
    if not payload.endswith(TRAILER):
        raise ValueError(".bun trailer mismatch")
    offset_start = len(payload) - len(TRAILER) - OFFSET_STRUCT_SIZE
    modules_offset = struct.unpack_from("<I", payload, offset_start + 8)[0]
    modules_size = struct.unpack_from("<I", payload, offset_start + 12)[0]
    entry_id = struct.unpack_from("<I", payload, offset_start + 16)[0]
    if modules_size % MODULE_RECORD_SIZE:
        raise ValueError("module table size is not record-aligned")
    count = modules_size // MODULE_RECORD_SIZE
    if entry_id >= count:
        raise ValueError("entry module id is out of range")
    modules: list[dict[str, object]] = []
    for index in range(count):
        record_offset = modules_offset + index * MODULE_RECORD_SIZE
        record = payload[record_offset : record_offset + MODULE_RECORD_SIZE]
        name_offset, name_size, content_offset, content_size = struct.unpack_from(
            "<IIII", record, 0
        )
        loader = record[49]
        name = payload[name_offset : name_offset + name_size].decode("utf-8").rstrip("\0")
        content = payload[content_offset : content_offset + content_size]
        modules.append(
            {
                "index": index,
                "entry": index == entry_id,
                "name": name.replace("\\", "/"),
                "loader": loader,
                "content": content,
            }
        )
    return modules, entry_id


def napi_basename(name: str) -> str:
    return name.rsplit("/", 1)[-1].removesuffix(".node")


def relative_asset_path(name: str, loader: int) -> Path | None:
    if loader == NAPI_LOADER:
        base = napi_basename(name)
        if not base:
            return None
        return Path("vendor") / base / "x64-linux" / f"{base}.node"
    if not name.startswith(ROOT_PREFIX):
        return None
    subpath = name[len(ROOT_PREFIX) :]
    if not subpath or ".." in Path(subpath).parts:
        return None
    return Path("graph") / subpath


def safe_query(domain: int, fallback: str, payload: str) -> str:
    return (
        "(()=>{try{return globalThis.__rp?.q?.("
        f"{domain},{fallback}{payload})??{fallback}"
        f"}}catch{{return {fallback}}}}})()"
    )


def patch_context(text: str) -> str:
    old_resolver = (
        "function RE(e,t){if(Oe(e))return 1e6;if(t?.includes(sr.header)&&Nf(e))return 1e6;"
        "if(Vo(e))return 1e6;let n=rM(e);if(n!==null)return n;let r=c.CLAUDE_CODE_MAX_CONTEXT_TOKENS;"
        "if(r!==void 0&&r>0&&!P(X(e)).startsWith(\"claude-\"))return r;return AE}"
    )
    query = safe_query(3, "n", ",P(X(e))")
    new_resolver = (
        "function RE(e,t){let n=Oe(e)||t?.includes(sr.header)&&Nf(e)||Vo(e)?1e6:rM(e),"
        "r=c.CLAUDE_CODE_MAX_CONTEXT_TOKENS;n??=r!==void 0&&r>0&&!P(X(e)).startsWith(\"claude-\")"
        f"?r:AE;return {query}}}"
    )
    text = replace_once(text, old_resolver, new_resolver, "provider context policy")
    constants = "var AE=200000,kE=200000,QI=32000,ZI=128000,nM=1e6;"
    capture_base = (
        constants
        + "globalThis.__rpD0=[,,,P,,Dt,Gr,RE,Oe,Vo,Nf,wE,tM,rM,iM];"
    )
    return replace_once(text, constants, capture_base, "d0 context suppliers")


def patch_reset(text: str) -> str:
    old = "function Bu(e,o,i,l,s,u){let f="
    query = safe_query(1, "!1", ",o,l")
    new = f"function Bu(e,o,i,l,s,u){{l||=!!{query};let f="
    return replace_once(text, old, new, "renderer reset policy")


def patch_key_manager(text: str) -> str:
    old = (
        "let Ke=qe,ze;if(D[21]!==Ce||D[22]!==Ke)ze=K(I.Provider,{value:Ke,children:Ce}),"
        "D[21]=Ce,D[22]=Ke,D[23]=ze;else ze=D[23];return ze}"
    )
    new = (
        "return K(I.Provider,{value:qe,children:K(Ce.type,{...Ce.props,__rp:["
        "globalThis.__rpG=(globalThis.__rpG??0)+1,qe,y,he,W,be,ye,de,fe,ue]})})}"
    )
    return replace_once(text, old, new, "d5 key payload")


def patch_routing(text: str) -> str:
    old = "if(n){if(n===\"inherit\")return s();if(PGn(n,t))return t;"
    fallback = "PGn(n,t)"
    query = safe_query(4, fallback, ",n,t")
    new = f"if(n){{if(n===\"inherit\")return s();if({query})return t;"
    text = replace_once(text, old, new, "explicit subagent routing policy")
    old_initializer = (
        "var kJ=w(()=>{_t();bS();Yt();vk();be();Dt();h_();Spe();mo();Coe();wTt();Zo();A2o()});"
    )
    new_initializer = (
        "var kJ=w(()=>{_t();bS();Yt();vk();be();Dt();h_();Spe();mo();Coe();wTt();Zo();A2o();"
        "let A=globalThis.__rpD0||[];try{globalThis.__rp?.c?.(0,0,4194303,[Lk,Wa,zm,A[3],"
        "cu,A[5],...A.slice(6),tE,MGn,kTt,PGn,P2o,wJ,x2o])}catch{}"
        "delete globalThis.__rpD0});"
    )
    return replace_once(text, old_initializer, new_initializer, "d0 routing capture")


def patch_key_lifecycle(text: str) -> str:
    old_header = (
        "function yr(Ha){let se=O(28),{bindings:Y,pendingChordRef:Z,setPendingChord:E,"
        "activeContexts:St,handlerRegistryRef:Te,preDispatchRef:Yo,keyHandlerRegistry:Zo,"
        "children:er}=Ha,"
    )
    new_header = old_header.replace("O(28)", "O(29)").replace(
        "children:er}=Ha,", "children:er,__rp:RP}=Ha,"
    )
    text = replace_once(text, old_header, new_header, "d5 lifecycle props")
    old_effect = (
        "if(se[22]===Q)pi=()=>{if(!Rt.current){return}let Ce=Ct(Rt.current);let mi=()=>{"
        "let Je=Rt.current;if(!Je||Ce.activeElement===Je){return}if(Ce.activeElement===null){"
        "Ce.focus(Je);return}let _t=Je.parentNode;while(_t){if(_t===Ce.activeElement){Ce.focus(Je);"
        "return}_t=_t.parentNode}};return mi(),Ce.subscribe(mi)},fi=[],se[22]=pi,se[23]=fi;"
        "else pi=se[22],fi=se[23];"
    )
    new_effect = (
        "if(se[22]!==RP)pi=()=>{let e,t;if(RP){let[n,...r]=RP;"
        "try{globalThis.__rp?.c?.(5,n,511,r)}catch{}t=n}if(Rt.current){let n=Ct(Rt.current),"
        "r=()=>{let e=Rt.current;if(!e||n.activeElement===e)return;if(n.activeElement===null)"
        "return void n.focus(e);for(let t=e.parentNode;t;){if(t===n.activeElement)return void n.focus(e);"
        "t=t.parentNode}};r(),e=n.subscribe(r)}return()=>{e?.();if(t!==void 0)try{"
        "globalThis.__rp?.c?.(5,t,0,null)}catch{}}},fi=[RP],se[22]=RP,se[23]=pi,se[28]=fi;"
        "else pi=se[23],fi=se[28];"
    )
    text = replace_once(text, old_effect, new_effect, "d5 capture lifecycle")
    old_render = (
        'Tt(pi,fi);let gi;if(se[24]!==er||se[25]!==nr||se[26]!==ir)gi=s(Et,{ref:Rt,'
        'keybindingScope:"Global",tabIndex:-1,flexDirection:"column",flexGrow:1,'
        'onKeyDownCapture:nr,onWheelCapture:ir,children:er}),se[24]=er,se[25]=nr,se[26]=ir,'
        'se[27]=gi;else gi=se[27];return gi}'
    )
    new_render = (
        'Tt(pi,fi);return s(Et,{ref:Rt,keybindingScope:"Global",tabIndex:-1,'
        'flexDirection:"column",flexGrow:1,onKeyDownCapture:nr,onWheelCapture:ir,children:er})}'
    )
    return replace_once(text, old_render, new_render, "d5 lifecycle render")


def patch_messages(text: str) -> str:
    query = safe_query(0, "0", ",a")
    old_policy = "Ie=Kg(),ot=!1,Me=re(()=>null,[e,!1]),"
    new_policy = (
        f"Ie=Kg(),ot={query},rm=m||!!(1&ot),dc=P||!!(2&ot),Me=re(()=>null,[e,ot]),"
    )
    text = replace_once(text, old_policy, new_policy, "renderer messages policy")
    text = replace_once(
        text,
        "Ve=W!=null&&!z",
        "Ve=W!=null&&!z&&!dc",
        "transcript virtual-scroll gate",
    )
    for old, new in (
        ("Le=h&&!m&&!Ve", "Le=h&&!rm&&!Ve"),
        ("let At=!Ve&&!P?", "let At=!Ve&&!dc?"),
        ("let V=!Ve&&!P?", "let V=!Ve&&!dc?"),
        ("[Pt,k,Ve,P,Xe]", "[Pt,k,Ve,dc,Xe]"),
        ("h&&m&&ho>0&&!P", "h&&rm&&ho>0&&!dc"),
    ):
        text = replace_once(text, old, new, f"renderer messages alias {old}")
    old_capture = "},[Pt,k,Ve,dc,Xe]),M="
    slots = "[e,G,ve,Pt,T,At,It,St,wn,ho,Ve,Xe,a,rm,dc,k]"
    new_capture = (
        "},[Pt,k,Ve,dc,Xe]),rp=globalThis.__rpG=(globalThis.__rpG??0)+1,"
        "rc=(()=>{try{globalThis.__rp?.c?.(3,rp,65535,"
        + slots
        + ")}catch{}})(),M="
    )
    text = replace_once(text, old_capture, new_capture, "d3 render capture")
    old_cleanup = "te(()=>()=>Bt(null),[Bt])"
    new_cleanup = (
        "te(()=>()=>{Bt(null);try{globalThis.__rp?.c?.(3,rp,0,null)}catch{}},[Bt,rp])"
    )
    return replace_once(text, old_cleanup, new_cleanup, "d3 render cleanup")


def patch_toggle(text: str) -> str:
    telemetry = (
        'q("tengu_toggle_transcript",{is_entering:r1!=="transcript",show_all:Fle,'
        'message_count:Ile,open_dialog_count:Lle.getState().open.length}),Mle()'
    )
    query = safe_query(2, "!1", ',r1!=="transcript"')
    return replace_once(
        text,
        telemetry,
        telemetry + f",{query}&&setTimeout(F6e,50)",
        "toggle redraw policy",
    )


def patch_repl(text: str) -> str:
    old_header = (
        "function J1(LLt){let ba=Q(84),{focused:Di,tools:tR,commands:rue,turn:iue,"
        "onOpenRateLimitOptions:sue,hideWelcomeChrome:aue,toolJSX:D1,scrollRef:jc,"
        "virtualScrollActive:$c,embedded:lue,scrollKeysActive:uue,showSandboxViolations:P1,"
        "dumpMode:el,onDumpToScrollback:cue,onExit:oR}=LLt,due=it(),{storageV5:mue}=Ve(),"
        "pue=Tt(),[OLt,BLt]=L(!1),Il=OLt||el,"
    )
    new_header = old_header.replace(
        "showSandboxViolations:P1,dumpMode:el,",
        "showSandboxViolations:P1,showAllInTranscript:rpa,setShowAllInTranscript:rps,dumpMode:el,",
    ).replace("[OLt,BLt]=L(!1),Il=OLt||el,", "Il=rpa||el,BLt=rps,")
    text = replace_once(text, old_header, new_header, "REPL transcript props")
    text = replace_once(
        text,
        '[se,re]=L("prompt"),[oe,ge]=L(!1),ke=H(()=>{re("prompt"),ge(!1)},[]),',
        '[se,re]=L("prompt"),[oe,ge]=L(!1),[rpa,rps]=L(!1),'
        'ke=H(()=>{re("prompt"),ge(!1),rps(!1)},[]),',
        "REPL transcript state",
    )
    text = replace_once(
        text,
        "let pI=co()&&!K,",
        "let pI=!1,",
        "transcript alternate-screen gate",
    )
    d1_slots = "[Xa,,,,,,,,,,,,,It,,D,,,,,q]"
    capture = (
        "composer:jt});let rpg=globalThis.__rpG=(globalThis.__rpG??0)+1,"
        "rpc=(...J)=>{try{globalThis.__rp?.c?.(...J)}catch{}},"
        'rpt={onToggleTranscript:()=>{re(J=>J==="transcript"?"prompt":"transcript"),rps(!1)},redraw:F6e};'
        "globalThis.__rpS||(globalThis.__rpS=1,rpc(1,0,1089537,"
        + d1_slots
        + "));rpc(2,rpg,31,[ze,It,ze.getState,Oe,ze.subscribe]);"
        "rpc(4,rpg,65535,[ze,Oe,Ti,se,re,rpa,rps,oe,ge,kn,Al,Bt,zn,yt,null,rpt]);"
        "x(()=>()=>{rpc(2,rpg,0,null);rpc(4,rpg,0,null)},[rpg]);function Ih(J){"
    )
    text = replace_once(text, "composer:jt});function Ih(J){", capture, "REPL captures")
    old_transcript = (
        "i(J1,{focused:Ti,tools:Bt,commands:kn,turn:Ge,onOpenRateLimitOptions:oI,"
        "hideWelcomeChrome:O??P,toolJSX:qe,scrollRef:J,virtualScrollActive:pI,embedded:P,"
        'scrollKeysActive:Ri!=="ultraplan-choice",showSandboxViolations:!Ee,dumpMode:oe,'
        "onDumpToScrollback:()=>ge(!0),onExit:ke})"
    )
    new_transcript = old_transcript.replace(
        "showSandboxViolations:!Ee,",
        "showSandboxViolations:!Ee,showAllInTranscript:rpa,setShowAllInTranscript:rps,",
    )
    text = replace_once(text, old_transcript, new_transcript, "REPL message props")
    text = replace_once(
        text,
        'if(se==="transcript"){let J=P||co()&&!K&&!oe?yt:void 0,',
        'if(se==="transcript"){let J=P?yt:void 0,',
        "classic transcript wrapper",
    )
    text = replace_once(
        text,
        "return i(R8e,{mouseTracking:u$(),children:J})",
        "return J",
        "classic main-screen wrapper",
    )
    old_toggle = (
        'i(hk,{screen:se,onToggleTranscript:()=>re((J)=>J==="transcript"?"prompt":"transcript"),'
        "messageCount:Ti.messages.length})"
    )
    new_toggle = (
        "i(hk,{screen:se,onToggleTranscript:rpt.onToggleTranscript,"
        "messageCount:Ti.messages.length})"
    )
    return replace_once(text, old_toggle, new_toggle, "REPL toggle handler")


def apply_source_patches(texts: dict[str, str]) -> dict[str, str]:
    patched = dict(texts)
    patched[MODULES["context"]] = patch_context(patched[MODULES["context"]])
    patched[MODULES["reset"]] = patch_reset(patched[MODULES["reset"]])
    patched[MODULES["key_manager"]] = patch_key_manager(patched[MODULES["key_manager"]])
    patched[MODULES["routing"]] = patch_routing(patched[MODULES["routing"]])
    patched[MODULES["key_lifecycle"]] = patch_key_lifecycle(
        patched[MODULES["key_lifecycle"]]
    )
    patched[MODULES["messages"]] = patch_messages(patched[MODULES["messages"]])
    patched[MODULES["repl"]] = patch_toggle(patched[MODULES["repl"]])
    patched[MODULES["repl"]] = patch_repl(patched[MODULES["repl"]])
    return patched


def render_launcher(release_id: str, identity_sha: str, asset_list_sha: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

RELEASE_ID={json.dumps(release_id)}
TARGET_VERSION={json.dumps(VERSION)}
BRIDGE_BUILD_ID={json.dumps(BRIDGE_BUILD_ID)}
IDENTITY_SHA256={json.dumps(identity_sha)}
ASSET_LIST_SHA256={json.dumps(asset_list_sha)}
ROOT="$(dirname "$(readlink -f "$0")")"
BUN="$ROOT/runtime/bun"
ENTRY="$ROOT/graph/cli"
BOOTSTRAP="$ROOT/bootstrap.mjs"
DEFAULT_EXTENSION="$ROOT/extensions/default.mjs"
IDENTITY="$ROOT/{VERSION}"
ASSET_LIST="$ROOT/assets.sha256"

sha256() {{ sha256sum "$1" | cut -d ' ' -f 1; }}
fail() {{ echo "claude-renderpatch: $*" >&2; exit 1; }}
verify_release() {{
  [[ ! -L "$ROOT" && -d "$ROOT" ]] || fail "release root is missing or a symlink"
  [[ "$(sha256 "$IDENTITY")" == "$IDENTITY_SHA256" ]] || fail "identity hash mismatch"
  [[ "$(sha256 "$ASSET_LIST")" == "$ASSET_LIST_SHA256" ]] || fail "asset list hash mismatch"
  (cd "$ROOT" && sha256sum --check --quiet assets.sha256) || fail "release asset hash mismatch"
}}
scrub() {{
  unset BUN_OPTIONS CLAUDE_RENDERPATCH_ACTIVE CLAUDE_RENDERPATCH_MODULE \
    CLAUDE_RENDERPATCH_USER_MODULE CLAUDE_RENDERPATCH_TARGET \
    CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256 \
    CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION CLAUDE_PRELOAD_TARGET \
    CLAUDE_PRELOAD_VERSIONS_DIR CLAUDE_PRELOAD_BOOTSTRAP
}}
reject_ambient() {{
  for name in BUN_OPTIONS CLAUDE_RENDERPATCH_ACTIVE CLAUDE_RENDERPATCH_MODULE \
    CLAUDE_RENDERPATCH_USER_MODULE CLAUDE_RENDERPATCH_TARGET \
    CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256 \
    CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION; do
    [[ ! -v "$name" ]] || fail "refusing inherited $name; use --renderpatch-safe or unset it"
  done
}}

mode=normal
user_module=""
args=()
while (($#)); do
  case "$1" in
    --renderpatch-safe) [[ "$mode" == normal ]] || fail "wrapper modes are exclusive"; mode=safe; shift ;;
    --renderpatch-status) [[ "$mode" == normal ]] || fail "wrapper modes are exclusive"; mode=status; shift ;;
    --renderpatch-extension)
      (($# >= 2)) || fail "--renderpatch-extension requires an absolute path"
      [[ "$2" == /* ]] || fail "extension path must be absolute"
      [[ -z "$user_module" ]] || fail "extension may be supplied once"
      user_module="$2"; shift 2 ;;
    --) shift; args+=("$@"); break ;;
    *) args+=("$1"); shift ;;
  esac
done
set -- "${{args[@]}}"

verify_release
if [[ "$mode" == status ]]; then
  (($# == 0)) || fail "--renderpatch-status accepts no Claude arguments"
  scrub
  reported="$($BUN "$ENTRY" --version)"
  printf 'release_id=%s\ntarget_version=%s\nreported_version=%s\nbridge_build_id=%s\nidentity_sha256=%s\npolicy_domains=0,1,2,3,4\ncapture_domains=0,1,2,3,4,5\nverification=ok\n' \
    "$RELEASE_ID" "$TARGET_VERSION" "$reported" "$BRIDGE_BUILD_ID" "$IDENTITY_SHA256"
  exit 0
fi
if [[ "$mode" == safe ]]; then
  scrub
  exec "$BUN" "$ENTRY" "$@"
fi
reject_ambient
export BUN_OPTIONS="--preload=$BOOTSTRAP"
export CLAUDE_RENDERPATCH_ACTIVE=1
export CLAUDE_RENDERPATCH_MODULE="$DEFAULT_EXTENSION"
if [[ -n "$user_module" ]]; then export CLAUDE_RENDERPATCH_USER_MODULE="$user_module"; fi
export CLAUDE_RENDERPATCH_TARGET="$IDENTITY"
export CLAUDE_RENDERPATCH_BRIDGE_BUILD_ID="$BRIDGE_BUILD_ID"
export CLAUDE_RENDERPATCH_BRIDGE_ARTIFACT_SHA256="$IDENTITY_SHA256"
export CLAUDE_RENDERPATCH_BRIDGE_TARGET_VERSION="$TARGET_VERSION"
exec "$BUN" "$ENTRY" "$@"
'''


def chmod_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
        elif path.name in {"bun", "claude-renderpatch"}:
            path.chmod(0o555)
        else:
            path.chmod(0o444)
    root.chmod(0o555)



def remove_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in (root, *root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
    shutil.rmtree(root)
def build(stock_path: Path, bun_path: Path, output: Path, force: bool) -> None:
    stock = stock_path.read_bytes()
    if len(stock) != EXPECTED_STOCK_SIZE or digest(stock) != EXPECTED_STOCK_SHA256:
        raise ValueError("stock Claude Code 2.1.246 size/SHA-256 mismatch")
    bun_path = bun_path.resolve(strict=True)
    bun_version = subprocess.run(
        [str(bun_path), "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if bun_version != "1.4.0":
        raise ValueError(f"expected Bun 1.4.0, found {bun_version}")
    modules, entry_id = parse_modules(stock)
    paths: dict[str, Path] = {}
    records: list[tuple[dict[str, object], Path]] = []
    for module in modules:
        relative = relative_asset_path(str(module["name"]), int(module["loader"]))
        if relative is None:
            continue
        paths[str(module["name"])] = output / relative
        records.append((module, relative))
    entry = modules[entry_id]
    entry_relative = relative_asset_path(str(entry["name"]), int(entry["loader"]))
    if entry_relative != Path("graph/cli"):
        raise ValueError(f"unexpected entry module: {entry['name']}")
    missing = [name for name in MODULES.values() if ROOT_PREFIX + name not in paths]
    if missing:
        raise ValueError(f"missing semantic source modules: {missing}")

    js_texts: dict[str, str] = {}
    for module, relative in records:
        if int(module["loader"]) != JS_LOADER:
            continue
        text = bytes(module["content"]).decode("utf-8")
        text = re.sub(r"^(?:// *@bun[^\n]*\n)+", "", text)
        text = PATH_PATTERN.sub(lambda match: str(paths.get(match.group(0), Path(match.group(0)))), text)
        js_texts[relative.name] = text
    patched_texts = apply_source_patches(js_texts)

    temporary = output.with_name(output.name + f".tmp-{os.getpid()}")
    if temporary.exists():
        remove_tree(temporary)
    if output.exists():
        if not force:
            raise FileExistsError(f"release already exists: {output}")
        remove_tree(output)
    temporary.mkdir(parents=True)
    try:
        for module, relative in records:
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if int(module["loader"]) == JS_LOADER:
                destination.write_text(patched_texts[relative.name], encoding="utf-8")
            else:
                destination.write_bytes(bytes(module["content"]))
        (temporary / "runtime").mkdir()
        shutil.copy2(bun_path, temporary / "runtime/bun")
        repo = Path(__file__).resolve().parents[1]
        shutil.copy2(repo / "preload/bootstrap-2.1.246-linux.mjs", temporary / "bootstrap.mjs")
        shutil.copytree(repo / "preload/extensions", temporary / "extensions")

        assets = sorted(
            path
            for path in temporary.rglob("*")
            if path.is_file() and path.name not in {"assets.sha256", VERSION, "claude-renderpatch"}
        )
        asset_lines = [f"{file_digest(path)}  {path.relative_to(temporary).as_posix()}" for path in assets]
        asset_list = "\n".join(asset_lines) + "\n"
        (temporary / "assets.sha256").write_text(asset_list, encoding="utf-8")
        asset_list_sha = digest(asset_list.encode())
        graph_digest = digest(
            "\n".join(line for line in asset_lines if "  graph/" in line).encode()
        )
        release_id = f"{VERSION}-internal-sdk-linux-x64-{graph_digest[:8]}"
        identity = {
            "schemaVersion": 1,
            "releaseId": release_id,
            "product": "Claude Code",
            "targetVersion": VERSION,
            "platform": "linux-x64",
            "bridgeBuildId": BRIDGE_BUILD_ID,
            "stockSha256": EXPECTED_STOCK_SHA256,
            "bunVersion": bun_version,
            "bunSha256": file_digest(temporary / "runtime/bun"),
            "sourceGraphSha256": graph_digest,
            "assetsListSha256": asset_list_sha,
            "moduleCount": len(modules),
            "extractedAssetCount": len(records),
            "semanticRanges": 8,
            "policyDomains": [0, 1, 2, 3, 4],
            "captureDomains": [0, 1, 2, 3, 4, 5],
        }
        identity_text = json.dumps(identity, indent=2, sort_keys=True) + "\n"
        identity_path = temporary / VERSION
        identity_path.write_text(identity_text, encoding="utf-8")
        identity_sha = digest(identity_text.encode())
        launcher = render_launcher(release_id, identity_sha, asset_list_sha)
        (temporary / "claude-renderpatch").write_text(launcher, encoding="utf-8")
        chmod_tree(temporary)
        temporary.rename(output)
    except BaseException:
        if temporary.exists():
            remove_tree(temporary)
        raise
    print(f"release={output}")
    print(f"release_id={release_id}")
    print(f"identity_sha256={identity_sha}")
    print(f"modules={len(modules)} assets={len(records)} semantic_ranges=8")


def verify_release(output: Path) -> None:
    if output.is_symlink() or not output.is_dir():
        raise ValueError(f"release root is unavailable or a symlink: {output}")
    identity = json.loads((output / VERSION).read_text(encoding="utf-8"))
    expected_identity = {
        "targetVersion": VERSION,
        "platform": "linux-x64",
        "bridgeBuildId": BRIDGE_BUILD_ID,
        "stockSha256": EXPECTED_STOCK_SHA256,
        "bunVersion": "1.4.0",
        "moduleCount": 1576,
        "extractedAssetCount": 1576,
        "semanticRanges": 8,
        "policyDomains": [0, 1, 2, 3, 4],
        "captureDomains": [0, 1, 2, 3, 4, 5],
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise ValueError(f"identity {key} mismatch: {identity.get(key)!r}")
    asset_list = output / "assets.sha256"
    if file_digest(asset_list) != identity.get("assetsListSha256"):
        raise ValueError("asset list identity mismatch")
    for line in asset_list.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = output / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"release asset is missing or a symlink: {relative}")
        if file_digest(path) != expected:
            raise ValueError(f"release asset SHA-256 mismatch: {relative}")
    expected_modes = {
        output: 0o555,
        output / "runtime/bun": 0o555,
        output / "claude-renderpatch": 0o555,
        output / VERSION: 0o444,
        output / "assets.sha256": 0o444,
        output / "bootstrap.mjs": 0o444,
        output / "extensions": 0o555,
        output / "extensions/_shared.mjs": 0o444,
        output / "extensions/default.mjs": 0o444,
    }
    for path, expected in expected_modes.items():
        actual = stat.S_IMODE(path.stat().st_mode)
        if actual != expected:
            raise ValueError(f"release mode mismatch: {path}: {oct(actual)}")
    markers = {
        MODULES["context"]: ["globalThis.__rpD0=", "globalThis.__rp?.q?.(3,n,P(X(e)))"],
        MODULES["reset"]: ["globalThis.__rp?.q?.(1,!1,o,l)"],
        MODULES["key_manager"]: ["__rp:[globalThis.__rpG="],
        MODULES["routing"]: ["globalThis.__rp?.q?.(4,PGn(n,t),n,t)", "globalThis.__rp?.c?.(0,0,4194303"],
        MODULES["key_lifecycle"]: ["globalThis.__rp?.c?.(5,n,511,r)", "globalThis.__rp?.c?.(5,t,0,null)"],
        MODULES["messages"]: ["globalThis.__rp?.q?.(0,0,a)", "Ve=W!=null&&!z&&!dc", "globalThis.__rp?.c?.(3,rp,65535", "globalThis.__rp?.c?.(3,rp,0,null)"],
        MODULES["repl"]: ["globalThis.__rp?.q?.(2,!1,r1!==\"transcript\")", "let pI=!1,", "return J}VIe();", "rpc(1,0,1089537", "rpc(2,rpg,31", "rpc(4,rpg,65535"],
    }
    for filename, expected_markers in markers.items():
        text = (output / "graph" / filename).read_text(encoding="utf-8")
        for marker in expected_markers:
            if text.count(marker) != 1:
                raise ValueError(f"semantic marker mismatch: {filename}: {marker}")
    shared_extension = (output / "extensions/_shared.mjs").read_text(encoding="utf-8")
    if "export function rendererToggleRedraw()" not in shared_extension or "return true" not in shared_extension:
        raise ValueError("authoritative toggle redraw policy is missing")
    status = subprocess.run(
        [str(output / "claude-renderpatch"), "--renderpatch-status"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "verification=ok" not in status or f"reported_version={VERSION} (Claude Code)" not in status:
        raise ValueError("release launcher status failed")
    print(status, end="")
    print("static_source_markers=8/8")
    print("asset_integrity=ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stock",
        type=Path,
        default=Path.home() / ".local/share/claude/versions" / VERSION,
    )
    parser.add_argument("--bun", type=Path, default=Path("/usr/bin/bun"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        output = args.output.expanduser().resolve()
        if args.verify:
            verify_release(output)
        else:
            build(args.stock.resolve(), args.bun, output, args.force)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"build-source-release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
