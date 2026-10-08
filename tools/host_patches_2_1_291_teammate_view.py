"""Disk-backed in-process teammate views for the official 2.1.291 graph.

Semantic anchors, not portable minified names:
* transcript-view enter/exit: local_agent gets retain/diskLoaded; teammate
  only gets evictAfter. Give both the existing view-retention lifecycle.
* retained-view watcher: getAgentTranscript(id, storage) -> UUID merge ->
  degradeRestored(disk-only rows). Reuse it for teammates, not a JSONL parser.
* teammate append/dedupe helper: last 49 + new row. Keep that off-view bound,
  bypass it only for a retained view, including seed and interruption paths.
* in-process runner: idle eviction deadline and terminal last-message cleanup.
  A viewed transcript must survive both; terminal transitions rehydrate disk.

Plain-agent append, compaction, routing, stop/resume and persistence are not
changed. The disk reader retains upstream's active-lineage/compaction semantics.
"""


HYDRATE_BEFORE = (
    "function kMe({store:h,setAppState:C,storageV5:M}){return $H([h],()=>{"
    "let{viewingAgentTaskId:N,tasks:Q}=h.getState(),he=N?Q[N]:void 0,"
    "be=Pn(he)&&he.retain&&!he.diskLoaded;return[N,be]},(N,Q)=>{"
    "if(!N||!Q)return;let he=N;ese(yo(he),M).then((be)=>{C((Pe)=>{"
    "let Oe=Pe.tasks[he];if(!Pn(Oe)||Oe.diskLoaded||!Oe.retain)return Pe;"
    "let Ne=Pe.transcripts[he],He=Ne?.messages??[],Ge=new Set(He.map((Ye)=>Ye.uuid)),"
    "je=be?be.messages.filter((Ye)=>!Ge.has(Ye.uuid)):[];return oPe(je),"
    "{...Pe,tasks:{...Pe.tasks,[he]:{...Oe,diskLoaded:!0}},"
    "transcripts:{...Pe.transcripts,[he]:{inProgressToolUseIDs:new Set,"
    "...Ne,messages:[...je,...He]}}}})}).catch(c)})}"
)

HYDRATE_AFTER = (
    "function kMe({store:h,setAppState:C,storageV5:M}){let rpEpoch=0;"
    "let rpOff=$H([h],()=>{let{viewingAgentTaskId:N,tasks:Q}=h.getState(),"
    "he=N?Q[N]:void 0,be=pZ(he)&&he.retain&&!he.diskLoaded;"
    "return[N,be,he?.startTime,he?.status,he?.type===\"in_process_teammate\"?he.identity.resumableAgentId:N]},"
    "(N,Q,rpStart,rpStatus,rpAgentId)=>{let rpRead=++rpEpoch;if(!N||!Q||!rpAgentId)return;let he=N;"
    "ese(yo(rpAgentId),M).then((be)=>{if(rpRead!==rpEpoch)return;C((Pe)=>{"
    "let Oe=Pe.tasks[he];if(rpRead!==rpEpoch||Pe.viewingAgentTaskId!==he||"
    "!pZ(Oe)||Oe.startTime!==rpStart||Oe.diskLoaded||!Oe.retain||"
    "Oe.type===\"in_process_teammate\"&&Oe.identity.resumableAgentId!==rpAgentId)return Pe;"
    "let Ne=Pe.transcripts[he],He=Ne?.messages??[],je,rpMessages;"
    "if(Oe.type===\"in_process_teammate\"&&be){let rpLive=new Map,rpIndex=new Map,rpPos=0;"
    "for(let rpRow of He)rpLive.set(rpRow.uuid,rpRow);"
    "for(let rpI=0;rpI<be.messages.length;rpI++)rpIndex.set(be.messages[rpI].uuid,rpI);"
    "je=be.messages.filter((rpRow)=>!rpLive.has(rpRow.uuid));rpMessages=[];"
    "for(let rpRow of He){let rpI=rpIndex.get(rpRow.uuid);"
    "if(rpI===void 0){while(rpPos<be.messages.length&&!rpLive.has(be.messages[rpPos].uuid)&&"
    "typeof rpRow.timestamp===\"string\"&&typeof be.messages[rpPos].timestamp===\"string\"&&"
    "be.messages[rpPos].timestamp<=rpRow.timestamp)rpMessages.push(be.messages[rpPos++]);"
    "if(rpLive.has(rpRow.uuid)){rpMessages.push(rpLive.get(rpRow.uuid));rpLive.delete(rpRow.uuid)}}"
    "else while(rpPos<=rpI){let rpDisk=be.messages[rpPos++];rpMessages.push(rpLive.get(rpDisk.uuid)??rpDisk)}}"
    "while(rpPos<be.messages.length){let rpDisk=be.messages[rpPos++];rpMessages.push(rpLive.get(rpDisk.uuid)??rpDisk)}}"
    "else{let Ge=new Set(He.map((Ye)=>Ye.uuid));je=be?be.messages.filter((Ye)=>!Ge.has(Ye.uuid)):[];"
    "rpMessages=[...je,...He]}return oPe(je),"
    "{...Pe,tasks:{...Pe.tasks,[he]:{...Oe,diskLoaded:!0}},"
    "transcripts:{...Pe.transcripts,[he]:{inProgressToolUseIDs:new Set,"
    "...Ne,messages:rpMessages}}}})}).catch(c)});"
    "return()=>{rpEpoch++;rpOff()}}"
)


