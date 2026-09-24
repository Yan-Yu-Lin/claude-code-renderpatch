# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Exact, fail-closed semantic edits for the official 2.1.261 Darwin graph."""

QUERY = "function __rpQ261(id,fallback,...args){try{return globalThis.__rp?.q?.(id,fallback,...args)??fallback}catch{return fallback}}\n"
CAPTURE = "function __rpC261(...args){try{globalThis.__rp?.c?.(...args)}catch{}}\n"


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
        original = result[name]
        text = original
        for old, new in changes:
            text = replace(text, old, new)
        if "__rpQ261" in text or "__rpQ261" in extra:
            text += "\n" + QUERY
        if "__rpC261" in text or "__rpC261" in extra:
            text += "\n" + CAPTURE
        text += "\n" + extra
        result[name] = text
        changed[name] = len(changes)

    # Wrap the complete resolver so every upstream early return retains its
    # meaning before the provider policy is consulted.
    edit(
        "chunk-7s5z3cw5.js",
        [
            (
                "function QL(e,t){",
                "function QL(e,t){return __rpQ261(3,__rpRawWindow261(e,t),Ue(bt(e)))}function __rpRawWindow261(e,t){",
            ),
        ],
        "globalThis.__rpModel261=[rt,bt,Rr,Ue,Tl,Qa,vp,QL,tc,_g,GC,JL,ivn,sCt,m5];",
    )
    edit(
        "chunk-3963bmck.js",
        [
            (
                'if(r==="inherit")return p();if(ojt(r,t))return t;',
                'if(r==="inherit")return p();if(__rpQ261(4,ojt(r,t),r,t))return t;',
            ),
            # The split Bun runtime has no embedded ugrep/bfs. Only the Bash
            # tool's helper target uses stock Claude; app spawning stays on Bun.
            (
                "D[HJe]=process.execPath",
                'D[HJe]=jAe(SD(),P()==="windows"?"claude.exe":"claude")',
            ),
        ],
        "try{__rpC261(0,0,4194303,[...globalThis.__rpModel261,cH,PDn,olt,ojt,vV,(e)=>JJ(e,Ue(e)),oDo])}finally{delete globalThis.__rpModel261}",
    )

    # Query full-frame policy at the canonical mode selector. No environment
    # settings are changed; absent preload leaves the stock selector intact.
    edit(
        "chunk-w7y6dfep.js",
        [
            (
                "function Ta(e=KI){",
                'function Ta(e=KI){if(__rpQ261(0,0,"prompt")&2)return!1;',
            ),
        ],
    )
    edit(
        "chunk-9wy4tdk8.js",
        [
            (
                "function oO(){let r=De(de);",
                'function oO(){let r=De(de);if(__rpQ261(0,0,"prompt")&2)return"inline";',
            ),
        ],
        "globalThis.__rpRender261=[S9e,(stdout=process.stdout)=>ws().get(stdout),Y0,he];",
    )
    edit(
        "chunk-q5rezcap.js",
        [
            (
                "function Za(t,s,c,f,m,y){let b=f?0:",
                "function Za(t,s,c,f,m,y){let rp=__rpQ261(1,!1,s,f);if(rp)globalThis.__rpResetEpoch261=(globalThis.__rpResetEpoch261??0)+1;let b=f||rp?0:",
            ),
            (
                'type:"clearTerminal",reason:s,altScreen:f,viewportRows:t.viewport.height,debug:y',
                'type:"clearTerminal",reason:s,altScreen:f,destructiveReplay:rp,viewportRows:t.viewport.height,debug:y',
            ),
            ("function iee(){", 'function iee(){if(__rpQ261(0,0,"prompt")&2)return!1;'),
        ],
        "globalThis.__rpInk261=[Xye,Yd,Za,ng,Kd];",
    )
    edit(
        "chunk-rvxxpz38.js",
        [
            (
                "i+=l.altScreen?JUn():Lat(l.viewportRows);",
                "i+=l.altScreen||l.destructiveReplay?JUn():Lat(l.viewportRows);",
            ),
        ],
        "globalThis.__rpTerminal261=[Dtn,JUn,Lat];",
    )

    # The sentinel is a separate React component: original components retain
    # their hook count and order. Each generation gets a matching cleanup.
    cleanup = "function __rpCleanup261({generation,domains}){E(()=>()=>{for(const id of domains)__rpC261(id,generation,0,null)},[generation]);return null}\n"
    repl_wrapper = "function m5e(props){const state=d(!1);return e(__rpRepl261,{...props,__rpShowAll:state})}\n"
    toggle = "function __rpToggle261(callback,entering){const epoch=globalThis.__rpResetEpoch261??0;callback();if(__rpQ261(2,!1,entering))setTimeout(()=>{if((globalThis.__rpResetEpoch261??0)===epoch)F5t()},50)}\n"
    edit(
        "chunk-5vxbh0wn.js",
        [
            (
                'ZM=iQt==="uncapped"||Ok!==void 0,',
                'rpPolicy261=__rpQ261(0,0,fhe),ZM=iQt==="uncapped"||Ok!==void 0||!!(rpPolicy261&2),',
            ),
            ("$x=hhe!=null&&!ain,", "$x=hhe!=null&&!ain&&!(rpPolicy261&2),"),
            ("_he=om&&!yhe&&!$x,", "_he=om&&!yhe&&!$x&&!(rpPolicy261&1),"),
            (
                "return nYt}function d7(w)",
                "let rpg=globalThis.__rpG=(globalThis.__rpG??0)+1;__rpC261(3,rpg,65535,[k0,Jb,Rhe,Mhe,Hw,khe,CU.preCap,CU.slice,D9e,_U,$x,FK,fhe,yhe||!!(rpPolicy261&1),ZM,Ok]);return r(N,{children:[e(__rpCleanup261,{generation:rpg,domains:[3]}),nYt]})}function d7(w)",
            ),
            ("X7e()},lA[6]=nZe", '__rpToggle261(X7e,rye!=="transcript")},lA[6]=nZe'),
            (
                "function m5e(Bwi){let ls=_(596),",
                "function __rpRepl261(Bwi){let ls=_(597),[rpa,rps]=Bwi.__rpShowAll,",
            ),
            (
                "[rcn,icn]=d(!1),M_=rcn||$w,",
                "[rpLocal,rpSetLocal]=d(!1),rcn=ncn.__rpShowAll?.[0]??rpLocal,icn=ncn.__rpShowAll?.[1]??rpSetLocal,M_=rcn||$w,",
            ),
            ("let e0;if(ls[472]!==y4", "let e0;if(ls[596]!==rpa||ls[472]!==y4"),
            ("e0=e(_7,{focused:hm,", "e0=e(_7,{__rpShowAll:[rpa,rps],focused:hm,"),
            ("ls[483]=KYe,ls[484]=e0;", "ls[483]=KYe,ls[484]=e0,ls[596]=rpa;"),
            (
                'let zYe=HVo;if(fm==="transcript")',
                ('let zYe=HVo,rpg=globalThis.__rpG=(globalThis.__rpG??0)+1,rpt={onToggleTranscript:()=>{JWo(v=>v==="transcript"?"prompt":"transcript");rps(!1)},redraw:F5t};'
                "if(!globalThis.__rpStatic261){globalThis.__rpStatic261=!0;let ink=globalThis.__rpInk261,term=globalThis.__rpTerminal261,render=globalThis.__rpRender261;__rpC261(1,0,3194879,[ws(),...ink,...term,...render,jb,,n,,,,,i,__rpTelemetryAsync261]);delete globalThis.__rpInk261;delete globalThis.__rpTerminal261;delete globalThis.__rpRender261}"
                "__rpC261(2,rpg,63,[$a,jb,$a.getState,Sc,$a.subscribe,__rpDefaultState261]);"
                "__rpC261(4,rpg,65535,[$a,Sc,hm,fm,JWo,rpa,rps,EYe,XWo,y4,Ji.submitIncomingPrompt,zD,$a.getState().agentDefinitions,Vu.viewport,null,rpt]);"
                'if(fm==="transcript")'),
            ),
            (
                "return j4}let DV=",
                "return r(N,{children:[e(__rpCleanup261,{generation:rpg,domains:[2,4]}),j4]})}let DV=",
            ),
            (
                "return WVo}\nexport{",
                "return r(N,{children:[e(__rpCleanup261,{generation:rpg,domains:[2,4]}),WVo]})}\nexport{",
            ),
        ],
        cleanup
        + repl_wrapper
        + toggle
        + 'import{iF as __rpDefaultState261}from"./chunk-sdfqx0j1.js";\nimport{qs as __rpTelemetryAsync261}from"./chunk-bam8cfq8.js";',
    )

    # Capture the assembled key manager without altering the original provider's
    # hooks. The returned child owns cleanup for this provider generation.
    edit(
        "chunk-3nf3qbb9.js",
        [
            (
                "return I}function sl(){",
                "let rpg=globalThis.__rpG=(globalThis.__rpG??0)+1;__rpC261(5,rpg,511,[L,a,T,K,j,E,P,H,N]);return e(__rpKeyCleanup261,{generation:rpg,children:I})}function sl(){",
            ),
        ],
        "function __rpKeyCleanup261({generation,children}){dn(()=>()=>__rpC261(5,generation,0,null),[generation]);return children}",
    )
    return result, changed
