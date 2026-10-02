# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exact, fail-closed baked-in edits for the official 2.1.287 Darwin graph.

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
    edit("chunk-qravq5t1.js", [("function Sc(e=x2){", "function Sc(e=x2){return!1;")])
    # R2: the latched renderer mode is always inline.
    edit(
        "chunk-jkt292h5.js",
        # The context hook still runs first so React hook order is unchanged.
        [("function IO(){let o=ke(oe);", 'function IO(){let o=ke(oe);return"inline";')],
    )
    # R3 + R4: no DECSTBM scroll-region renderer; every main-screen full reset
    # replays from row zero and is serialized destructively (ED2+ED3+home).
    edit(
        "chunk-p50qybax.js",
        [
            (
                "function WW(){{let n=ko();",
                "function WW(){return!1;{let n=ko();",
            ),
            (
                "function Ir(n,u,f,m,y,g){let C=m?0:",
                "function Ir(n,u,f,m,y,g){let rp=!m;if(rp)globalThis.__rpResetEpoch=(globalThis.__rpResetEpoch??0)+1;let C=m||rp?0:",
            ),
            (
                'type:"clearTerminal",reason:u,altScreen:m,viewportRows:n.viewport.height,debug:g',
                'type:"clearTerminal",reason:u,altScreen:m,destructiveReplay:rp,viewportRows:n.viewport.height,debug:g',
            ),
        ],
    )
    # R5: a destructive replay serializes like the alt-screen full clear.
    edit(
        "chunk-nzck9a32.js",
        [
            (
                'case"clearTerminal":d+=c.altScreen?Lco():cYt(c.viewportRows);',
                'case"clearTerminal":d+=c.altScreen||c.destructiveReplay?Lco():cYt(c.viewportRows);',
            ),
        ],
    )
    # R6-R8: messages are uncapped and unvirtualized; the transcript shows all.
    # Every flag is already a memo dependency, so no cache slot changes.
    edit(
        "chunk-1ypw9bby.js",
        [
            (
                'Ce=_!==void 0,W=_==="uncapped"||be!==void 0,',
                'Ce=_!==void 0,W=!0,',
            ),
            ("st=se!=null&&!gt,", "st=!1,"),
            ("Cs=ne&&!Ce&&!st,", "Cs=!1,"),
        ],
    )
    # R9: after Ctrl+O request one authoritative redraw, unless the renderer
    # already performed a full reset since the toggle (avoids a double repaint).
    edit(
        "chunk-f2cpzzp9.js",
        [("D()},Oe[6]=Ie", "__rpToggle(D)},Oe[6]=Ie")],
        "function __rpToggle(callback){const epoch=globalThis.__rpResetEpoch??0;callback();setTimeout(()=>{if((globalThis.__rpResetEpoch??0)===epoch)ddt()},50)}",
    )
    # S1: explicit Agent-tool model override is honored; frontmatter call stock.
    edit(
        "chunk-5ne43w2c.js",
        [
            (
                'if(n==="inherit")return h();if(LLn(n,s))return s;',
                'if(n==="inherit")return h();if(!1&&LLn(n,s))return s;',
            ),
        ],
    )
    # S2: named-teammate spawn; only a tool-supplied model is an explicit override.
    edit(
        "chunk-fkttf1dq.js",
        [
            ("function se(n,e){", "function se(n,e,rpTool){"),
            (
                "if(e!==null&&LLn(n,e))return e;",
                "if(!rpTool&&e!==null&&LLn(n,e))return e;",
            ),
            ("let s=se(n,e),", 'let s=se(n,e,o==="tool"),'),
        ],
    )
    return result, changed