def patch_teammate_view(result, edit):
    edit(
        "chunk-scapxbwa.js",
        [
            (HYDRATE_BEFORE, HYDRATE_AFTER),
            (
                'if(h.type==="in_process_teammate")return{...h,evictAfter:h.isIdle?Date.now()+$Me:void 0};',
                'if(h.type==="in_process_teammate")return{...h,retain:!1,diskLoaded:!1,evictAfter:h.isIdle||js(h.status)?Date.now()+$Me:void 0};',
            ),
            (
                "Pe=pZ(N)&&(uZ(N)&&!N.retain||N.evictAfter!==void 0),",
                "Pe=pZ(N)&&(!N.retain||N.evictAfter!==void 0),",
            ),
            (
                "if(Pe)Ne[h]=uZ(N)?{...N,retain:!0,evictAfter:void 0}:{...N,evictAfter:void 0}",
                "if(Pe)Ne[h]={...N,retain:!0,evictAfter:void 0}",
            ),
        ],
    )
    edit(
        "chunk-9ag6ybmh.js",
        [
            (
                "function GBe(e,n){if(e===void 0||e.length===0)return[n];if(e.length>=uJn){let r=e.slice(-(uJn-1));return r.push(n),r}return[...e,n]}"
                "function e6o(e,n){let r=e===void 0||e.every((s)=>s.uuid!==n.uuid)?e:e.filter((s)=>s.uuid!==n.uuid);return GBe(r,n)}",
                "function GBe(e,n,rpRetain){if(e===void 0||e.length===0)return[n];if(!rpRetain&&e.length>=uJn){let r=e.slice(-(uJn-1));return r.push(n),r}return[...e,n]}"
                "function e6o(e,n,rpRetain){let r=e===void 0||e.every((s)=>s.uuid!==n.uuid)?e:e.filter((s)=>s.uuid!==n.uuid);return GBe(r,n,rpRetain)}",
            ),
        ],
    )
    edit(
        "chunk-m5sckpqa.js",
        [
            ("messages:GBe(a.messages,r)", "messages:GBe(a.messages,r,s.get(e)?.retain)"),
            (
                "messages:GBe(m.messages,Re({content:r,origin:a}))",
                "messages:GBe(m.messages,Re({content:r,origin:a}),s.get(e)?.retain)",
            ),
        ],
    )
    edit(
        "chunk-zg4dkp5j.js",
        [
            (
                "let Q=I.messages;if(u)for(let be of u.slice(-uJn))Q=GBe(Q,be);return{...I,messages:GBe(Q,Re({content:Ee}))}",
                "let Q=I.messages,rpRetain=l.get(s)?.retain;if(u)for(let be of rpRetain?u:u.slice(-uJn))Q=e6o(Q,be,rpRetain);return{...I,messages:GBe(Q,Re({content:Ee}),rpRetain)}",
            ),
            ("messages:e6o(k.messages,r)", "messages:e6o(k.messages,r,l.get(s)?.retain)"),
            ("messages:GBe(w.messages,r)", "messages:GBe(w.messages,r,l.get(s)?.retain)"),
            (
                "evictAfter:ie?void 0:Date.now()+Yx,onIdleCallbacks:[]",
                "evictAfter:ie||r.retain?void 0:Date.now()+Yx,onIdleCallbacks:[]",
            ),
            (
                'return x=I.toolUseId,I.onIdleCallbacks?.forEach((Q)=>Q()),{...I,status:"completed",notified:!0,',
                'return x=I.toolUseId,I.onIdleCallbacks?.forEach((Q)=>Q()),{...I,status:"completed",diskLoaded:!1,notified:!0,',
            ),
            (
                "messages:I.messages.length?[I.messages.at(-1)]:[]",
                "messages:l.get(s)?.retain?I.messages:I.messages.length?[I.messages.at(-1)]:[]",
            ),
            (
                'return me=x.toolUseId,x.onIdleCallbacks?.forEach((I)=>I()),{...x,status:"failed",notified:!0,',
                'return me=x.toolUseId,x.onIdleCallbacks?.forEach((I)=>I()),{...x,status:"failed",diskLoaded:!1,notified:!0,',
            ),
            (
                "messages:x.messages.length?[x.messages.at(-1)]:[]",
                "messages:l.get(s)?.retain?x.messages:x.messages.length?[x.messages.at(-1)]:[]",
            ),
        ],
    )
    # The registry protects any task with a retain property and no deadline,
    # even retain:false. Preserve the stock delayed kill eviction off-view.
    edit(
        "chunk-qm1h7fwt.js",
        [
            (
                "paneTeardown:void 0,evictAfter:void 0}});let c=n?Ft(",
                "paneTeardown:void 0,evictAfter:e.retain?void 0:Date.now()+Ght}});let c=n?Ft(",
            ),
        ],
    )
