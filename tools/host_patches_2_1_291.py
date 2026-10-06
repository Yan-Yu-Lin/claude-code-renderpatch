# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exact, fail-closed baked-in edits for the official 2.1.291 Darwin graph.

Host architecture: the patched graph runs inside the untouched official
executable, so there is no policy or capture ABI. The renderer behavior is
fixed to the retired default extension's values:

  renderer.messages      -> 2 | (screen === "transcript" ? 1 : 0)
  renderer.reset         -> destructive whenever the reset is not alt-screen
  renderer.toggleRedraw  -> always one authoritative redraw after Ctrl+O

Explicit tool-supplied model overrides bypass only the same-family shortcut.
Frontmatter/default/inherit and the upstream FORCE/environment precedence stay
unchanged. Both plain Agent and named-teammate collisions reproduce on stock.
"""


def patch_graph(texts):
    result = dict(texts)
    changed = {}

    def global_count(needle):
        return sum(text.count(needle) for text in result.values())

    def edit(name, changes, extra=""):
        if name not in result:
            raise ValueError(f"missing target chunk: {name}")
        text = result[name]
        for old, new in changes:
            old_count = global_count(old)
            if old_count != 1:
                raise ValueError(
                    f"expected one global anchor ({old_count}): {old[:160]}"
                )
            new_count = global_count(new)
            if new_count != 0:
                raise ValueError(
                    f"replacement already present globally ({new_count}): {new[:80]}"
                )
            if text.count(old) != 1:
                raise ValueError(f"global anchor is not in expected chunk {name}: {old[:160]}")
            text = text.replace(old, new, 1)
            result[name] = text
        if extra:
            extra_count = global_count(extra)
            if extra_count != 0:
                raise ValueError(
                    f"extra replacement already present globally ({extra_count}): {extra[:80]}"
                )
            text += "\n" + extra
            result[name] = text
        changed[name] = len(changes)

    # R1: never select the fullscreen alternate-screen renderer.
    edit(
        "chunk-m6m73xp1.js",
        [
            (
                'function Hc(e=iW){if(Wu()==="local-agent")return!1;',
                'function Hc(e=iW){return!1;if(Wu()==="local-agent")return!1;',
            ),
        ],
    )
    # R2: the React hook and compiler memo still run, but the split resolver
    # always returns inline mode.
    edit(
        "chunk-vc97qmvg.js",
        [
            (
                "function N1n(o){if(o===null)return xe();",
                'function N1n(o){return"inline";if(o===null)return xe();',
            ),
        ],
    )
    # R3 + R4: no DECSTBM scroll-region renderer; every main-screen full reset
    # replays from row zero, advances the reset epoch, and is serialized as a
    # destructive replay (ED2 + ED3 + home).
    edit(
        "chunk-047zrb4c.js",
        [
            (
                "function D6(){let n=bo();if(n.decstbmRendererEnabled!==void 0)return n.decstbmRendererEnabled;",
                "function D6(){return!1;let n=bo();if(n.decstbmRendererEnabled!==void 0)return n.decstbmRendererEnabled;",
            ),
            (
                "function Wl(n,u,f,m,y,g){let S=m?0:Math.min(y,Math.max(0,n.screen.height-n.viewport.height+1)),",
                "function Wl(n,u,f,m,y,g){let rp=!m;if(rp)globalThis.__rpResetEpoch=(globalThis.__rpResetEpoch??0)+1;let S=m||rp?0:Math.min(y,Math.max(0,n.screen.height-n.viewport.height+1)),",
            ),
            (
                'type:"clearTerminal",reason:u,altScreen:m,viewportRows:n.viewport.height,debug:g',
                'type:"clearTerminal",reason:u,altScreen:m,destructiveReplay:rp,viewportRows:n.viewport.height,debug:g',
            ),
        ],
    )
    # R5: a destructive replay serializes like the alt-screen full clear.
    edit(
        "chunk-na5bb0t0.js",
        [
            (
                'case"clearTerminal":d+=c.altScreen?Iwo():gtn(c.viewportRows);',
                'case"clearTerminal":d+=c.altScreen||c.destructiveReplay?Iwo():gtn(c.viewportRows);',
            ),
        ],
    )
    # R6-R8: messages are uncapped and unvirtualized; the transcript shows all.
    # The existing compiler memo dependency slots still include these flags.
    edit(
        "chunk-03vmca9k.js",
        [
            (
                '_e=M!==void 0,O=M==="uncapped"||Se!==void 0,Fe=hI(qa),',
                '_e=M!==void 0,O=!0,Fe=hI(qa),',
            ),
            (
                "oo=V(qI),xo=null,lt=oe!=null&&!gt,ne=zb(ze,te),re;",
                "oo=V(qI),xo=null,lt=!1,ne=zb(ze,te),re;",
            ),
            (
                "let Gn=Fs,zn=X&&!_e&&!lt,No;",
                "let Gn=Fs,zn=!1,No;",
            ),
        ],
    )
    # R9: after Ctrl+O request one authoritative redraw, unless the renderer
    # already performed a full reset since the toggle (avoids a double repaint).
    edit(
        "chunk-scapxbwa.js",
        [
            (
                "M()},Ne[6]=Oe,Ne[7]=je,",
                "__rpToggle(M)},Ne[6]=Oe,Ne[7]=je,",
            ),
        ],
        "function __rpToggle(callback){const epoch=globalThis.__rpResetEpoch??0;callback();setTimeout(()=>{if((globalThis.__rpResetEpoch??0)===epoch)Pmt()},50)}",
    )
    # S1: explicit plain Agent override; retain the later frontmatter shortcut.
    edit(
        "chunk-g2d84gj0.js",
        [
            (
                'if(n==="inherit")return h();if(Tzn(n,s))return s;',
                'if(n==="inherit")return h();if(!1&&Tzn(n,s))return s;',
            ),
        ],
    )
    # S2: source is already tracked by every teammate backend. Pass it into
    # resolution; bypass the collision only for a tool-supplied override.
    # FORCE clears e before this branch, preserving upstream precedence.
    edit(
        "chunk-az8vv0m7.js",
        [
            (
                "function re(e,n){if(a.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;",
                "function re(e,n,rpSource){if(a.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;",
            ),
            (
                "if(e!==void 0){if(!zr(e))return Z(e,n);if(n!==null&&Tzn(e,n))return n;return e}",
                'if(e!==void 0){if(!zr(e))return Z(e,n);if(rpSource!=="tool"&&n!==null&&Tzn(e,n))return n;return e}',
            ),
            (
                'function W(e,n,r="tool"){if(a.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;let s=re(e,n),',
                'function W(e,n,r="tool"){if(a.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;let s=re(e,n,r),',
            ),
        ],
    )
    return result, changed
