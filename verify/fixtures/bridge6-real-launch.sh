#!/bin/bash
# usage: launch.sh <session> <dir> [extra claude args...]
# Real user settings + hooks (no env -i, no --setting-sources). Only strips the
# variables inherited from the parent Claude session and cmux, so the child is a
# fresh top-level session like one Arthur starts in a terminal.
S="$1"; D="$2"; shift 2
UNSET=$(env | cut -d= -f1 | grep -E '^(CLAUDE|CLAUDECODE|ANTHROPIC_|CMUX|BUN_OPTIONS|RP_|TMUX)' | sed 's/^/-u /' | tr '\n' ' ')
tmux kill-session -t "$S" 2>/dev/null
env $UNSET tmux new-session -d -s "$S" -x 220 -y 60 "cd '$D' && env $UNSET '$HOME/.local/bin/claude-bridge' --debug-file '$D/debug.log' $* ; echo EXITED; sleep 600"
