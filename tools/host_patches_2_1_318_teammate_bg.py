# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Background Agent and Bash work for in-process teammates on 2.1.318.

The patch keeps the 2.1.291 release-.6 design: task notifications stay in
Claude Code's command queue, are owned by the teammate that launched the work,
and are folded by that teammate's normal query loop.  The runner additionally
drains the queue at turn end and while idle so a completion can wake an idle
teammate.  Esc ends only the current turn; terminal teammate exit owns child
cleanup and forwards any remaining notices to the lead.

2.1.318 moved the Agent launch decision and notification router but did not
supply teammate ownership.  Its newer generic runner keepalive predicate still
covers background shells/monitors only, so live child Agents remain an explicit
runner keepalive condition here.
"""

STOPPED_TEAMMATE_POLICY = "stop-children"

LIVE_TEAMMATE_JS = (
    "function __rpLiveTeammate(e,s){return Object.values(s.all()).some((rpT)=>"
    "rpT.type===\"in_process_teammate\"&&rpT.status===\"running\"&&"
    "(rpT.identity?.resumableAgentId??rpT.identity?.agentId)===e)}"
)

RUNNER_HELPERS = (
    "function __rpTeammateId(n){return n.resumableAgentId??n.agentId}"
    "function __rpTakeQueued(n){let rpId=__rpTeammateId(n),rpCmds=xBe((rpC)=>"
    "rpC.mode===\"task-notification\"&&rpC.agentId===rpId&&typeof rpC.value===\"string\"&&"
    "rpC.value!==\"\"&&!(rpC.uuid!==void 0&&Jes(rpC.uuid)));"
    "if(rpCmds.length===0)return null;"
    "t(`[inProcessRunner] ${n.agentName} taking ${rpCmds.length} queued task-notification(s)`);"
    "return{type:\"new_message\",message:rpCmds.map((rpC)=>rpC.value).join(`\\n\\n`),"
    "origin:{kind:\"task-notification\"},from:\"user\"}}"
    "function __rpHasLiveChildren(rpId,a){return Object.values(a.all()).some((rpT)=>"
    "rpT.type===\"local_agent\"&&rpT.status===\"running\"&&rpT.ownerAgentId===rpId)}"
)

EXIT_POLICY_JS = {
    "stop-children": (
        "function __rpTeammateExit(n,a){try{let rpId=__rpTeammateId(n);"
        "for(let[rpTid,rpT]of Object.entries(a.all())){if(rpT.status!==\"running\")continue;"
        "if(rpT.type===\"local_agent\"&&rpT.ownerAgentId===rpId){"
        "t(`[inProcessRunner] ${n.agentName} exited: stopping its background agent ${rpTid}`);"
        "rx(rpTid,a,\"parent\")}else if(rpT.type===\"local_bash\"&&rpT.agentId===rpId){"
        "t(`[inProcessRunner] ${n.agentName} exited: stopping its background shell ${rpTid}`);"
        "fV(rpTid,a,{cause:\"owner_ended\"})}}"
        "Fn().killAgentMonitors?.(Er(rpId),a);"
        "let rpLeft=xBe((rpC)=>rpC.mode===\"task-notification\"&&rpC.agentId===rpId);"
        "if(rpLeft.length>0)t(`[inProcessRunner] ${n.agentName} exited: forwarding ${rpLeft.length} queued notification(s) to the lead`);"
        "for(let rpC of rpLeft)dl({...rpC,agentId:ot()})}"
        "catch(rpE){t(`[inProcessRunner] ${n.agentName} exit cleanup failed: ${rpE}`)}}"
    ),
}


def patch_teammate_bg(result, edit):
    if STOPPED_TEAMMATE_POLICY not in EXIT_POLICY_JS:
        raise ValueError(
            f"unimplemented stopped-teammate policy: {STOPPED_TEAMMATE_POLICY}"
        )

    # T1: remove all three explicit denials, let teammate calls participate in
    # the ordinary default/fork async decision, and preserve the teammate as
    # the completion owner instead of falling back to the lead.
    edit(
        "chunk-595kpmgv.js",
        [
            (
                'if(He&&W===!0)throw m("subagent_launch","subagent_teammate_background_denied"),new Z("In-process teammates cannot spawn background agents. Use run_in_background=false for synchronous subagents.");',
                "/*rp:teammate-bg-explicit-allowed*/",
            ),
            (
                "if(He&&w.background===!0)throw m(\"subagent_launch\",\"subagent_teammate_background_denied\"),new Z(`In-process teammates cannot spawn background agents. Agent '${w.agentType}' has background: true in its definition.`);",
                "/*rp:teammate-bg-definition-allowed*/",
            ),
            (
                'if(Bt&&He&&we&&!Fe)throw m("subagent_launch","subagent_teammate_background_denied"),new Z("In-process teammates cannot spawn background agents; a plugin\'s agent.spawn hook backgrounded this one.");',
                "/*rp:teammate-bg-hook-allowed*/",
            ),
            (
                "y=s||n.callerIsHeadlessSubagent,A=n.isCoordinator&&!s||n.forceAsync||!y&&r!==!1",
                "y=n.callerIsHeadlessSubagent,A=n.isCoordinator&&!s||n.forceAsync||!y&&r!==!1",
            ),
            (
                "wn=yn&&DAt()&&!He&&!kn",
                "wn=yn&&DAt()&&!kn",
            ),
            (
                "let lt=C8(e.agentId,ge)??ot()",
                "let lt=C8(e.agentId,ge)??(He&&e.agentId!==void 0?e.agentId:ot())",
            ),
        ],
    )

    # T2: K3t is 2.1.318's completion owner router. A running teammate is a
    # valid destination even though it is not a Cn/local_agent task.
    edit(
        "chunk-0x9x817t.js",
        [
            (
                'function K3t({ownerAgentId:e,keepaliveReason:n,delivering:r,taskRegistry:s}){let h=e?s.get(e):void 0,b=Cn(h)&&(har(h)||zhe(e,s))&&ok(h)&&!ye()||Cn(h)&&h.status==="running";if(!(r&&b))WA(e,n,s);return b&&e?Er(e):ot()}',
                'function K3t({ownerAgentId:e,keepaliveReason:n,delivering:r,taskRegistry:s}){let h=e?s.get(e):void 0,b=Cn(h)&&(har(h)||zhe(e,s))&&ok(h)&&!ye()||Cn(h)&&h.status==="running",rpLive=e&&__rpLiveTeammate(e,s);if(!(r&&(b||rpLive)))WA(e,n,s);return(b||rpLive)&&e?Er(e):ot()}',
            ),
        ],
        LIVE_TEAMMATE_JS,
    )

    # T3: explicit SendMessage resume adopts the helper for a teammate caller,
    # matching the local-agent adoption path without changing observer wakes.
    edit(
        "chunk-z45ktpqq.js",
        [
            (
                'let ie=w?.kind==="observer-activity"?void 0:C8(r.agentId,R),yr=',
                'let ie=w?.kind==="observer-activity"?void 0:C8(r.agentId,R)??(r.teammateContext!==void 0&&r.agentId!==void 0?r.agentId:void 0),yr=',
            ),
        ],
    )

    # T4/T5 + terminal lifecycle: read teammate-owned task notifications while
    # idle and at turn end, keep idle teammates alive for child Agents, and run
    # the stop-children policy on both normal and exceptional runner exit.
    edit(
        "chunk-nyc0s6f6.js",
        [
            ("import{Ia,a_,bTe,p0,Sm}from", "import{Ia,a_,bTe,p0,Sm,Fn}from"),
            ("import{pfe,ye}from", "import{pfe,ye,ot}from"),
            (
                ",lTn,Vs,Ie}from",
                ",lTn,Vs,Ie,xBe,dl,Jes,rx,fV}from",
            ),
            (
                "let i=n.resumableAgentId!==void 0&&I5e(n.resumableAgentId,d),",
                "{let rpQ=__rpTakeQueued(n);if(rpQ)return rpQ}let i=n.resumableAgentId!==void 0&&(I5e(n.resumableAgentId,d)||__rpHasLiveChildren(n.resumableAgentId,d)),",
            ),
            (
                'catch(v){t(`[inProcessRunner] ${e.agentName} turn-end mailbox check failed: ${v}`)}if(o){',
                'catch(v){t(`[inProcessRunner] ${e.agentName} turn-end mailbox check failed: ${v}`)}if(!o&&!O.signal.aborted)o=__rpTakeQueued(e);if(o){',
            ),
            (
                "await xe(Ve)}let me=!1,x;",
                "await xe(Ve)}__rpTeammateExit(e,r);let me=!1,x;",
            ),
            (
                't(`[inProcessRunner] Agent ${e.agentId} failed: ${ae}`);let ie=!1,me;',
                't(`[inProcessRunner] Agent ${e.agentId} failed: ${ae}`);__rpTeammateExit(e,r);let ie=!1,me;',
            ),
        ],
        RUNNER_HELPERS + EXIT_POLICY_JS[STOPPED_TEAMMATE_POLICY],
    )

    # T6: per-turn query cleanup must not reap a teammate's shells, monitors,
    # or queued completions. The runner's terminal policy above owns teardown.
    edit(
        "chunk-56swczar.js",
        [
            (
                "&&(Vkn(me,r.taskRegistry)||I5e(me,r.taskRegistry)),Ze=",
                "&&(Vkn(me,r.taskRegistry)||I5e(me,r.taskRegistry))||Ve,Ze=",
            ),
        ],
    )

    return {
        "agent_launch": "chunk-595kpmgv.js · To/Gr · He/wn/lt",
        "owner_router": "chunk-0x9x817t.js · K3t + __rpLiveTeammate",
        "keepalive_sweeper": "chunk-0x9x817t.js · Gne (stock; agent:/workflow:/bash:)",
        "resume_adoption": "chunk-z45ktpqq.js · ie owner adoption",
        "runner": "chunk-nyc0s6f6.js · Qe/turn-end/__rpTakeQueued",
        "exit_policy": "chunk-nyc0s6f6.js · __rpTeammateExit",
        "turn_cleanup": "chunk-56swczar.js · HO cleanup xe",
        "upstream_retained": (
            "I5e already keeps idle teammates alive for running background Bash and "
            "monitor tasks; the port adds only live child-Agent eligibility"
        ),
        "upstream_shell_changes": (
            "chunk-0x9x817t.js · XXr applies the 180000ms async-subagent shell "
            "background threshold; JXr distinguishes message-arrival handoff; wDs "
            "withdraws a queued shell notice when delivered as the tool result. T6 "
            "preserves all of those stock paths."
        ),
        "upstream_dropped": "none of T1-T6 is fully supplied by 2.1.318",
    }
