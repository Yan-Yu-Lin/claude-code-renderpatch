from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

VERSION = "2.1.226"
EXPECTED_STOCK_SHA256 = (
    "013a1cf17df5ff1dcc189d5d6fd3fdd5f097ddc3cd41aa9992e99805574febbe"
)
EXPECTED_FILE_SIZE = 279_661_952
BUN_OFFSET = 65_306_624
BUN_SIZE = 213_598_208
BUN_END = BUN_OFFSET + BUN_SIZE
OUTPUT_NAME = "claude-2.1.226-semantic-bridge"
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


def _compact_single_arg_arrows(text: str) -> str:
    """Apply the semantics-preserving `(identifier)=>` -> `identifier=>` spelling."""
    text = re.sub(r"\(([A-Za-z_$][A-Za-z0-9_$]*)\)=>", r"\1=>", text)
    return re.sub(r"async([A-Za-z_$][A-Za-z0-9_$]*)=>", r"async \1=>", text)


def _compact_simple_control_blocks(text: str) -> str:
    """Remove braces around simple return/continue/break statements."""
    text = re.sub(r"if\(([^{};]+)\)\{return\}", r"if(\1)return;", text)
    text = re.sub(r"if\(([^{};]+)\)\{return ([^{};]+)\}", r"if(\1)return \2;", text)
    text = re.sub(r"if\(([^{};]+)\)\{continue\}", r"if(\1)continue;", text)
    text = re.sub(r"if\(([^{};]+)\)\{break\}", r"if(\1)break;", text)
    return text


def _replacement(name: str) -> bytes:
    path = REPLACEMENTS / name
    if not path.is_file():
        raise ValueError(f"replacement asset missing: {path}")
    return path.read_bytes()


def _messages_patch(data: bytes) -> Patch:
    start = data.find(b"var J3r,Nb,pI,Fhl,pCm,iCm,bHT,sCm,Iki=null,SHT,$hl=30,EHT=50,aCm=200,AHT=({")
    end = data.find(b",fCm,dCm;var jqn", start)
    if start < 0 or end < 0:
        raise ValueError("renderer-messages-d3: complete AHT range missing")
    old = data[start:end]
    text = old.decode("utf-8")
    text = _replace_once(
        text,
        "Q=tu(),G=!1,q=Nb.useMemo(()=>null,[e,!1]),",
        "Q=tu(),G=(K=0|rpQ(0,0,l),u||=!!(1&K),O||=!!(2&K)),q=Nb.useMemo(()=>null,[e,G]),",
        "renderer-messages-d3",
    )
    text = _replace_once(
        text,
        "Xe=Nb.useMemo(()=>new Set(c.map((be)=>be.contentBlock.id)),[c]),",
        "rp=++rpG;rpC(3,rp,65535,[e,ye,$e,Ge,yt,oe,se,ie,qe,tt,Y,ne,l,u,O,H]);let Xe=Nb.useMemo(()=>new Set(c.map(be=>be.contentBlock.id)),[c]),",
        "renderer-messages-d3",
    )
    text = _replace_once(
        text,
        "Nb.useEffect(()=>()=>jt(null),[jt]);",
        "Nb.useEffect(()=>()=>{jt(null),rpC(3,rp,0,null)},[jt,rp]);",
        "renderer-messages-d3",
    )
    text = _compact_simple_control_blocks(_compact_single_arg_arrows(text))
    new = _padded(old, _replacement("messages-d3.js"))
    return Patch("renderer-messages-d3", old, new, start)


def _reset_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function lhn(", b"function svd(")
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
                "e.txn((h)=>{let g=Array(1+m);g[0]=_vr;for(let _=0;_<m;_++)"
                "g[1+_]=XLo;return[g,{dx:-h.x,dy:m}]})"
            ),
            (
                "e.txn(h=>{let g=[_vr];for(let _=0;_<m;_++)g.push(XLo);"
                "return[g,{dx:-h.x,dy:m}]})"
            ),
        ),
        ("for(let m=0;m<l;m+=1,p+=1)", "for(let m=0;m<l;m++,p++)"),
        ("let g=h.hyperlink;s=aSt(e.diff,s,g);", "s=aSt(e.diff,s,h.hyperlink);"),
        (
            "if(svd(e,h,_))i=h.styleId,a=h.styleId",
            "if(svd(e,h,_))i=a=h.styleId",
        ),
    ]
    for before, after in replacements:
        text = _replace_once(text, before, after, "renderer-reset")
    new = _padded(old, text.encode("utf-8"))
    return Patch("renderer-reset", old, new, offset)


