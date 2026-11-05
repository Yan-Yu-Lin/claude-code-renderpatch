#!/usr/bin/env bash
# claude-bridge (omarchy) — immutable renderpatch release through CLIProxyAPI.
# Adds the multi-provider settings overlay, proxy health check, routing note,
# and /model pollution guard. Set CLAUDE_BRIDGE_BIN=~/.local/bin/claude for
# an explicit stock fallback without changing this launcher.

set -euo pipefail

PROXY_URL="http://127.0.0.1:8317"
# claude-renderpatch-active is a symlink to the selected immutable release
# launcher; switch/rollback by atomically repointing it (see
# ~/.local/share/claude-renderpatch/selections/).
CLAUDE_BIN="${CLAUDE_BRIDGE_BIN:-$HOME/.local/bin/claude-renderpatch-active}"
SETTINGS="$HOME/.claude/settings.json"
OVERLAY="$HOME/.claude/claude-mix-settings.json"
MIX_NOTE="Model routing note: this session runs through a local multi-provider proxy (CLIProxyAPI on omarchy). All four /model slots are Anthropic models on one Claude subscription: fable = Claude Fable 5.1 (wire id claude-f51, 1M context), opus = Claude Opus 5.5 (wire id claude-o55, 1M context), sonnet = Claude Sonnet 5.5 (wire id claude-sonnet-5-5, 1M context), haiku = Claude Haiku 5.5 (wire id claude-h55, 1M context). There is no OpenAI or Kimi model behind any slot. The model id shown in your system prompt is the model actually answering. For subagents, specify the desired model alias explicitly."

[[ -x "$CLAUDE_BIN" ]] || { echo "claude-bridge: claude binary not found at $CLAUDE_BIN" >&2; exit 1; }
[[ -f "$OVERLAY" ]] || { echo "claude-bridge: settings overlay missing: $OVERLAY" >&2; exit 1; }

if [[ "${1:-}" == "--renderpatch-status" ]]; then
  exec "$CLAUDE_BIN" --renderpatch-status
fi
# Version/help probes need no proxy. T3 Code probes `--version` seconds after
# boot, before cliproxyapi (which waits for DNS) is listening; the old proxy
# check made that probe exit 1 and T3 marked the Claude provider broken.
if (($# == 1)) && [[ "$1" == "--version" || "$1" == "-v" || "$1" == "--help" || "$1" == "-h" ]]; then
  exec "$CLAUDE_BIN" "$1"
fi

proxy_alive() {
  curl -s -m 3 -o /dev/null "$PROXY_URL/" 2>/dev/null
}

if ! proxy_alive; then
  # cliproxyapi is an enabled system unit; after boot systemd brings it up on
  # its own (up to ~60 s for DNS). Wait instead of failing. Only try sudo when
  # it needs no password (no TTY under T3/SSH automation).
  state="$(systemctl show -p ActiveState --value cliproxyapi.service 2>/dev/null || true)"
  if [[ "$state" != "active" && "$state" != "activating" ]] \
     && systemctl is-enabled cliproxyapi.service >/dev/null 2>&1; then
    sudo -n systemctl start cliproxyapi.service 2>/dev/null || true
  fi
  echo "claude-bridge: waiting for cliproxyapi on $PROXY_URL ..." >&2
  for _ in $(seq 1 60); do
    proxy_alive && break
    sleep 1
  done
  proxy_alive || { echo "claude-bridge: proxy still down; check 'systemctl status cliproxyapi'" >&2; exit 1; }
fi

previous_model=""
if command -v jq >/dev/null 2>&1 && [[ -f "$SETTINGS" ]]; then
  previous_model="$(jq -r '.model // empty' "$SETTINGS" 2>/dev/null)"
fi

set +e
"$CLAUDE_BIN" \
  --settings "$OVERLAY" \
  --append-system-prompt "$MIX_NOTE" \
  "$@"
rc=$?
set -e

# Guard the shared profile: /model can save a provider-specific model into user
# settings, which would break ordinary claude launches.
if command -v jq >/dev/null 2>&1 && [[ -f "$SETTINGS" ]]; then
  new_model="$(jq -r '.model // empty' "$SETTINGS" 2>/dev/null)"
  case "$new_model" in
    gpt-*|kimi-*|k2*|k3*|grok-*|cursor*|composer-*)
      case "$previous_model" in
        gpt-*|kimi-*|k2*|k3*|grok-*|cursor*|composer-*) previous_model="" ;;
      esac
      temporary_settings="$(mktemp "$SETTINGS.claude-bridge.XXXXXX")"
      if [[ -n "$previous_model" ]]; then
        jq --arg model "$previous_model" '.model = $model' "$SETTINGS" >"$temporary_settings"
      else
        jq 'del(.model)' "$SETTINGS" >"$temporary_settings"
      fi
      chmod 600 "$temporary_settings"
      mv -f "$temporary_settings" "$SETTINGS"
      echo "claude-bridge: restored settings.json model to '${previous_model:-default}'" >&2
      ;;
  esac
fi

exit "$rc"
