"""Disk-backed in-process teammate views for the official 2.1.318 graph.

The stock teammate display cache keeps only 50 rows, seeds resumed teammates
from the same bounded tail, and collapses a terminal transcript to its final
row.  Local-agent views already have a retained-view disk hydration lifecycle.
This recipe extends that lifecycle to in-process teammates while preserving the
stock off-view cap, explicit context compaction, and task retirement behavior.
"""


HYDRATE_BEFORE = (
    "function Pqe({store:h,setAppState:D,storageV5:O}){return nD([h],()=>{"
    "let{viewingAgentTaskId:H,tasks:te}=h.getState(),Re=H?te[H]:void 0,"
    "Oe=Cn(Re)&&Re.retain&&!Re.diskLoaded;return[H,Oe]},(H,te)=>{"
    "if(!H||!te)return;let Re=H;ede(Er(Re),O).then((Oe)=>{D((Ue)=>{"
    "let je=Ue.tasks[Re];if(!Cn(je)||je.diskLoaded||!je.retain)return Ue;"
    "let qe=Ue.transcripts[Re],Ke=qe?.messages??[],Ze=new Set(Ke.map((Rt)=>Rt.uuid)),"
    "st=xqe(Oe?.messages??[],Ke),bt=st.filter((Rt)=>!Ze.has(Rt.uuid));return t5e(bt),"
    "{...Ue,tasks:{...Ue.tasks,[Re]:{...je,diskLoaded:!0}},"
    "transcripts:{...Ue.transcripts,[Re]:{inProgressToolUseIDs:new Set,...qe,messages:st}}}})}"
    ").catch(a)})}"
)

HYDRATE_AFTER = (
    "function Pqe({store:h,setAppState:D,storageV5:O}){let rpEpoch=0;"
    "let rpOff=nD([h],()=>{let{viewingAgentTaskId:H,tasks:te}=h.getState(),"
    "Re=H?te[H]:void 0,Oe=(Cn(Re)||rf(Re))&&Re.retain&&!Re.diskLoaded;"
    "return[H,Oe,Re?.startTime,Re?.status,rf(Re)?Re.identity.resumableAgentId:H]},"
    "(H,te,rpStart,rpStatus,rpAgentId)=>{let rpRead=++rpEpoch;"
    "if(!H||!te||!rpAgentId)return;let Re=H;ede(Er(rpAgentId),O).then((Oe)=>{"
    "if(rpRead!==rpEpoch)return;D((Ue)=>{let je=Ue.tasks[Re];"
    "if(rpRead!==rpEpoch||Ue.viewingAgentTaskId!==Re||!(Cn(je)||rf(je))||"
    "je.startTime!==rpStart||je.diskLoaded||!je.retain||"
    "rf(je)&&je.identity.resumableAgentId!==rpAgentId)return Ue;"
    "let qe=Ue.transcripts[Re],Ke=qe?.messages??[],Ze=new Set(Ke.map((Rt)=>Rt.uuid)),"
    "st,bt;if(rf(je)&&Oe){let rpDisk=Oe.messages??[],rpLive=new Map,rpIndex=new Map,rpPos=0;"
    "for(let rpRow of Ke)rpLive.set(rpRow.uuid,rpRow);"
    "for(let rpI=0;rpI<rpDisk.length;rpI++)rpIndex.set(rpDisk[rpI].uuid,rpI);"
    "st=[];for(let rpRow of Ke){let rpI=rpIndex.get(rpRow.uuid);"
    "if(rpI===void 0){while(rpPos<rpDisk.length&&!rpLive.has(rpDisk[rpPos].uuid)&&"
    "typeof rpRow.timestamp===\"string\"&&typeof rpDisk[rpPos].timestamp===\"string\"&&"
    "rpDisk[rpPos].timestamp<=rpRow.timestamp)st.push(rpDisk[rpPos++]);"
    "if(rpLive.has(rpRow.uuid)){st.push(rpLive.get(rpRow.uuid));rpLive.delete(rpRow.uuid)}}"
    "else while(rpPos<=rpI){let rpRowDisk=rpDisk[rpPos++];"
    "st.push(rpLive.get(rpRowDisk.uuid)??rpRowDisk)}}"
    "while(rpPos<rpDisk.length){let rpRowDisk=rpDisk[rpPos++];"
    "st.push(rpLive.get(rpRowDisk.uuid)??rpRowDisk)}}"
    "else st=xqe(Oe?.messages??[],Ke);bt=st.filter((Rt)=>!Ze.has(Rt.uuid));"
    "return t5e(bt),{...Ue,tasks:{...Ue.tasks,[Re]:{...je,diskLoaded:!0}},"
    "transcripts:{...Ue.transcripts,[Re]:{inProgressToolUseIDs:new Set,...qe,messages:st}}}})}"
    ").catch(a)});return()=>{rpEpoch++;rpOff()}}"
)