def _toggle_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function J$i(", b"var i3l,Mrh;")
    text = old.decode("utf-8")
    replacements = [
        (
            'if(!rxO()&&G5r&&Y$i!=="transcript"){dPe(pSv);return}',
            'if(!rxO()&&G5r&&Y$i!=="transcript")return dPe(pSv);',
        ),
        (
            "oVn(fSv),uHt(!1)},pPe[6]=",
            (
                'oVn(fSv),uHt(!1),Y$i!=="transcript"&&rpQ(2,!1,!0)'
                "&&setTimeout(gSv,50)},pPe[6]="
            ),
        ),
        (
            "let Ybv=()=>{if(txO()){return}dPe(dSv)};",
            "let Ybv=()=>{if(!txO())dPe(dSv)};",
        ),
        (
            "if(!sxO()&&!G5r){return}let xrh=!G5r;",
            "if(!sxO()&&!G5r)return;let xrh=!G5r;",
        ),
        (
            (
                "dPe((Irh)=>{if(Irh.isBriefOnly===xrh){return Irh}"
                "return{...Irh,isBriefOnly:xrh}})"
            ),
            "dPe(Irh=>Irh.isBriefOnly===xrh?Irh:{...Irh,isBriefOnly:xrh})",
        ),
        (
            ('Zbv;if(pPe[26]===ee)Zbv={context:"Global"},pPe[26]=Zbv;else Zbv=pPe[26];'),
            'Zbv=pPe[26];if(Zbv===ee)Zbv=pPe[26]={context:"Global"};',
        ),
        (
            'let eSv;if(pPe[27]===ee)eSv={context:"Global"},pPe[27]=eSv;else eSv=pPe[27];',
            'let eSv=pPe[27];if(eSv===ee)eSv=pPe[27]={context:"Global"};',
        ),
        (
            'let tSv;if(pPe[28]===ee)tSv={context:"Global"},pPe[28]=tSv;else tSv=pPe[28];',
            'let tSv=pPe[28];if(tSv===ee)tSv=pPe[28]={context:"Global"};',
        ),
        (
            ('rSv;if(pPe[29]===ee)rSv={context:"Global"},pPe[29]=rSv;else rSv=pPe[29];'),
            'rSv=pPe[29];if(rSv===ee)rSv=pPe[29]={context:"Global"};',
        ),
        (
            ('nSv;if(pPe[30]===ee)nSv={context:"Global"},pPe[30]=nSv;else nSv=pPe[30];'),
            'nSv=pPe[30];if(nSv===ee)nSv=pPe[30]={context:"Global"};',
        ),
    ]
    for before, after in replacements:
        text = _replace_once(text, before, after, "renderer-toggle-redraw")
    new = _padded(old, text.encode("utf-8"))
    return Patch("renderer-toggle-redraw", old, new, offset)


def _context_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function Qmf(", b"var Zmf,TOr,cui,G_e,Rba,thf;")
    text = old.decode("utf-8")
    stock = (
        'function Qmf(e,t){if(ES(e))return 1e6;if(t?.includes(dz.header)&&mz(e))return 1e6;'
        'if(U1(e))return 1e6;let r=tri(e);if(r!==null)return r;let n=te.CLAUDE_CODE_MAX_CONTEXT_TOKENS;'
        'if(n!==void 0&&n>0&&!Eo(ns(e)).startsWith("claude-"))return n;return ebr}'
    )
    bridged = (
        'var rpG=0,rpS=0;function rpQ(...e){try{return globalThis.__rp?.q?.(...e)??e[1]}catch{return e[1]}}'
        'function rpC(...e){try{globalThis.__rp?.c?.(...e)}catch{}}'
        'function Qmf(e,t){let r=ES(e)||t?.includes(dz.header)&&mz(e)||U1(e)?1e6:tri(e),'
        'n=te.CLAUDE_CODE_MAX_CONTEXT_TOKENS;return null===r&&(r=n!==void 0&&n>0&&!Eo(ns(e)).startsWith("claude-")?n:ebr),rpQ(3,r,Eo(ns(e)))}'
    )
    text = _replace_once(text, stock, bridged, "provider-context-window")
    text = _replace_once(
        text,
        'function tri(e){if(Jne())return null;if(ES(e))return null;if(Eo(e)!=="claude-sonnet-4-6")return null;',
        'function tri(e){if(Jne()||ES(e)||Eo(e)!=="claude-sonnet-4-6")return null;',
        "provider-context-window",
    )
    text = _replace_once(
        text,
        'function JSS(e){let t=wk()?.heather_vale;if(typeof t!=="object"||t===null||Array.isArray(t))return null;let r=t[e];if(typeof r!=="number"||!Number.isInteger(r)||r<=0)return null;return r}',
        'function JSS(e){let t=wk()?.heather_vale;if(typeof t!=="object"||null===t||Array.isArray(t))return null;let r=t[e];return typeof r!=="number"||!Number.isInteger(r)||r<=0?null:r}',
        "provider-context-window",
    )
    text = _replace_once(
        text,
        'function ZDr(e){if(e==="firstParty"||hG(e))return!0;return!0}',
        'function ZDr(e){return e==="firstParty"||hG(e),!0}',
        "provider-context-window",
    )
    text = _replace_once(
        text,
        'function Tba(e){if(A_o())return e;return e.filter((t)=>thf.has(t))}',
        'function Tba(e){return A_o()?e:e.filter(t=>thf.has(t))}',
        "provider-context-window",
    )
    text = _compact_simple_control_blocks(_compact_single_arg_arrows(text))
    new = _padded(old, _replacement("context-and-capture-runtime.js"))
    return Patch("provider-context-window", old, new, offset)


def _routing_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function fse(", b"function Hbe(")
    text = old.decode("utf-8")
    text = _replace_once(
        text,
        'if(r==="inherit")return i();if(XDp(r,t))return t;let p=c(Ffa(ns(r)),r);',
        'if(r==="inherit")return i();let p=XDp(r,t);if(rpQ(4,p,r,t))return t;p=c(Ffa(ns(r)),r);',
        "subagent-routing-static-d0",
    )
    text = _replace_once(
        text,
        'var Swt=v(()=>{cr();_z();uR();Qe();qr();Wr();wy();P4e();Oi();pz();$fa();As()});',
        'var Swt=v(()=>{cr();_z();uR();Qe();qr();Wr();wy();P4e();Oi();pz();$fa();As();'
        'rpC(0,0,4194303,[jD,ns,vc,Eo,Jy,BT,hC,Qmf,ES,U1,mz,Xmf,SHs,tri,sTt,fse,QDp,Ffa,XDp,V$b,LIr,K$b])});',
        "subagent-routing-static-d0",
    )
    text = _replace_once(
        text,
        'if(wa(ns(m)).toLowerCase()!==wa(ns(g)).toLowerCase())o?.(p,g,h!==null?"family_step_down":"parent_inherit");return g',
        'return wa(ns(m)).toLowerCase()!==wa(ns(g)).toLowerCase()&&o?.(p,g,null!==h?"family_step_down":"parent_inherit"),g',
        "subagent-routing-static-d0",
    )
    text = _compact_simple_control_blocks(_compact_single_arg_arrows(text))
    new = _padded(old, _replacement("routing-and-d0.js"))
    return Patch("subagent-routing-static-d0", old, new, offset)


def _app_provider_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function oI(", b"var rkf,j6,Kot,nkf,cmi;")
    replacement = (
        'function oI(e){let t,r=nkf.c(26),{children:n,initialState:s,onChangeAppState:a}=e;'
        'if(j6.useContext(cmi))throw Error("AppStateProvider can not be nested within another AppStateProvider");'
        'r[0]!==s||r[1]!==a?(t=()=>xR(s??Tfe(),a),r[0]=s,r[1]=a,r[2]=t):t=r[2];'
        'let c,i,l,u,S,o,f,p,d,[h]=j6.useState(t);r[3]!==h?(c=()=>{let e=++rpG;'
        'rpC(2,e,63,[h,C$,h.getState,h.setState,h.subscribe,Tfe]);let t=()=>w1n(h.getState().tasks),r=Pa(t);'
        'return()=>{t(),r(),rpC(2,e,0,null)}},i=[h],r[3]=h,r[4]=c,r[5]=i):(c=r[4],i=r[5]),j6.useEffect(c,i),'
        'r[6]!==h?(l=()=>wZn(()=>h.getState().mcp.clients),u=[h],r[6]=h,r[7]=l,r[8]=u):(l=r[7],u=r[8]),j6.useEffect(l,u),'
        'r[9]!==h?(S=()=>CZn((e,t)=>{let r=!1;return h.setState(n=>{let s=_Tr(n,e,t);return r=s!==n,s}),r}),o=[h],r[9]=h,r[10]=S,r[11]=o):(S=r[10],o=r[11]),j6.useEffect(S,o),'
        'r[12]!==h.setState?(f=()=>C1n(h.setState),r[12]=h.setState,r[13]=f):f=r[13],r[14]!==h?(p=[h],r[14]=h,r[15]=p):p=r[15],j6.useEffect(f,p),'
        'r[16]!==h.setState?(d=e=>A1n(e,h.setState),r[16]=h.setState,r[17]=d):d=r[17];let g,v,z,E,Y=j6.useEffectEvent(d);Wot(Y),'
        'r[18]!==Y?(g=()=>{R1n(()=>Y("policySettings"))},r[18]=Y,r[19]=g):g=r[19],r[20]===ee?(v=[],r[20]=v):v=r[20],j6.useEffect(g,v),'
        'r[21]!==n?(z=Kot.jsx(Vfi,{children:Kot.jsx(Opi,{children:n})}),r[21]=n,r[22]=z):z=r[22],'
        'r[23]!==h||r[24]!==z?(E=Kot.jsx(cmi.Provider,{value:!0,children:Kot.jsx(xot.Provider,{value:h,children:z})}),r[23]=h,r[24]=z,r[25]=E):E=r[25],E}'
    )
    new = _padded(old, replacement.encode("utf-8"))
    return Patch("app-provider-d2", old, new, offset)


def _repl_patch(data: bytes) -> Patch:
    start = data.find(b"let Bor=Qr.useCallback(")
    end = data.find(b";var D7l=", start)
    if start < 0 or end < 0:
        raise ValueError("repl-render-d4-static-d1: supplier range missing")
    old = data[start:end]
    text = old.decode("utf-8")
    d1_bitmap = sum(1 << index for index in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 20, 21])
    capture = (
        ',AI={screen:hr,setScreen:zr,showAllInTranscript:jt,setShowAllInTranscript:ct,'
        'messageCount:wE.messages.length,virtualScrollActive:Li,searchBarOpen:mc},rp=++rpG;'
        f'rpS||(rpS=1,rpC(1,0,{d1_bitmap},[Kp,Svr,T4s,lhn,ivd,v4s,kUs,AUs,ehn,nEd,Ywy,Vwy,Gwy,C$,,E,,,,,L,Te]));'
        'rpC(2,rp,63,[Ge,C$,Ge.getState,Ue,Ge.subscribe,Tfe]);'
        'rpC(4,rp,65535,[Ge,Ue,wE,hr,zr,jt,ct,lr,er,Jo,CI,en,ue,Xd,cs,AI]);'
    )
    text = _replace_once(
        text,
        ",{columns:iEe,rows:eOe}=ln(),jor=Qr.useRef(iEe);Qr.useEffect(()=>{",
        ",{columns:iEe,rows:eOe}=ln(),jor=Qr.useRef(iEe)" + capture + "Qr.useEffect(()=>{",
        "repl-render-d4-static-d1",
    )
    text = _replace_once(
        text,
        'og("")}},[iEe,dl,mc,og]);',
        'og("")}return()=>{rpC(2,rp,0,null),rpC(4,rp,0,null)}},[iEe,dl,mc,og,rp]);',
        "repl-render-d4-static-d1",
    )
    text = _replace_once(
        text,
        'let AI={screen:hr,setScreen:zr,showAllInTranscript:jt,setShowAllInTranscript:ct,messageCount:wE.messages.length,virtualScrollActive:Li,searchBarOpen:mc},$W=',
        'let $W=',
        "repl-render-d4-static-d1",
    )
    text = text.replace("Array.from(to.values())", "[...to.values()]")
    text = _compact_simple_control_blocks(_compact_single_arg_arrows(text))
    new = _padded(old, _replacement("repl-d4.js"))
    return Patch("repl-render-d4-static-d1", old, new, start)


def _key_provider_patch(data: bytes) -> Patch:
    offset, old = _unique_region(data, b"function Nhn(", b"function $w()")
    replacement = (
        'function Nhn(e){let t,r,n,i,s,d=z3s.c(25),{bindings:c,pendingChordRef:g,pendingChord:o,setPendingChord:a,'
        'activeContexts:l,registerActiveContext:h,unregisterActiveContext:p,handlerRegistryRef:u,preDispatchRef:C,keyHandlerRegistry:v,children:x}=e;'
        'd[0]!==c||d[1]!==g?(t=(e,t,r)=>Uyt(M3s(e,t),r,c,g.current),d[0]=c,d[1]=g,d[2]=t):t=d[2],'
        'd[3]!==c?(r=(e,t)=>Jpn(e,t,c),d[3]=c,d[4]=r):r=d[4],d[5]!==u?(n=e=>{let t=u.current;return t?(t.has(e.action)||t.set(e.action,new Set),'
        't.get(e.action).add(e),()=>{let r=t.get(e.action);r&&(r.delete(e),0===r.size&&t.delete(e.action))}):n0y},d[5]=u,d[6]=n):n=d[6],'
        'd[7]!==C?(i=e=>(C.current.add(e),()=>C.current.delete(e)),d[7]=C,d[8]=i):i=d[8],'
        'd[9]!==l||d[10]!==c||d[11]!==v||d[12]!==o||d[13]!==h||d[14]!==a||d[15]!==t||d[16]!==r||d[17]!==n||d[18]!==i||d[19]!==p?'
        '(s={resolve:t,setPendingChord:a,getDisplayText:r,bindings:c,pendingChord:o,activeContexts:l,registerActiveContext:h,unregisterActiveContext:p,registerHandler:n,registerPreDispatch:i,keyHandlerRegistry:v},'
        'd[9]=l,d[10]=c,d[11]=v,d[12]=o,d[13]=h,d[14]=a,d[15]=t,d[16]=r,d[17]=n,d[18]=i,d[19]=p,d[20]=s,d[24]=[++rpG,s,c,u,C,v,l,g,a,o]):s=d[20],'
        'x.type===wFa&&(x=t6e.cloneElement(x,{__rp:d[24]}));let y,R=s;return d[21]!==x||d[22]!==R?(y=j3s.jsx(I1o.Provider,{value:R,children:x}),d[21]=x,d[22]=R,d[23]=y):y=d[23],y}'
    )
    new = _padded(old, replacement.encode("utf-8"))
    return Patch("key-provider-d5-payload", old, new, offset)


def _key_lifecycle_patch(data: bytes) -> Patch:
    start = data.find(b"function wFa(")
    end = data.find(b"function qfi(", start + len(b"function wFa("))
    if start < 0 or end < 0:
        raise ValueError("key-provider-d5-lifecycle: supplier range missing")
    old = data[start:end]
    text = old.decode("utf-8")
    text = _replace_once(
        text,
        "keyHandlerRegistry:iRf,children:sRf}=rax",
        "keyHandlerRegistry:iRf,children:sRf,__rp:RP}=rax",
        "key-provider-d5-lifecycle",
    )
    old_effect = (
        'if(M7t[22]===ee)oMS=()=>{if(!vFa.current){return}let g1n=iAe(vFa.current);let sMS=()=>{let Ufi=vFa.current;'
        'if(!Ufi||g1n.activeElement===Ufi){return}if(g1n.activeElement===null){g1n.focus(Ufi);return}let EFa=Ufi.parentNode;'
        'while(EFa){if(EFa===g1n.activeElement){g1n.focus(Ufi);return}EFa=EFa.parentNode}};return sMS(),g1n.subscribe(sMS)},iMS=[],M7t[22]=oMS,M7t[23]=iMS;'
        'else oMS=M7t[22],iMS=M7t[23];H0.useLayoutEffect(oMS,iMS);'
    )
    new_effect = (
        'if(M7t[22]!==RP)oMS=()=>{let e,t;if(RP){let[n,...o]=RP;rpC(5,n,511,o),t=n}if(vFa.current){let n=iAe(vFa.current),o=()=>{let e=vFa.current;'
        'if(!e||n.activeElement===e)return;if(null===n.activeElement)return void n.focus(e);for(let t=e.parentNode;t;){if(t===n.activeElement)return void n.focus(e);t=t.parentNode}};o(),e=n.subscribe(o)}'
        'return()=>{e?.(),t!==void 0&&rpC(5,t,0,null)}},iMS=[RP],M7t[22]=RP,M7t[23]=oMS,M7t[28]=iMS;else oMS=M7t[23],iMS=M7t[28];H0.useLayoutEffect(oMS,iMS);'
    )
    text = _replace_once(text, old_effect, new_effect, "key-provider-d5-lifecycle")
    text = _compact_simple_control_blocks(_compact_single_arg_arrows(text))
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
