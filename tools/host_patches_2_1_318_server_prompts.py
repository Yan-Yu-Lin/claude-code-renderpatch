"""Block server-supplied free text from model-visible prompt channels.

The launcher can restore stock behavior with CLAUDE_BRIDGE_ALLOW_SERVER_PROMPTS=1.
Blocked text is recorded once per process/session in a user-private JSONL log.
"""


def _helper(name):
    return f'''function {name}(e,n,r){{if(process.env.CLAUDE_BRIDGE_ALLOW_SERVER_PROMPTS==="1"||typeof n!=="string"||n==="")return n;let s=globalThis.__claudeBridgeBlockedPrompts??=new Set,h=`${{e}}\\0${{n}}`;if(!s.has(h)){{s.add(h);try{{let y=import.meta.require("fs"),b=import.meta.require("path"),w=process.env.HOME||import.meta.require("os").homedir(),M=b.join(w,".local","state","claude-bridge"),x=b.join(M,"blocked-injections.jsonl");y.mkdirSync(M,{{recursive:!0,mode:448}}),y.appendFileSync(x,JSON.stringify({{timestamp:new Date().toISOString(),channel:e,model:r??process.env.ANTHROPIC_MODEL??null,text:n,pid:process.pid}})+"\\n",{{encoding:"utf8",mode:384}})}}catch{{}}}}return null}}'''


def patch_server_prompts(result, edit):
    helper = "__rpBlockPrompt0"
    edit(
        "chunk-0x9x817t.js",
        [
            (
                'function Cmr(e){if(!e)return null;return l("tengu_heron_brook_applied",{len:e.value.length,fromClientData:e.fromClientData}),e.value}',
                f'function Cmr(e,n){{if(!e)return null;let r={helper}("tengu_heron_brook",e.value,n);if(r===null)return null;return l("tengu_heron_brook_applied",{{len:r.length,fromClientData:e.fromClientData}}),r}}',
            ),
            (
                'function $mr(e){let n=gSt(),r=cS(e,n===void 0?void 0:vl(n,e)),s=Ufn(e,r);if(s===null)return null;return l("tengu_brook_heron_applied",{len:s.length,effort:ce(r)}),s}',
                f'function $mr(e){{let n=gSt(),r=cS(e,n===void 0?void 0:vl(n,e)),s=Ufn(e,r);if(s===null)return null;let h={helper}("tengu_brook_heron",s,e);if(h===null)return null;return l("tengu_brook_heron_applied",{{len:h.length,effort:ce(r)}}),h}}',
            ),
            (
                'let uo=Cmr(Re());if(uo!==null)return{kind:"served",text:uo}',
                'let uo=Cmr(Re(),h);if(uo!==null)return{kind:"served",text:uo}',
            ),
        ],
        _helper(helper),
    )

    helper = "__rpBlockPrompt1"
    edit(
        "chunk-363wfywp.js",
        [
            (
                'else{let y=q3t(s,n);if(y!==void 0)return Zm(e,y)}let h=e.modelOwn?.(et(n));',
                'else{let y=q3t(s,n);if(y!==void 0){let b=Zm(e,y,n);if(b!==null)return b}}let h=e.modelOwn?.(et(n));',
            ),
            (
                'function Zm(e,[n,r]){if(typeof r!=="string")return ql(e.clientDataKey,`value for pattern "${n}" is ${typeof r}, expected the reminder text`),null;return mi(r,"clientData",n)}',
                f'function Zm(e,[n,r],s){{if(typeof r!=="string")return ql(e.clientDataKey,`value for pattern "${{n}}" is ${{typeof r}}, expected the reminder text`),null;let h={helper}(e.clientDataKey,r,s);return h===null?null:mi(h,"clientData",n)}}',
            ),
        ],
        _helper(helper),
    )

    helper = "__rpBlockPrompt2"
    edit(
        "chunk-3xyf3gs0.js",
        [
            (
                'function gca(){let e=k("tengu_kairos_brief_stop_hook_text","");return typeof e==="string"&&e.length>0?e:r}',
                f'function gca(){{let e=k("tengu_kairos_brief_stop_hook_text","");if(typeof e==="string"&&e.length>0){{let n={helper}("tengu_kairos_brief_stop_hook_text",e);if(n!==null)return n}}return r}}',
            ),
        ],
        _helper(helper),
    )

    helper = "__rpBlockPrompt3"
    edit(
        "chunk-52mcbrhk.js",
        [
            (
                'function tt(e){let n=k("tengu_projects_thread_recap_prompt","");return typeof n==="string"&&n.trim()!==""?n:e}',
                f'function tt(e,n){{let r=k("tengu_projects_thread_recap_prompt","");if(typeof r==="string"&&r.trim()!==""){{let s={helper}("tengu_projects_thread_recap_prompt",r,n);if(s!==null)return s}}return e}}',
            ),
            (
                'text:w?tt(oe):te,cache_control:Q',
                'text:w?tt(oe,de):te,cache_control:Q',
            ),
        ],
        _helper(helper),
    )

    helper = "__rpBlockPrompt4"
    edit(
        "chunk-v5d8s1b8.js",
        [
            (
                'let q=k("tengu_cinder_plover","").trim();c=q?`\n${q}\n`:nIi}let m=k("tengu_cinder_wren",""),r=typeof m==="string"?m.trim():"",w=r?`\n${r}\n`:"",',
                f'let q=k("tengu_cinder_plover","").trim(),B={helper}("tengu_cinder_plover",q,e);c=B===null?nIi:B?`\n${{B}}\n`:nIi}}let m=k("tengu_cinder_wren",""),r=typeof m==="string"?m.trim():"",R={helper}("tengu_cinder_wren",r,e),w=R===null?"":R?`\n${{R}}\n`:"",',
            ),
        ],
        _helper(helper),
    )
