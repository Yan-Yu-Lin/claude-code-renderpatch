from __future__ import annotations

import itertools
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

VERSION = "2.1.220"
EXPECTED_STOCK_SHA256 = (
    "8addc857f3fe64d5a0368af9ee50321b50afb4a6918ba3ef018ab84f5dbbe081"
)
EXPECTED_FILE_SIZE = 256_908_272
BUN_OFFSET = 64_831_488
BUN_SIZE = 191_365_120
BUN_END = BUN_OFFSET + BUN_SIZE
OUTPUT_NAME = "claude-2.1.220-semantic-bridge-prototype"
REPLACEMENTS = Path(__file__).resolve().parent / "replacements" / VERSION


@dataclass(frozen=True)
class Patch:
    name: str
    old: bytes
    new: bytes
    offset: int

    @property
    def length(self) -> int:
        return len(self.old)

    @property
    def end(self) -> int:
        return self.offset + self.length


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _padded(old: bytes, replacement: bytes) -> bytes:
    if len(replacement) > len(old):
        raise ValueError(
            f"replacement grew: old={len(old)} replacement={len(replacement)}"
        )
    return replacement + b" " * (len(old) - len(replacement))


def _replacement(name: str) -> bytes:
    path = REPLACEMENTS / name
    if not path.is_file():
        raise ValueError(f"replacement asset missing: {path}")
    return path.read_bytes()


def _unique_region(data: bytes, start: bytes, end: bytes) -> tuple[int, bytes]:
    start_offsets: list[int] = []
    cursor = 0
    while True:
        offset = data.find(start, cursor)
        if offset < 0:
            break
        start_offsets.append(offset)
        cursor = offset + 1
    if len(start_offsets) != 1:
        raise ValueError(
            f"start anchor {start!r}: expected 1 match, found {len(start_offsets)}"
        )
    offset = start_offsets[0]
    end_offset = data.find(end, offset + len(start))
    if end_offset < 0:
        raise ValueError(f"end anchor {end!r}: no match after offset {offset}")
    if data.find(end, end_offset + 1) >= 0 and end.startswith(b"function"):
        # Function end anchors may recur elsewhere; the first following occurrence is
        # the semantic boundary paired with the unique start anchor.
        pass
    return offset, data[offset:end_offset]


