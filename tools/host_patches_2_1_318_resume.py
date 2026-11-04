# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resumable stopped background agents for the official 2.1.318 graph.

Stop still kills the agent and records the upstream stoppedByUser marker. Only
an explicit SendMessage (the resume engine's ``reply`` mode) may revive it.
Automatic notification, inline, stranded-retry, and orphan-restart paths keep
respecting the marker.

2.1.318 upstream changes retained by this port:

* The session rehydrator rebuilds ``agentNameRegistry`` from successful Agent
  tool-use/tool-result pairs (``y9n``), fixing SendMessage-by-name after a
  restart. The 2.1.291 sidecar-name fallback is therefore intentionally
  dropped.
* Orphan notices were rewritten around behavioral capabilities. This recipe
  does not pin or replace their wording; it only prevents stopped or unreadable
  agents from entering the automatic restart list.
"""


def patch_resume(result, edit):
    # R1: resume engine (Ur). B is the mode passed by Xzr ("reply") for
    # SendMessage. Bypass both stopped-by-user refusals only for reply mode.
    # The second guard still rejects a stop that lands during the resume: its
    # userStopCount differs from the snapshot in je.
    #
    # Extend upstream's marker-clear path to explicit reply resumes. Its own
    # counter re-check and corrective MCn rewrite remain intact, so a racing
    # stop wins and the revived agent does not retain a stale stop marker.
    edit(
        "chunk-z45ktpqq.js",
        [
            (
                'if((s?.stoppedByUser||tt)&&w?.kind!=="observer-activity"){if(!te)throw T(),new G6(',
                'if((s?.stoppedByUser||tt)&&w?.kind!=="observer-activity"&&B!=="reply"){if(!te)throw T(),new G6(',
            ),
            (
                'if(Cn(pe)&&pe.stoppedByUser&&(!te||(pe.userStopCount??0)!==je))throw T(),new G6(',
                'if(Cn(pe)&&pe.stoppedByUser&&(!te&&B!=="reply"||(pe.userStopCount??0)!==je))throw T(),new G6(',
            ),
            (
                'let Rt=te&&(s?.stoppedByUser===!0||tt||Cn(H)&&H.stoppedByUser===!0),Ot=',
                'let Rt=(te||B==="reply")&&(s?.stoppedByUser===!0||tt||Cn(H)&&H.stoppedByUser===!0),Ot=',
            ),
        ],
    )

    # R2: every explicit SendMessage must reach the resume engine. Remove both
    # the resolver's stopped-by-user terminal kind and 2.1.318's additional
    # restricted-messaging stoppedByPerson precheck. The resume engine remains
    # the authority and only its "reply" mode receives the exception.
    edit(
        "chunk-xfg1peqx.js",
        [
            (
                'if(s.stoppedByUser)return{kind:"agent-stopped-by-user",agentName:i};',
                "/*rp:explicit-reply-may-resume-stopped-agent*/",
            ),
        ],
    )
    edit(
        "chunk-nhbc679q.js",
        [
            (
                'if((r.kind==="agent-stopped"||r.kind==="agent-evicted")&&$di(r.agentId))return cs(r.agentName);',
                "/*rp:explicit-sendmessage-reaches-resume-engine*/",
            ),
        ],
    )


    # R3: orphan scan. Read both current stop-marker stores once: the sidecar
    # metadata and the race-safe stoppedByUser marker beside it. Any read error
    # fails closed. A known-stopped or unreadable orphan may still be resumed by
    # an explicit SendMessage, but never enters the 48-hour automatic restart
    # list. Upstream's capability-based notices and grouping remain untouched.
    edit(
        "chunk-7fv02std.js",
        [
            (
                "um,yb,bV,Vc,clt",
                "um,yb,DCn,bV,Vc,clt",
            ),
            (
                'let ie=s!==void 0&&(O.launchedByAgentTool===!0||O.launchedByForkedSkill===!0)&&N!==null&&await yb(B,y).catch(qOe("resume orphan probe"))!==null;return{mtimeMs:N,hasMeta:ie,fetchable:N===null&&clt()}',
                'let rpS=!1,ie=!1;if(N!==null)try{let[rpM,rpStop]=await Promise.all([yb(B,y),DCn(B,"stoppedByUser",y)]);rpS=rpM?.stoppedByUser===!0||rpStop,ie=s!==void 0&&(O.launchedByAgentTool===!0||O.launchedByForkedSkill===!0)&&rpM!==null}catch(rpE){qOe("resume orphan probe")(rpE),rpS=!0}return{mtimeMs:N,hasMeta:ie,fetchable:N===null&&clt(),rpStopped:rpS}',
            ),
            (
                "let{mtimeMs:N,hasMeta:ie,fetchable:Z}=S[O]??{mtimeMs:null,hasMeta:!1,fetchable:!1};",
                "let{mtimeMs:N,hasMeta:ie,fetchable:Z,rpStopped:rpS}=S[O]??{mtimeMs:null,hasMeta:!1,fetchable:!1,rpStopped:!1};",
            ),
            (
                "&&ie&&N!==null&&D-N<ei){C.push({agentId:B.agentId",
                "&&ie&&N!==null&&!rpS&&D-N<ei){C.push({agentId:B.agentId",
            ),
        ],
    )
