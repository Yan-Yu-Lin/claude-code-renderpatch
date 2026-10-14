"""Background work for in-process teammates in the official 2.1.291 graph.

Semantic anchors, not portable minified names:
* Agent tool call(): three "In-process teammates cannot spawn background
  agents" throws; the foreground/background decider's
  `callerIsInProcessTeammate` suppression; fork mode's forceAsync `!ke`; and
  the completion owner `t3(parentAgentId) ?? mainSessionId`.
* enqueueAgentNotification's owner router (`keepaliveReason` /
  `delivering`): only a local_agent owner is routable, else the lead.
* in-process runner: idle poll (pendingUserMessages -> keepalive -> mailbox),
  "turn-end mailbox check failed", and the two terminal exits (`aOe(id)`).
* runAgent cleanup: keepalive-gated "nonShellMonitors"/"shellTasks" stages,
  whose shellTasks stage also drops every queued notification for the agent.
* resume engine: owner adoption `t3(caller)` when an agent resumes another.

Delivery path (no mailbox write, no provenance ledger involved): every
teammate turn is a `pk()` query loop whose per-tool-round attachment step
already folds queued task-notifications whose agentId is the loop's own
agentId (= identity.resumableAgentId). Routing the owner to the teammate
therefore delivers at its next tool round natively. The runner never reads
that queue while idle or at turn end; T4/T5 add that, which also wakes an
idle teammate. Background Bash already carries the teammate's agentId, so the
same fix covers it.

Lifecycle: a turn interrupt (Esc) is not a stop, so per-turn cleanup no longer
kills a teammate's shells/monitors (T6). When the teammate's runner really
exits (kill, TaskStop, approved shutdown, idle-timeout reap), the policy block
STOPPED_TEAMMATE_POLICY decides what happens to its live background children.
"""

# Policy for children of a teammate whose runner has exited.
#   "stop-children": stop its running background agents/shells/monitors and
#       hand any still-queued notifications for it to the lead (stock Fke()
#       semantics for local agents). Nothing is orphaned or lost.
#   "revive": not implemented yet (needs a wake that resumes the stopped
#       teammate with the queued notification; see the port notes).
STOPPED_TEAMMATE_POLICY = "stop-children"

EXIT_POLICY_JS = {
    "stop-children": (
        "function __rpTeammateExit(n,a){try{let rpId=__rpTeammateId(n);"
        "for(let[rpTid,rpT]of Object.entries(a.all())){if(rpT.status!==\"running\")continue;"
        "if(rpT.type===\"local_agent\"&&rpT.ownerAgentId===rpId){"
        "t(`[inProcessRunner] ${n.agentName} exited: stopping its background agent ${rpTid}`);_A(rpTid,a,\"parent\")}"
        "else if(Hu(rpT)&&rpT.agentId===rpId){"
        "t(`[inProcessRunner] ${n.agentName} exited: stopping its background shell ${rpTid}`);t$(rpTid,a)}}"
        "er().killAgentMonitors?.(rpId,a);"
        "let rpLeft=xht((rpC)=>rpC.mode===\"task-notification\"&&rpC.agentId===rpId);"
        "if(rpLeft.length>0)t(`[inProcessRunner] ${n.agentName} exited: forwarding ${rpLeft.length} queued notification(s) to the lead`);"
        "for(let rpC of rpLeft)Yi({...rpC,agentId:rpLeadId()})}"
        "catch(rpE){t(`[inProcessRunner] ${n.agentName} exit cleanup failed: ${rpE}`)}}"
    ),
}

RUNNER_HELPERS = (
    "function __rpTeammateId(n){return n.resumableAgentId??n.agentId}"
    "function __rpTakeQueued(n){let rpId=__rpTeammateId(n),rpQ=uy(),"
    "rpCmds=rpQ.getCommandQueue().filter((rpC)=>rpC.mode===\"task-notification\"&&rpC.agentId===rpId&&"
    "typeof rpC.value===\"string\"&&rpC.value!==\"\"&&!(rpC.uuid!==void 0&&rpQ.isFoldInFlight(rpC.uuid)));"
    "if(rpCmds.length===0)return null;rpQ.consume(rpCmds,{reason:\"delivered_to_agent\"});"
    "t(`[inProcessRunner] ${n.agentName} taking ${rpCmds.length} queued task-notification(s)`);"
    "return{type:\"new_message\",message:rpCmds.map((rpC)=>rpC.value).join(`\n\n`),"
    "origin:{kind:\"task-notification\"},from:\"user\"}}"
    "function __rpHasLiveChildren(rpId,a){return Object.values(a.all()).some((rpT)=>"
    "rpT.type===\"local_agent\"&&rpT.status===\"running\"&&rpT.ownerAgentId===rpId)}"
)

LIVE_TEAMMATE_JS = (
    "function __rpLiveTeammate(e,s){return Object.values(s.all()).some((rpT)=>"
    "rpT.type===\"in_process_teammate\"&&rpT.status===\"running\"&&"
    "(rpT.identity?.resumableAgentId??rpT.identity?.agentId)===e)}"
)


