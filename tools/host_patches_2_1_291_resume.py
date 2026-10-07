# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resumable stopped background agents for the official 2.1.291 Darwin graph.

Stop means pause: every stop path still really kills the agent and still
writes the upstream `stoppedByUser` marker (task UI, notifications and
automatic wake paths keep relying on it). Only an explicit SendMessage
(the resume engine's "reply" mode) may revive a stopped agent.

  T1  resume engine: the sidecar and in-memory stopped-by-user refusals no
      longer apply to reply mode. A stop that lands *during* a reply resume
      still wins (userStopCount race check). A reply resume clears the
      sidecar marker through upstream's own userInitiated clear block (same
      counter re-check and corrective re-write). This is required: otherwise
      the revived agent's later task-notification wakes ("notification" mode)
      would be refused by the stale marker. Like upstream, the clear happens
      before launch is fully committed. Upstream exceptions stay: a human
      typing into the agent's own view (userInitiated) and observer-activity.
  T2  SendMessage resolver: an in-memory stopped-by-user agent resolves as an
      ordinary stopped agent, so the resume engine is reached at all.
  T3  orphan notice after restart: one sidecar read per orphan; a stopped or
      unreadable sidecar is excluded from the 48 h auto-resume list (fail
      closed), and a known stop gets its own truthful "paused, resume with
      SendMessage" notice (never folded into the grouped generic wording).
  T4  SendMessage by name after a restart: only when the whole resolver ends
      in "not-found" for a bare name (after teammates, roster, sessions, cloud,
      bridge and pins), look the name up in this session's subagent sidecars
      and resolve it when exactly one readable agent carries it. Any read
      failure or duplicate keeps the original not-found result.

