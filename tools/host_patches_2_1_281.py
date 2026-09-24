# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exact, fail-closed baked-in edits for the official 2.1.281 Darwin graph.

Host architecture: the patched graph runs inside the untouched official
executable, so there is no policy or capture ABI. Every former policy is a
constant equal to what the retired default extension returned:

  renderer.messages      -> 2 | (screen === "transcript" ? 1 : 0)
  renderer.reset         -> destructive whenever the reset is not alt-screen
  renderer.toggleRedraw  -> always one authoritative redraw after Ctrl+O
  explicitModelRouting   -> the same-family shortcut never skips an explicit
                            tool-supplied model

The Bash helper execPath edit of the source bridge is unnecessary here:
process.execPath is the official executable, which carries ugrep and bfs.
"""


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
        if extra:
            text += "\n" + extra
        result[name] = text
        changed[name] = len(changes)

    # R1: never select the fullscreen alternate-screen renderer.
    edit("chunk-5msfmr7e.js", [("function rl(e=N$){", "function rl(e=N$){return!1;")])
    # R2: the latched renderer mode is always inline.
    edit(
        "chunk-hkhfvq8c.js",
        # The context hook still runs first so React hook order is unchanged.
        [("function $O(){let o=Ie(re);", 'function $O(){let o=Ie(re);return"inline";')],
    )
    # R3 + R4: no DECSTBM scroll-region renderer; every main-screen full reset
    # replays from row zero and is serialized destructively (ED2+ED3+home).
    edit(
        "chunk-vnnj4fsp.js",
        [
            ("function Qle(){", "function Qle(){return!1;"),
            (
                "function Xr(n,d,f,m,y,g){let C=m?0:",
                "function Xr(n,d,f,m,y,g){let rp=!m;if(rp)globalThis.__rpResetEpoch=(globalThis.__rpResetEpoch??0)+1;let C=m||rp?0:",
            ),
            (
                'type:"clearTerminal",reason:d,altScreen:m,viewportRows:n.viewport.height,debug:g',
                'type:"clearTerminal",reason:d,altScreen:m,destructiveReplay:rp,viewportRows:n.viewport.height,debug:g',
            ),
        ],
    )
    # R5: a destructive replay serializes like the alt-screen full clear.
    edit(
        "chunk-35z18qft.js",
        [
            (
                'case"clearTerminal":i+=d.altScreen?Z6r():e2t(d.viewportRows);',
                'case"clearTerminal":i+=d.altScreen||d.destructiveReplay?Z6r():e2t(d.viewportRows);',
            ),
        ],
    )
    # R6-R8: messages are uncapped and unvirtualized; the transcript shows all.
    # Every flag is already a memo dependency, so no cache slot changes.
    edit(
        "chunk-rsmxg7f6.js",
        [
            (
                'fe=v!==void 0,D=v==="uncapped"||de!==void 0,',
                'fe=v!==void 0,D=!0,',
            ),
            ("Ke=ee!=null&&!qe,", "Ke=!1,"),
            ("Bo=q&&!fe&&!Ke,", "Bo=!1,"),
        ],
    )
    # R9: after Ctrl+O request one authoritative redraw, unless the renderer
    # already performed a full reset since the toggle (avoids a double repaint).
    edit(
        "chunk-dkd7nfng.js",
        [("D()},Me[6]=Pe", "__rpToggle(D)},Me[6]=Pe")],
        "function __rpToggle(callback){const epoch=globalThis.__rpResetEpoch??0;callback();setTimeout(()=>{if((globalThis.__rpResetEpoch??0)===epoch)hrt()},50)}",
    )
    # S1: explicit Agent-tool model override is honored; frontmatter call stock.
    edit(
        "chunk-5mg9g7ss.js",
        [
            (
                'if(n==="inherit")return _();if(Rwn(n,r))return r;',
                'if(n==="inherit")return _();if(!1&&Rwn(n,r))return r;',
            ),
        ],
    )
    # S2: named-teammate spawn; only a tool-supplied model is an explicit override.
    edit(
        "chunk-ehps9anq.js",
        [
            ("function se(n,e){", "function se(n,e,rpTool){"),
            (
                "if(e!==null&&Rwn(n,e))return e;",
                "if(!rpTool&&e!==null&&Rwn(n,e))return e;",
            ),
            ("let s=se(n,e),", 'let s=se(n,e,o==="tool"),'),
        ],
    )
    return result, changed
