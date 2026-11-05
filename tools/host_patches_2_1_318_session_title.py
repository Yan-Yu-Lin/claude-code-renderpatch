"""Keep the auto-generated tab/session title under essential-traffic mode.

2.1.318 added `!z2o()` to the haiku title gate in SessionController._runImpl,
where z2o() = St() || CLAUDE_CODE_DISABLE_TERMINAL_TITLE and St() is
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC. 2.1.291 had no such check. The title
request is a normal model call through ANTHROPIC_BASE_URL (the local proxy),
the same path as every conversation turn, so it adds no traffic to Anthropic's
telemetry/GrowthBook/update endpoints. This keeps only the explicit
CLAUDE_CODE_DISABLE_TERMINAL_TITLE opt-out; z2o() itself (used elsewhere) is
left unchanged.
"""


def patch_session_title(result, edit):
    edit(
        "chunk-p2q3ejfg.js",
        [
            (
                "if(!Oo&&!z2o()&&!Sn&&!Jo&&!Wn&&!this._haikuTitleAttempted){",
                "if(!Oo&&!i.CLAUDE_CODE_DISABLE_TERMINAL_TITLE&&!Sn&&!Jo&&!Wn&&!this._haikuTitleAttempted){",
            ),
        ],
    )
