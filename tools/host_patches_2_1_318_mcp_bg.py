"""2.1.318 MCP owner backgrounding and server progress-triggered handoff.

Applied after the core recipes to a freshly extracted, hash-pinned graph.
Server-side MCP Tasks eligibility stays unchanged. Only background callers
acquire ownership; foreground subagents keep the synchronous call path.
"""


def patch_mcp_bg(result, edit):
    for name, ctx, client, tool in (
        ("chunk-6jypdf2f.js", "b", "ut", "te"),
        ("chunk-r2ksrv9a.js", "B", "hn", "ge"),
    ):
        eligible = (
            f'(!{ctx}.agentId||PTe({ctx}.agentContext)!==void 0||'
            f'{ctx}.isBackgroundAgent||{ctx}.teammateContext!==void 0||'
            f'{ctx}.agentContext?.agentType==="in_process_teammate")'
        )
        if ctx == "b":
            old = 'if(ut&&!b.agentId&&b.taskRegistry!==TV&&te.name!==Uk())'
            new = f'if(ut&&{eligible}&&b.taskRegistry!==TV&&te.name!==Uk())'
        else:
            # Qt also gates server-side Tasks below: do not broaden Qt itself.
            old = 'if(hn&&Qt){let Nt=hn.getMcpAutoBackgroundMs'
            new = f'if(hn&&{eligible}&&B.taskRegistry!==TV&&ge.name!==Uk()){{let Nt=hn.getMcpAutoBackgroundMs'
        edit(name, [(old, new), (
            f'foregroundCalls:{ctx}.innerCall?void 0:LEe.of({ctx}.session),noticeGate:',
            f'ownerAgentId:{ctx}.agentId,foregroundCalls:{ctx}.agentId||{ctx}.innerCall?void 0:LEe.of({ctx}.session),noticeGate:',
        )])
        if ctx == "B":
            edit(name, [('if(!rn&&JA()&&!Qcs())zt=', 'if(Qt&&!rn&&JA()&&!Qcs())zt=')])

    name = "chunk-kdb20esk.js"
    edit(name, [
        ('import{Ine,N8r,dl}', 'import{Ine,N8r,dl,K3t,ucr}'),
        ('foregroundCalls:V,noticeGate:B}){if(p)', 'foregroundCalls:V,noticeGate:B,ownerAgentId:rpOwner}){if(p)'),
        ('Q=V?.add({toolUseId:u,backgroundNow:()=>{if(!C||d.signal.aborted||R?.()===!0)return!1;return C=!1,D(),!0}}),_=!1;try{',
         'rpReason, rpMove=(rpWhy)=>{if(!C||d.signal.aborted||R?.()===!0)return!1;return C=!1,rpReason=rpWhy,D(),!0},Q=V?.add({toolUseId:u,backgroundNow:()=>rpMove("message")}),_=!1;__rpMcpEarly.set(b.signal,()=>rpMove("server"));try{'),
        ('finally{C=!1,Q?.(),N.abort()}E();let P=Rnr',
         'finally{C=!1,__rpMcpEarly.delete(b.signal),Q?.(),N.abort()}E();let P=Rnr'),
        ('backgroundedToDeliverMessage:_||void 0}),{id:s,description:I}=P;T.register(P);let Z=le',
         'backgroundedToDeliverMessage:_&&rpReason!=="server"||void 0}),{id:s,description:I}=P;if(rpOwner)P.agentId=rpOwner;T.register(P);if(rpOwner)XO(rpOwner,`mcp:${s}`,T);let Z=le'),
        ('trigger:_?S("deliver_message"):S("timeout")',
         'trigger:rpReason==="server"?S("server_request"):_?S("deliver_message"):S("timeout")'),
        ('function x(n,L,oe,U,O){if(q(Z),M?.becameTask)return;',
         'function rpRelease(){WA(rpOwner,`mcp:${s}`,T)}function x(n,L,oe,U,O){q(Z);if(M?.becameTask){rpRelease();return}'),
        ('return W=!0,{...f,status:n,mcpStatus:n,statusMessage:F,endTime:Date.now(),notified:!0,abortController:void 0',
         'return W=!0,{...f,status:n,mcpStatus:n,statusMessage:F,endTime:Date.now(),notified:!0,__rpMcpNoticePending:rpOwner!==void 0,abortController:void 0'),
        ('}}),!W)return;if(n==="completed")g("mcp_auto_background")',
         '}}),!W){rpRelease();return}if(n==="completed")g("mcp_auto_background")'),
        ('let v=()=>{try{let f=Pr(r,o);Wf(f),dl(',
         'let v=()=>{let rpRecipient=K3t({ownerAgentId:rpOwner,keepaliveReason:`mcp:${s}`,delivering:!0,taskRegistry:T});try{let f=Pr(r,o);Wf(f),dl('),
        ('statusMessage:F}),toolsUsed:[f],mode:"task-notification",skipAttachments:!0,priority:"next",agentId:ot(),taskId:s}',
         'statusMessage:F}),toolsUsed:[f],mode:"task-notification",skipAttachments:!0,priority:"next",agentId:rpRecipient,taskId:s}'),
        ('value:`MCP task ${s} ${n}; the result could not be rendered.`,mode:"task-notification",skipAttachments:!0,priority:"next",agentId:ot(),taskId:s}',
         'value:`MCP task ${s} ${n}; the result could not be rendered.`,mode:"task-notification",skipAttachments:!0,priority:"next",agentId:rpRecipient,taskId:s}'),
        ('catch(ne){t(`degraded MCP task notification enqueue failed: ${String(ne)}`,{level:"error"})}}};if(B===void 0)',
         'catch(ne){t(`degraded MCP task notification enqueue failed: ${String(ne)}`,{level:"error"})}}finally{if(rpOwner){T.update(s,(rpT)=>({...rpT,__rpMcpNoticePending:!1}));if(!ucr(rpOwner,s))rpRelease()}}};if(B===void 0)'),
        ('te=_?`MCP tool "${I}" was moved to the background as task ${s} so that a message',
         'te=rpReason==="server"?`MCP tool "${I}" was moved to the background as task ${s} because the server requested backgrounding; it was not interrupted and keeps running`:_?`MCP tool "${I}" was moved to the background as task ${s} so that a message'),
        ('re=Py()?`. You can keep working in the meantime.',
         're=Py()&&!rpOwner?`. You can keep working in the meantime.'),
        ('function Ie(e,r){try{Fn().mcpCallProgress.get(e)?.(r)}catch(o){a(o)}}',
         'function Ie(e,r){try{if(r?._meta?.["claudecode/backgroundNow"]===!0)__rpMcpEarly.get(e)?.();Fn().mcpCallProgress.get(e)?.(r)}catch(o){a(o)}}'),
    ], 'import{XO,WA}from"./chunk-ygm0kzqk.js";const __rpMcpEarly=new WeakMap;')

    edit("chunk-0x9x817t.js", [
        ('if(r.startsWith("monitor:")||r.startsWith("workflow:")||nAn(r))return!0;',
         'if(r.startsWith("monitor:")||r.startsWith("workflow:")||r.startsWith("mcp:")||nAn(r))return!0;'),
        ('if(r.isBackgrounded&&(h.startsWith("workflow:")||nAn(h)))return!0;',
         'if(r.isBackgrounded&&(h.startsWith("workflow:")||h.startsWith("mcp:")||nAn(h)))return!0;'),
        ('else if(s.startsWith("bash:"))h=s.slice(5);else continue;if(ucr(e,h))continue;',
         'else if(s.startsWith("bash:"))h=s.slice(5);else if(s.startsWith("mcp:"))h=s.slice(4);else continue;if(ucr(e,h))continue;'),
        ('y.type==="local_bash"&&y.notified&&Ko(y.status))WA(e,s,n)',
         'y.type==="local_bash"&&y.notified&&Ko(y.status)||y.type==="mcp_task"&&y.notified&&!y.__rpMcpNoticePending)WA(e,s,n)'),
        ('b=Cn(h)&&(har(h)||zhe(e,s))&&ok(h)&&!ye()||Cn(h)&&h.status==="running",rpLive=',
         'b=Cn(h)&&(har(h)||zhe(e,s))&&ok(h)&&(!ye()||n.startsWith("mcp:"))||Cn(h)&&h.status==="running",rpLive='),
        ('return(Cn(y)||y?.type==="local_workflow")&&y.ownerAgentId===e});for(let h of s)dl',
         'return((Cn(y)||y?.type==="local_workflow")&&y.ownerAgentId===e)||(y?.type==="mcp_task"&&y.agentId===e)});for(let h of s)dl'),
    ])
    edit("chunk-nyc0s6f6.js", [
        ('rpT.type==="local_agent"&&rpT.status==="running"&&rpT.ownerAgentId===rpId)}',
         'rpT.status==="running"&&(rpT.type==="local_agent"&&rpT.ownerAgentId===rpId||rpT.type==="mcp_task"&&rpT.agentId===rpId))}'),
        ('fV(rpTid,a,{cause:"owner_ended"})}}Fn().killAgentMonitors',
         'fV(rpTid,a,{cause:"owner_ended"})}else if(rpT.type==="mcp_task"&&rpT.agentId===rpId){rpT.abortController?.abort()}}Fn().killAgentMonitors'),
    ])