def patch_teammate_view(result, edit):
    edit(
        "chunk-0x9x817t.js",
        [
            (
                'function Wut(e){if(e.type==="in_process_teammate")return{...e,evictAfter:e.isIdle?Date.now()+uzn:void 0};return{...e,retain:!1,diskLoaded:!1,evictAfter:Ko(e.status)&&!IG(e)?Date.now()+uzn:void 0}}',
                'function Wut(e){if(e.type==="in_process_teammate")return{...e,retain:!1,diskLoaded:!1,evictAfter:e.isIdle||Ko(e.status)?Date.now()+uzn:void 0};return{...e,retain:!1,diskLoaded:!1,evictAfter:Ko(e.status)&&!IG(e)?Date.now()+uzn:void 0}}',
            ),
            (
                "w=jut(s)&&(Uut(s)&&!s.retain||s.evictAfter!==void 0),",
                "w=jut(s)&&(!s.retain||s.evictAfter!==void 0),",
            ),
            (
                "if(w)z[e]=Uut(s)?{...s,retain:!0,evictAfter:void 0}:{...s,evictAfter:void 0}",
                "if(w)z[e]={...s,retain:!0,evictAfter:void 0}",
            ),
        ],
    )
    edit("chunk-p2q3ejfg.js", [(HYDRATE_BEFORE, HYDRATE_AFTER)])
    edit(
        "chunk-ygm0kzqk.js",
        [
            (
                "function Ult(e,n){if(e===void 0||e.length===0)return[n];if(e.length>=dto){let r=e.slice(-(dto-1));return r.push(n),r}return[...e,n]}"
                "function Q_i(e,n){let r=e===void 0||e.every((o)=>o.uuid!==n.uuid)?e:e.filter((o)=>o.uuid!==n.uuid);return Ult(r,n)}",
                "function Ult(e,n,rpRetain){if(e===void 0||e.length===0)return[n];if(!rpRetain&&e.length>=dto){let r=e.slice(-(dto-1));return r.push(n),r}return[...e,n]}"
                "function Q_i(e,n,rpRetain){let r=e===void 0||e.every((o)=>o.uuid!==n.uuid)?e:e.filter((o)=>o.uuid!==n.uuid);return Ult(r,n,rpRetain)}",
            ),
        ],
    )
    edit(
        "chunk-me4n0c3r.js",
        [
            ("messages:Ult(n.messages,a)", "messages:Ult(n.messages,a,s.get(e)?.retain)"),
            ("messages:Ult(r.messages,i)", "messages:Ult(r.messages,i,s.get(e)?.retain)"),
        ],
    )
    edit(
        "chunk-nyc0s6f6.js",
        [
            (
                "let z=k.messages;if(I)for(let Ae of I.slice(-dto))z=Ult(z,Ae);return{...k,messages:Ult(z,Ie({content:Ee}))}",
                "let z=k.messages,rpRetain=r.get(s)?.retain;if(I)for(let Ae of rpRetain?I:I.slice(-dto))z=Q_i(z,Ae,rpRetain);return{...k,messages:Ult(z,Ie({content:Ee}),rpRetain)}",
            ),
            ("messages:Q_i(E.messages,o)", "messages:Q_i(E.messages,o,r.get(s)?.retain)"),
            ("messages:Ult(v.messages,o)", "messages:Ult(v.messages,o,r.get(s)?.retain)"),
            (
                "evictAfter:oe?void 0:Date.now()+YO,onIdleCallbacks:[]",
                "evictAfter:oe||o.retain?void 0:Date.now()+YO,onIdleCallbacks:[]",
            ),
            (
                'return x=k.toolUseId,k.onIdleCallbacks?.forEach((z)=>z()),{...k,status:"completed",notified:!0,',
                'return x=k.toolUseId,k.onIdleCallbacks?.forEach((z)=>z()),{...k,status:"completed",diskLoaded:!1,notified:!0,',
            ),
            (
                "r.updateTranscript(s,(k)=>({...k,messages:k.messages.length?[k.messages.at(-1)]:[],inProgressToolUseIDs:new Set}))",
                "r.updateTranscript(s,(k)=>({...k,messages:r.get(s)?.retain?k.messages:k.messages.length?[k.messages.at(-1)]:[],inProgressToolUseIDs:new Set}))",
            ),
            (
                'return me=x.toolUseId,x.onIdleCallbacks?.forEach((k)=>k()),{...x,status:"failed",notified:!0,',
                'return me=x.toolUseId,x.onIdleCallbacks?.forEach((k)=>k()),{...x,status:"failed",diskLoaded:!1,notified:!0,',
            ),
            (
                "r.updateTranscript(s,(x)=>({...x,messages:x.messages.length?[x.messages.at(-1)]:[],inProgressToolUseIDs:new Set}))",
                "r.updateTranscript(s,(x)=>({...x,messages:r.get(s)?.retain?x.messages:x.messages.length?[x.messages.at(-1)]:[],inProgressToolUseIDs:new Set}))",
            ),
        ],
    )
    edit(
        "chunk-nn5f14r9.js",
        [
            ("import{rf,I9t}from", "import{rf,I9t,YO}from"),
            (
                "paneTeardown:void 0,evictAfter:void 0}});let c=n?Wt(",
                "paneTeardown:void 0,evictAfter:e.retain?void 0:Date.now()+YO}});let c=n?Wt(",
            ),
        ],
    )
    return {
        "view_lifecycle": "chunk-0x9x817t.js · Wut/E1/k1",
        "disk_hydration": "chunk-p2q3ejfg.js · Pqe/xqe via identity.resumableAgentId",
        "bounded_cache": "chunk-ygm0kzqk.js · dto/Ult/Q_i",
        "message_append": "chunk-me4n0c3r.js · l2r/gGt",
        "runner": "chunk-nyc0s6f6.js · q$o seed/stream/idle/terminal paths",
        "kill_eviction": "chunk-nn5f14r9.js · a8n + YO",
        "compaction": "chunk-nyc0s6f6.js · WJr transition intentionally unchanged",
    }