def patch_teammate_bg(result, edit):
    if STOPPED_TEAMMATE_POLICY not in EXIT_POLICY_JS:
        raise ValueError(f"unimplemented stopped-teammate policy: {STOPPED_TEAMMATE_POLICY}")
    # T1: Agent tool. Allow background launches from a teammate, let the
    # default/fork-mode background apply to it like to the lead, and make the
    # teammate itself the owner of what it launches.
    edit(
        "chunk-s6pn7fn6.js",
        [
            (
                'if(ke&&K===!0)throw m("subagent_launch","subagent_teammate_background_denied"),'
                'new C("In-process teammates cannot spawn background agents. Use run_in_background=false for synchronous subagents.");',
                "/*rp:teammate-bg-allowed*/",
            ),
            (
                'if(ke&&s.background===!0)throw m("subagent_launch","subagent_teammate_background_denied"),'
                "new C(`In-process teammates cannot spawn background agents. Agent '${s.agentType}' has background: true in its definition.`);",
                "/*rp:teammate-bg-definition-allowed*/",
            ),
            (
                'if(ft&&ke&&X&&!ye)throw m("subagent_launch","subagent_teammate_background_denied"),'
                "new C(\"In-process teammates cannot spawn background agents; a plugin's agent.spawn hook backgrounded this one.\");",
                "/*rp:teammate-bg-hook-allowed*/",
            ),
            (
                "h=g||n.callerIsHeadlessSubagent,S=n.isCoordinator&&!g||n.forceAsync||!h&&p!==!1,",
                "h=n.callerIsHeadlessSubagent,S=n.isCoordinator&&!g||n.forceAsync||!h&&p!==!1,",
            ),
            ("Yt=Vt&&!ke&&!Kt,", "Yt=Vt&&!Kt,"),
            ("et=t3(Ie,j)??ze(),", "et=t3(Ie,j)??(ke&&Ie!==void 0?Ie:ze()),"),
        ],
    )
    # T2: owner router. A live (status running, idle or busy) teammate owner
    # keeps the notification; an exited one falls back to the lead.
    edit(
        "chunk-v1gtm86q.js",
        [
            (
                "if(!(r&&b))Xx(e,n,s);return b&&e?yo(e):ze()}",
                "if(!(r&&b))Xx(e,n,s);return b&&e?yo(e):e&&__rpLiveTeammate(e,s)?yo(e):ze()}",
            ),
        ],
        LIVE_TEAMMATE_JS,
    )
    # T3: a teammate that resumes one of its finished helpers via SendMessage
    # adopts it, exactly as a local agent caller already does.
    edit(
        "chunk-ebe4qw6e.js",
        [
            (
                'N=g?.kind==="observer-activity"?void 0:t3(s.agentId,u),',
                'N=g?.kind==="observer-activity"?void 0:t3(s.agentId,u)??(s.teammateContext!==void 0&&s.agentId!==void 0?s.agentId:void 0),',
            ),
        ],
    )
    # T4-T5 + exit policy: runner reads its own queued notifications while
    # idle (wake) and at turn end, stays alive while background agents it owns
    # run, and applies the stopped-teammate policy on exit.
    edit(
        "chunk-zg4dkp5j.js",
        [
            ("JQ,wGr,hs,Re}from\"", "JQ,wGr,hs,Re,uy,xht,Yi,_A,t$,Hu}from\""),
            ("import{C7,ve}from\"", "import{C7,ve,ze as rpLeadId}from\""),
            ("import{Bi,jg,VA,ku}from\"", "import{Bi,jg,VA,ku,er}from\""),
            (
                "let o=n.resumableAgentId!==void 0&&bPe(n.resumableAgentId,a),",
                "{let rpQ=__rpTakeQueued(n);if(rpQ)return d2n(s,Re({content:rpQ.message,origin:rpQ.origin}),a),rpQ}"
                "let o=n.resumableAgentId!==void 0&&(bPe(n.resumableAgentId,a)||__rpHasLiveChildren(n.resumableAgentId,a)),",
            ),
            (
                "turn-end mailbox check failed: ${w}`)}if(r){",
                "turn-end mailbox check failed: ${w}`)}"
                "if(!r&&!O.signal.aborted&&(r=__rpTakeQueued(e)))d2n(s,Re({content:r.message,origin:r.origin}),l);if(r){",
            ),
            ("if(aOe(e.agentId),$e)", "if(__rpTeammateExit(e,l),aOe(e.agentId),$e)"),
            (
                'return aOe(e.agentId),m("swarm_in_process_run"',
                'return __rpTeammateExit(e,l),aOe(e.agentId),m("swarm_in_process_run"',
            ),
        ],
        RUNNER_HELPERS + EXIT_POLICY_JS[STOPPED_TEAMMATE_POLICY],
    )
    # T6: a teammate turn ending (normally or by Esc) is not the teammate
    # exiting: keep its shells/monitors and their queued notifications. The
    # runner exit policy owns that cleanup.
    edit(
        "chunk-g2d84gj0.js",
        [
            (
                "let C=g&&Jt&&!we.signal.aborted&&(ijo(se,n.taskRegistry)||bPe(se,n.taskRegistry)),",
                "let C=g&&Jt&&!we.signal.aborted&&(ijo(se,n.taskRegistry)||bPe(se,n.taskRegistry))||fo!==void 0,",
            ),
        ],
    )
