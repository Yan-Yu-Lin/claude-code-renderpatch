# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exact, fail-closed semantic edits for the official 2.1.281 Darwin graph.

Renderer-only port. Unlike 2.1.261 this recipe publishes no raw capture
domains: the REPL memo-cache edits existed only for d1/d2/d4 capture and the
lifted show-all state, and nothing in the installed bridge consumes them.
The provider context-window policy is gone; the settings overlay supplies
CLAUDE_CODE_MAX_CONTEXT_TOKENS instead.
"""

QUERY = "function __rpQ281(id,fallback,...args){try{return globalThis.__rp?.q?.(id,fallback,...args)??fallback}catch{return fallback}}\n"


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"expected one anchor ({text.count(old)}): {old[:160]}")
    if new in text:
        raise ValueError(f"replacement already present: {new[:80]}")
    return text.replace(old, new, 1)


def patch_graph(texts):
    result = dict(texts)
    changed = {}

    def edit(name, changes, extra=""):
        text = result[name]
        for old, new in changes:
            text = replace(text, old, new)
        if "__rpQ281" in text or "__rpQ281" in extra:
            text += "\n" + QUERY
        text += "\n" + extra
        result[name] = text
        changed[name] = len(changes)

    # R1: canonical fullscreen decision. Policy 0 bit 2 keeps the classic
    # renderer; absent preload the stock selector runs unchanged.
    edit(
        "chunk-5msfmr7e.js",
        [
            (
                "function rl(e=N$){",
                'function rl(e=N$){if(__rpQ281(0,0,"prompt")&2)return!1;',
            ),
        ],
    )
    # R2: the latched inline/fullscreen context value.
    edit(
        "chunk-hkhfvq8c.js",
        [
            (
                "function $O(){let o=Ie(re);",
                'function $O(){let o=Ie(re);if(__rpQ281(0,0,"prompt")&2)return"inline";',
            ),
        ],
    )
    # R3 + R4: DECSTBM scroll-region renderer off; full resets replay from row
    # zero and mark themselves destructive when policy 1 accepts the reason.
    edit(
        "chunk-vnnj4fsp.js",
        [
            ("function Qle(){", 'function Qle(){if(__rpQ281(0,0,"prompt")&2)return!1;'),
            (
                "function Xr(n,d,f,m,y,g){let C=m?0:",
                "function Xr(n,d,f,m,y,g){let rp=__rpQ281(1,!1,d,m);if(rp)globalThis.__rpResetEpoch281=(globalThis.__rpResetEpoch281??0)+1;let C=m||rp?0:",
            ),
            (
                'type:"clearTerminal",reason:d,altScreen:m,viewportRows:n.viewport.height,debug:g',
                'type:"clearTerminal",reason:d,altScreen:m,destructiveReplay:rp,viewportRows:n.viewport.height,debug:g',
            ),
        ],
    )
    # R5: a destructive replay serializes as ED2+ED3+home like the alt screen.
    edit(
        "chunk-35z18qft.js",
        [
            (
                'case"clearTerminal":i+=d.altScreen?Z6r():e2t(d.viewportRows);',
                'case"clearTerminal":i+=d.altScreen||d.destructiveReplay?Z6r():e2t(d.viewportRows);',
            ),
        ],
    )
    # R6-R8: Messages. Bit 2 uncaps both cap computations and disables
    # virtualization; bit 1 disables the transcript tail truncation (show all).
    # All three flags are already memo dependencies, so no cache slot changes.
    edit(
        "chunk-rsmxg7f6.js",
        [
            (
                'fe=v!==void 0,D=v==="uncapped"||de!==void 0,',
                'fe=v!==void 0,rpPolicy281=__rpQ281(0,0,b),D=v==="uncapped"||de!==void 0||!!(rpPolicy281&2),',
            ),
            ("Ke=ee!=null&&!qe,", "Ke=ee!=null&&!qe&&!(rpPolicy281&2),"),
            ("Bo=q&&!fe&&!Ke,", "Bo=q&&!fe&&!Ke&&!(rpPolicy281&1),"),
        ],
    )
    # R9: after Ctrl+O, request one authoritative redraw unless the renderer
    # already performed a destructive reset since the toggle.
    toggle = "function __rpToggle281(callback,entering){const epoch=globalThis.__rpResetEpoch281??0;callback();if(__rpQ281(2,!1,entering))setTimeout(()=>{if((globalThis.__rpResetEpoch281??0)===epoch)hrt()},50)}\n"
    edit(
        "chunk-dkd7nfng.js",
        [("D()},Me[6]=Pe", '__rpToggle281(D,v!=="transcript")},Me[6]=Pe')],
        toggle,
    )
    # B1: the split Bun runtime has no embedded ugrep/bfs. Only the Bash tool's
    # helper target uses native stock Claude from the install bin directory.
    edit(
        "chunk-h3bc7dkc.js",
        [
            (
                "G[l_e]=process.execPath",
                'G[l_e]=__rpJoin281(__rpBinDir281(),H()==="windows"?"claude.exe":"claude")',
            ),
        ],
        'import{Y2 as __rpBinDir281}from"./chunk-8bc0vvxx.js";\nimport{join as __rpJoin281}from"path";',
    )
    # S1: explicit Agent-tool model override; frontmatter call left stock.
    edit(
        "chunk-5mg9g7ss.js",
        [
            (
                'if(n==="inherit")return _();if(Rwn(n,r))return r;',
                'if(n==="inherit")return _();if(__rpQ281(4,Rwn(n,r),n,r))return r;',
            ),
        ],
    )
    # S2: named-teammate spawn. Only a tool-supplied model is an explicit
    # override; frontmatter/default teammate models keep stock semantics.
    edit(
        "chunk-ehps9anq.js",
        [
            ("function se(n,e){", "function se(n,e,rpTool){"),
            (
                "if(e!==null&&Rwn(n,e))return e;",
                "if(e!==null&&(rpTool?__rpQ281(4,Rwn(n,e),n,e):Rwn(n,e)))return e;",
            ),
            ("let s=se(n,e),", 'let s=se(n,e,o==="tool"),'),
        ],
    )
    return result, changed
