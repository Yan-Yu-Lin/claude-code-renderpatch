#!/bin/bash
# usage: send.sh <session> <prompt-file>
tmux load-buffer -b p "$2" && tmux paste-buffer -p -b p -t "$1" && sleep 1 && tmux send-keys -t "$1" Enter