Automatic wake paths (task-notification wakes, stranded resumes, observer
deliveries, orphan auto-resume) still refuse a stopped agent, so nothing
restarts on its own.
"""

import re

STOP_REFUSAL = (
    "Agent ${e} was stopped by the user and won't be resumed. Treat its work as "
    "cancelled; only launch a new agent if the user explicitly asks."
)


def patch_resume(result, edit):
    # T1: resume engine (Qt). `ce` is Qt's mode parameter; SendMessage enters
    # through the "reply" wrapper. Automatic paths use "notification"/"inline".
    edit(
        "chunk-ebe4qw6e.js",
        [
            (
                'if(n?.stoppedByUser&&g?.kind!=="observer-activity"){if(!M)throw k(),new OU(',
                'if(n?.stoppedByUser&&g?.kind!=="observer-activity"&&ce!=="reply"){if(!M)throw k(),new OU(',
            ),
            (
                "W=u.get(e);if(Pn(W)&&W.stoppedByUser&&(!M||(W.userStopCount??0)!==ee))throw k(),new OU(",
                'W=u.get(e);if(Pn(W)&&W.stoppedByUser&&(!M&&ce!=="reply"||(W.userStopCount??0)!==ee))throw k(),new OU(',
            ),
            (
                "if(it)try{if(vJn(u.get(e))===ee){if(await Yoe(yo(e),{stoppedByUser:!1},s.storageV5)",
                'if(it||ce==="reply"&&(n?.stoppedByUser===!0||Pn(P)&&P.stoppedByUser===!0))try{if(vJn(u.get(e))===ee){if(await Yoe(yo(e),{stoppedByUser:!1},s.storageV5)',
            ),
        ],
    )
    # T2 + T4: SendMessage target resolver. The dynamic import reuses the
    # graph's own absolute module directory (taken from an existing import).
    match = re.search(r'import\{F4n,R1r,M7n\}from"([^"]+/)chunk-v1gtm86q\.js"', result["chunk-dj0tea96.js"])
    if not match:
        raise ValueError("resolver import anchor missing")
    graph_dir = match[1]
    edit(
        "chunk-dj0tea96.js",
        [
            (
                'if(s.stoppedByUser)return{kind:"agent-stopped-by-user",agentName:i};',
                "/*rp:stopped-agent-resumable*/",
            ),
            (
                'import{F4n,R1r,M7n}from"',
                'import{F4n,R1r,M7n,Kx}from"',
            ),
            (
                "return De(k,r,s,V())??{...U(r,k),...be(r,f,k,s.sendMessagePins),...fe(u,F,c.unavailable,{remoteTruncated:Y}),...N(s.sendMessagePins,[r],Q)}}",
                "let rpNf=De(k,r,s,V())??{...U(r,k),...be(r,f,k,s.sendMessagePins),...fe(u,F,c.unavailable,{remoteTruncated:Y}),...N(s.sendMessagePins,[r],Q)};"
                "if(rpNf.kind===\"not-found\"&&!lze(n)&&AG(n)===null){let rpId=await __rpSidecarName(r,o);if(typeof rpId===\"string\")return X(s,rpId,n)}return rpNf}"
                "async function __rpSidecarName(r,o){let rpIds;try{rpIds=await(await import(\"" + graph_dir + "chunk-vvnkdfw1.js\")).YWe(o)}catch{return}"
                "let rpHit=[];for(let rpId of rpIds){if(iA(rpId)===null)continue;let rpMeta;try{rpMeta=await Kx(yo(rpId),o)}catch{return}"
                "if(rpMeta&&typeof rpMeta.name===\"string\"&&rpMeta.isObserver!==!0&&!lze(rpMeta.name)&&Ur(rpMeta.name)===r)rpHit.push(rpId)}"
                "return rpHit.length===1?rpHit[0]:rpHit.length>1?null:void 0}",
            ),
        ],
    )
    # T3: orphan notice in the next process after the previous one exited.
    edit(
        "chunk-jdcpjj4f.js",
        [
            (
                "let H;try{H=await ns(N,h,!1)}catch{H=null}let V=s!==void 0&&(x.launchedByAgentTool===!0||x.launchedByForkedSkill===!0)&&H!==null&&await Kx(N,h).catch(x1e(\"resume orphan probe\"))!==null;return{mtimeMs:H,hasMeta:V,fetchable:H===null&&cjt()}",
                "let H;try{H=await ns(N,h,!1)}catch{H=null}let rpM=H===null?null:await Kx(N,h).then((rpR)=>({ok:!0,meta:rpR}),(rpE)=>(x1e(\"resume orphan probe\")(rpE),{ok:!1,meta:null})),"
                "rpS=rpM!==null&&(!rpM.ok||rpM.meta?.stoppedByUser===!0),"
                "V=s!==void 0&&(x.launchedByAgentTool===!0||x.launchedByForkedSkill===!0)&&H!==null&&rpM.ok&&rpM.meta!==null;"
                "return{mtimeMs:H,hasMeta:V,fetchable:H===null&&cjt(),rpStopped:rpS,rpKnownStop:rpM?.meta?.stoppedByUser===!0}",
            ),
            (
                "let{mtimeMs:H,hasMeta:V,fetchable:A}=C[x]??{mtimeMs:null,hasMeta:!1,fetchable:!1};",
                "let{mtimeMs:H,hasMeta:V,fetchable:A,rpStopped:rpS,rpKnownStop:rpK}=C[x]??{mtimeMs:null,hasMeta:!1,fetchable:!1};",
            ),
            (
                "&&V&&H!==null&&R-H<es){v.push({agentId:N.agentId",
                "&&V&&H!==null&&!rpS&&R-H<es){v.push({agentId:N.agentId",
            ),
            (
                ":j?`No completion record was found for it in the previous session. It may have been stopped, or it may have been running",
                ":j&&rpK?`It was stopped (by the user, TaskStop, or an interrupt) before it finished, so it is paused: its transcript is saved and it will not continue on its own. To continue it, send it a message with SendMessage using its agent id; otherwise leave it stopped. Do not launch a duplicate agent for the same work.`"
                ":j?`No completion record was found for it in the previous session. It may have been stopped, or it may have been running",
            ),
            (
                "if(N.redispatched)Ne(N,L,Y,ce);else M[L].push({agent:N,summary:Y,note:ce});",
                "if(N.redispatched||rpK)Ne(N,L,Y,ce);else M[L].push({agent:N,summary:Y,note:ce});",
            ),
        ],
    )