def _replace_once(text: str, old: str, new: str, patch_name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(
            f"{patch_name}: expected one transformation anchor {old!r}, found {count}"
        )
    return text.replace(old, new, 1)


def _messages_patch(data: bytes) -> Patch:
    start = data.find(b"lzb=({")
    end = data.find(b",rgf,egf;var MAn", start)
    if start < 0 or end < 0:
        raise ValueError("renderer-messages-d3: complete lzb range missing")
    old = data[start:end]
    new = _padded(old, _replacement("messages-d3.js"))
    return Patch("renderer-messages-d3", old, new, start)


def _reset_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function CXr(", b"function wUu")
    text = old.decode("utf-8")
    replacements = [
        (
            "let s=n?0:Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1))",
            (
                "let s=(n||=!!rpQ(1,!1,t,n))?0:"
                "Math.min(o,Math.max(0,e.screen.height-e.viewport.height+1))"
            ),
        ),
        ("let i=o.none,s=void 0,a=-1", "let i=o.none,s,a=-1"),
        ("for(let f=r;f<n;f+=1)", "for(let f=r;f<n;f++)"),
        (
            (
                "e.txn((g)=>{let _=Array(1+m);_[0]=Ysr;for(let y=0;y<m;y++)"
                "_[1+y]=kho;return[_,{dx:-g.x,dy:m}]})"
            ),
            (
                "e.txn(g=>{let _=[Ysr];for(let y=0;y<m;y++)_.push(kho);"
                "return[_,{dx:-g.x,dy:m}]})"
            ),
        ),
        ("for(let m=0;m<l;m+=1,p+=1)", "for(let m=0;m<l;m++,p++)"),
        ("let _=g.hyperlink;s=eut(e.diff,s,_);", "s=eut(e.diff,s,g.hyperlink);"),
        (
            "if(wUu(e,g,y))i=g.styleId,a=g.styleId",
            "if(wUu(e,g,y))i=a=g.styleId",
        ),
    ]
    for before, after in replacements:
        text = _replace_once(text, before, after, "renderer-reset")
    new = _padded(old, text.encode("utf-8"))
    return Patch("renderer-reset", old, new, offset)


def _toggle_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function Hui(", b"var Wrl,b7f;")
    text = old.decode("utf-8")
    replacements = [
        (
            'if(!uvI()&&aHr&&Pui!=="transcript"){MCe(eFS);return}',
            'if(!uvI()&&aHr&&Pui!=="transcript")return MCe(eFS);',
        ),
        (
            "Jvt(!1)},NCe[6]=",
            (
                'Jvt(!1),Pui!=="transcript"&&rpQ(2,!1,!0)'
                "&&setTimeout(oFS,50)},NCe[6]="
            ),
        ),
        (
            "let N2S=()=>{if(cvI()){return}MCe(Z2S)};",
            "let N2S=()=>{if(!cvI())MCe(Z2S)};",
        ),
        (
            "if(!mvI()&&!aHr){return}let f7f=!aHr;",
            "if(!mvI()&&!aHr)return;let f7f=!aHr;",
        ),
        (
            (
                "MCe((m7f)=>{if(m7f.isBriefOnly===f7f){return m7f}"
                "return{...m7f,isBriefOnly:f7f}})"
            ),
            "MCe((m7f)=>m7f.isBriefOnly===f7f?m7f:{...m7f,isBriefOnly:f7f})",
        ),
        (
            ('U2S;if(NCe[26]===J)U2S={context:"Global"},NCe[26]=U2S;else U2S=NCe[26];'),
            'U2S=NCe[26];if(U2S===J)U2S=NCe[26]={context:"Global"};',
        ),
        (
            (
                'let q2S;if(NCe[27]===J)q2S={context:"Global"},NCe[27]=q2S;'
                "else q2S=NCe[27];"
            ),
            'let q2S=NCe[27];if(q2S===J)q2S=NCe[27]={context:"Global"};',
        ),
        (
            (
                'let j2S;if(NCe[28]===J)j2S={context:"Global"},NCe[28]=j2S;'
                "else j2S=NCe[28];"
            ),
            'let j2S=NCe[28];if(j2S===J)j2S=NCe[28]={context:"Global"};',
        ),
        (
            ('W2S;if(NCe[29]===J)W2S={context:"Global"},NCe[29]=W2S;else W2S=NCe[29];'),
            'W2S=NCe[29];if(W2S===J)W2S=NCe[29]={context:"Global"};',
        ),
        (
            ('G2S;if(NCe[30]===J)G2S={context:"Global"},NCe[30]=G2S;else G2S=NCe[30];'),
            'G2S=NCe[30];if(G2S===J)G2S=NCe[30]={context:"Global"};',
        ),
    ]
    for before, after in replacements:
        text = _replace_once(text, before, after, "renderer-toggle-redraw")
    new = _padded(old, text.encode("utf-8"))
    return Patch("renderer-toggle-redraw", old, new, offset)


def _context_patch(data: bytes) -> Patch:
    offset, old = _unique_region(
        data, b"function SZc(", b"var wZc,yer,bro,Bde,yYi,RZc;"
    )
    new = _padded(old, _replacement("context-and-capture-runtime.js"))
    return Patch("provider-context-window", old, new, offset)


def _routing_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function ite(", b"function Fze")
    new = _padded(old, _replacement("routing-and-d0.js"))
    return Patch("subagent-routing-static-d0", old, new, offset)


def _app_provider_patch(data: bytes) -> Patch:
    context = b"tt(xZs,{AppStateProvider:()=>dR});function dR("
    context_offset = data.find(context)
    if context_offset < 0 or data.find(context, context_offset + 1) >= 0:
        raise ValueError("app-provider-d2: contextual function anchor is not unique")
    offset = context_offset + context.index(b"function dR(")
    end = data.find(b"var CTp,z3,RYe,ATp,h6o;", offset)
    if end < 0:
        raise ValueError("app-provider-d2: function end anchor missing")
    old = data[offset:end]
    new = _padded(old, _replacement("provider-d2.js"))
    return Patch("app-provider-d2", old, new, offset)


def _repl_patch(data: bytes) -> Patch:
    start = data.find(b",$r=ds()&&!z,Gr=kr.useRef(null)")
    end = data.find(b"var TLe,mhi;var khl", start)
    if start < 0 or end < 0:
        raise ValueError("repl-render-d4-static-d1: supplier range missing")
    old = data[start:end]
    new = _padded(old, _replacement("repl-d4.js"))
    return Patch("repl-render-d4-static-d1", old, new, start)


def _key_provider_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function tQr(", b"function TE()")
    new = _padded(old, _replacement("key-provider-d5.js"))
    return Patch("key-provider-d5-payload", old, new, offset)


def _key_lifecycle_patch(data: bytes) -> Patch:
    start = data.find(b"function cZs(")
    end = data.find(b"function ", start + len(b"function cZs("))
    if start < 0 or end < 0:
        raise ValueError("key-provider-d5-lifecycle: supplier range missing")
    old = data[start:end]
    new = _padded(old, _replacement("key-child-d5.js"))
    return Patch("key-provider-d5-lifecycle", old, new, start)


def discover_patches(stock_data: bytes) -> list[Patch]:
    if len(stock_data) != EXPECTED_FILE_SIZE:
        raise ValueError(
            f"unexpected stock size: expected {EXPECTED_FILE_SIZE}, found {len(stock_data)}"
        )
    if digest(stock_data) != EXPECTED_STOCK_SHA256:
        raise ValueError(
            "unexpected stock SHA-256: expected "
            f"{EXPECTED_STOCK_SHA256}, found {digest(stock_data)}"
        )
    patches = [
        _context_patch(stock_data),
        _reset_patch(stock_data),
        _key_provider_patch(stock_data),
        _routing_patch(stock_data),
        _key_lifecycle_patch(stock_data),
        _app_provider_patch(stock_data),
        _messages_patch(stock_data),
        _toggle_patch(stock_data),
        _repl_patch(stock_data),
    ]
    patches.sort(key=lambda patch: patch.offset)
    for patch in patches:
        if len(patch.old) != len(patch.new):
            raise ValueError(
                f"{patch.name}: length mismatch old={len(patch.old)} new={len(patch.new)}"
            )
        if not (BUN_OFFSET <= patch.offset < patch.end <= BUN_END):
            raise ValueError(
                f"{patch.name}: range {patch.offset}:{patch.end} is outside live __BUN "
                f"range {BUN_OFFSET}:{BUN_END}"
            )
        old_count = stock_data.count(patch.old)
        new_count = stock_data.count(patch.new)
        if old_count != 1 or new_count != 0:
            raise ValueError(
                f"{patch.name}: expected old=1/new=0, found "
                f"old={old_count}/new={new_count}"
            )
    for left, right in itertools.pairwise(patches):
        if left.end > right.offset:
            raise ValueError(
                f"overlapping patches: {left.name} ends at {left.end}, "
                f"{right.name} starts at {right.offset}"
            )
    return patches


def apply_patches(stock_data: bytes, patches: list[Patch]) -> bytes:
    data = bytearray(stock_data)
    for patch in patches:
        current = bytes(data[patch.offset : patch.end])
        if current != patch.old:
            raise ValueError(f"{patch.name}: bytes changed before replacement")
        data[patch.offset : patch.end] = patch.new
        candidate = bytes(data)
        old_count = candidate.count(patch.old)
        new_count = candidate.count(patch.new)
        if old_count != 0 or new_count != 1:
            raise ValueError(
                f"{patch.name}: immediate post-check expected old=0/new=1, found "
                f"old={old_count}/new={new_count}"
            )
    result = bytes(data)
    if len(result) != len(stock_data):
        raise ValueError(
            f"binary length changed: stock={len(stock_data)} patched={len(result)}"
        )
    for patch in patches:
        if result.count(patch.old) != 0 or result.count(patch.new) != 1:
            raise ValueError(f"{patch.name}: final replacement invariant failed")
    return result
