# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exact, fail-closed baked-in edits for the official 2.1.318 Darwin graph.

Host architecture: the patched graph runs inside the untouched official
executable, so there is no policy or capture ABI. The renderer behavior is
fixed to the retired default extension's values:

  renderer.messages      -> 2 | (screen === "transcript" ? 1 : 0)
  renderer.reset         -> destructive whenever the reset is not alt-screen
  renderer.toggleRedraw  -> always one authoritative redraw after Ctrl+O

Explicit tool-supplied model overrides bypass only the same-family shortcut.
Frontmatter/default/inherit and the upstream FORCE/environment precedence stay
unchanged. Both plain Agent and named-teammate collision paths remain distinct.
"""


def patch_graph(texts, extra=None):
    result = dict(texts)
    changed = {}

    def global_count(needle):
        return sum(text.count(needle) for text in result.values())

    def assert_applied(old, new, name):
        old_count = global_count(old)
        new_count = global_count(new)
        if old_count != 0 or new_count != 1:
            raise ValueError(
                f"postcondition failed for {name}: old={old_count}, new={new_count}: "
                f"{old[:120]}"
            )
        if result[name].count(new) != 1:
            raise ValueError(f"replacement is not unique in expected chunk {name}: {new[:160]}")

    def edit(name, changes, extra=""):
        if name not in result:
            raise ValueError(f"missing target chunk: {name}")
        text = result[name]
        for old, new in changes:
            if old == new:
                raise ValueError(f"no-op replacement in {name}: {old[:160]}")
            if old in new:
                raise ValueError(
                    f"old anchor is a substring of its replacement in {name}: {old[:160]}"
                )
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
            assert_applied(old, new, name)
        if extra:
            extra_count = global_count(extra)
            if extra_count != 0:
                raise ValueError(
                    f"extra replacement already present globally ({extra_count}): {extra[:80]}"
                )
            text += "\n" + extra
            result[name] = text
            if global_count(extra) != 1 or result[name].count(extra) != 1:
                raise ValueError(f"extra postcondition failed for {name}: {extra[:160]}")
        changed[name] = changed.get(name, 0) + len(changes)

    # R1: never select the fullscreen alternate-screen renderer.
    edit(
        "chunk-3df33mkc.js",
        [
            (
                'function Nd(e=j8){if(Gu()==="local-agent")return!1;',
                'function Nd(e=j8){return!1;if(Gu()==="local-agent")return!1;',
            ),
        ],
    )
    # R2: the React context hook and compiler memo still run, but the split
    # presentation resolver always returns inline mode.
    edit(
        "chunk-v5qk8x3w.js",
        [
            (
                "function i1r(o){if(o===null)return xe();",
                'function i1r(o){return"inline";if(o===null)return xe();',
            ),
        ],
    )
    # R3 + R4: no DECSTBM scroll-region renderer; every main-screen full reset
    # replays from row zero, advances the reset epoch, and is serialized as a
    # destructive replay (ED2 + ED3 + home).
    edit(
        "chunk-qfycx4yg.js",
        [
            (
                "function fj(){let n=ro();if(n.decstbmRendererEnabled!==void 0)return n.decstbmRendererEnabled;",
                "function fj(){return!1;let n=ro();if(n.decstbmRendererEnabled!==void 0)return n.decstbmRendererEnabled;",
            ),
            (
                "function Ol(n,u,c,h,m,g){let E=h?0:Math.min(m,Math.max(0,n.screen.height-n.viewport.height+1)),",
                "function Ol(n,u,c,h,m,g){let rp=!h;if(rp)globalThis.__rpResetEpoch=(globalThis.__rpResetEpoch??0)+1;let E=h||rp?0:Math.min(m,Math.max(0,n.screen.height-n.viewport.height+1)),",
            ),
            (
                'type:"clearTerminal",reason:u,altScreen:h,viewportRows:n.viewport.height,debug:g',
                'type:"clearTerminal",reason:u,altScreen:h,destructiveReplay:rp,viewportRows:n.viewport.height,debug:g',
            ),
        ],
    )
    # R5: a destructive replay serializes like the alt-screen full clear.
    edit(
        "chunk-8n1d4f6t.js",
        [
            (
                'case"clearTerminal":d+=c.altScreen?JVs():Wwt(c.viewportRows);',
                'case"clearTerminal":d+=c.altScreen||c.destructiveReplay?JVs():Wwt(c.viewportRows);',
            ),
        ],
    )
    # R6-R8: messages are uncapped and unvirtualized; the transcript shows all.
    # Existing React compiler memo dependencies and cache indices stay intact.
    edit(
        "chunk-2388he8y.js",
        [
            (
                'Ce=H!==void 0,ee=H==="uncapped"||we!==void 0,ke=SE(Rc),',
                'Ce=H!==void 0,ee=!0,ke=SE(Rc),',
            ),
            (
                "me=null,ce=Re!=null&&!bt,Be=ev(Wt,oe),lt;",
                "me=null,ce=!1,Be=ev(Wt,oe),lt;",
            ),
            (
                "let gn=Yn,Jo=he&&!Ce&&!ce,Xn;",
                "let gn=Yn,Jo=!1,Xn;",
            ),
        ],
    )
    # R9: after Ctrl+O request one authoritative redraw, unless the renderer
    # already performed a full reset since the toggle (avoids a double repaint).
    edit(
        "chunk-p2q3ejfg.js",
        [
            (
                "O()},qe[6]=je,qe[7]=st,",
                "__rpToggle(O)},qe[6]=je,qe[7]=st,",
            ),
        ],
        "function __rpToggle(callback){const epoch=globalThis.__rpResetEpoch??0;callback();setTimeout(()=>{if((globalThis.__rpResetEpoch??0)===epoch)TLt()},50)}",
    )
    # S1: explicit plain Agent override; retain the later frontmatter shortcut.
    edit(
        "chunk-0x9x817t.js",
        [
            (
                'if(r==="inherit")return b();if(z8r(r,n))return n;',
                'if(r==="inherit")return b();if(!1&&z8r(r,n))return n;',
            ),
        ],
    )
    # S2: source is already tracked by every teammate backend. Pass it into
    # resolution; bypass the collision only for a tool-supplied override.
    # FORCE clears e before this branch, preserving upstream precedence.
    edit(
        "chunk-0h62541d.js",
        [
            (
                "function ne(e,n){if(i.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;",
                "function ne(e,n,rpSource){if(i.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;",
            ),
            (
                "if(e!==void 0){if(!Eo(e))return K(e,n);if(n!==null&&z8r(e,n))return n;return e}",
                'if(e!==void 0){if(!Eo(e))return K(e,n);if(rpSource!=="tool"&&n!==null&&z8r(e,n))return n;return e}',
            ),
            (
                'function W(e,n,o="tool"){if(i.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;let w=ne(e,n),',
                'function W(e,n,o="tool"){if(i.CLAUDE_CODE_SUBAGENT_MODEL_FORCE)e=void 0;let w=ne(e,n,o),',
            ),
        ],
    )
    # Optional additional fail-closed edit sets share this edit function and its
    # global before/after uniqueness checks.
    if extra is not None:
        extra(result, edit)
    # Each edit checks global pre/postconditions immediately. Later recipe
    # layers may intentionally refine an earlier layer's replacement text.
    return result, changed
