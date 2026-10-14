#!/bin/bash
# usage: launch.sh <session> <dir> <launcher> [extra claude args...]
S="$1"; D="$2"; L="$3"; shift 3
tmux kill-session -t "$S" 2>/dev/null
tmux new-session -d -s "$S" -x 220 -y 70 "cd '$D' && env -i HOME='$HOME' USER='$USER' LOGNAME='$USER' PATH='$PATH' LANG=en_US.UTF-8 TERM=xterm-256color TMPDIR='$D/tmp' CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2 '$L' --setting-sources project,local --debug-file '$D/debug.log' $* ; echo EXITED; sleep 600"
