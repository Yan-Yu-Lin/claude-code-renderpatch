#!/usr/bin/env bash
# Install a durable copy of the experimental latest-candidate preload launcher.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  preload/install.sh
  preload/install.sh --uninstall

Optional absolute paths under the current user's home:
  CLAUDE_PRELOAD_INSTALL_DIR
  CLAUDE_PRELOAD_LINK
EOF
}

if (($# > 1)) || (($# == 1)) && [[ "$1" != "--uninstall" ]]; then
  usage >&2
  exit 2
fi

command -v python3 >/dev/null || {
  echo "Required command not found: python3" >&2
  exit 1
}

SCRIPT_PATH="$(python3 - "$0" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
)"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
INSTALL_DIR_INPUT="${CLAUDE_PRELOAD_INSTALL_DIR:-$HOME/.local/share/claude-renderpatch/preload}"
LINK_INPUT="${CLAUDE_PRELOAD_LINK:-$HOME/.local/bin/claude-preload-lab}"
MARKER_NAME=".claude-renderpatch-preload-install"
MARKER_CONTENT="claude-code-renderpatch preload runtime v1"

normalize_home_path() {
  local kind="$1"
  local input="$2"
  local allow_final_symlink="$3"
  python3 - "$kind" "$input" "$allow_final_symlink" <<'PY'
from pathlib import Path
import os
import stat
import sys

kind, raw, allow_final_symlink = sys.argv[1:]
try:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise RuntimeError(f"{kind} must be an absolute path: {path}")
    path = Path(os.path.normpath(path))
    home = Path.home().resolve()
    if path == home or home not in path.parents:
        raise RuntimeError(f"{kind} must live below the current user's home: {path}")

    uid = os.getuid()
    current = home
    parts = path.relative_to(home).parts
    for index, part in enumerate(parts):
        current /= part
        is_final = index == len(parts) - 1
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            if is_final and allow_final_symlink == "1":
                continue
            raise RuntimeError(f"{kind} path component must not be a symlink: {current}")
        if info.st_uid != uid:
            raise RuntimeError(f"{kind} path component is not user-owned: {current}")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise RuntimeError(f"{kind} path component is group/world writable: {current}")
    print(path)
except (OSError, RuntimeError, ValueError) as error:
    raise SystemExit(str(error))
PY
}

INSTALL_DIR="$(normalize_home_path "Install directory" "$INSTALL_DIR_INPUT" 0)"
LINK="$(normalize_home_path "Launcher link" "$LINK_INPUT" 1)"
INSTALLED_WRAPPER="$INSTALL_DIR/claude-preload-lab"
MARKER="$INSTALL_DIR/$MARKER_NAME"

if [[ "$INSTALL_DIR" == *[[:space:]]* ]]; then
  echo "Install directory cannot contain whitespace in this experiment: $INSTALL_DIR" >&2
  exit 1
fi

validate_existing_link() {
  if [[ ! -e "$LINK" && ! -L "$LINK" ]]; then
    return
  fi
  if [[ ! -L "$LINK" ]]; then
    echo "Refusing to replace a non-symlink: $LINK" >&2
    exit 1
  fi
  local existing
  existing="$(python3 - "$LINK" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
)"
  if [[ "$existing" != "$INSTALLED_WRAPPER" ]]; then
    echo "Refusing to replace a symlink to another target: $LINK -> $existing" >&2
    exit 1
  fi
}

validate_managed_install_dir() {
  local allow_empty="$1"
  if [[ ! -e "$INSTALL_DIR" ]]; then
    return
  fi
  if [[ -L "$INSTALL_DIR" || ! -d "$INSTALL_DIR" ]]; then
    echo "Refusing non-directory or symlink install path: $INSTALL_DIR" >&2
    exit 1
  fi
  python3 - "$INSTALL_DIR" "$MARKER_NAME" "$MARKER_CONTENT" "$allow_empty" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
marker_name, expected, allow_empty = sys.argv[2:]
entries = {entry.name for entry in root.iterdir()}
allowed = {"claude-preload-lab", "bootstrap.mjs", marker_name}
if not entries and allow_empty == "1":
    raise SystemExit
marker = root / marker_name
if not marker.is_file() or marker.read_text(encoding="utf-8").rstrip("\n") != expected:
    raise SystemExit(f"Refusing unrecognized install directory without the expected marker: {root}")
unexpected = sorted(entries - allowed)
if unexpected:
    raise SystemExit(
        f"Refusing install directory containing unmanaged files: {root}: {', '.join(unexpected)}"
    )
PY
}

validate_existing_link

if [[ "${1:-}" == "--uninstall" ]]; then
  command -v trash >/dev/null || {
    echo "Required command not found: trash" >&2
    exit 1
  }
  validate_managed_install_dir 0
  paths=()
  [[ ! -e "$LINK" && ! -L "$LINK" ]] || paths+=("$LINK")
  [[ ! -e "$INSTALL_DIR" ]] || paths+=("$INSTALL_DIR")
  ((${#paths[@]} == 0)) || trash "${paths[@]}"
  echo "Removed experimental preload launcher files."
  exit 0
fi

validate_managed_install_dir 1
(umask 077; mkdir -p -- "$INSTALL_DIR" "$(dirname "$LINK")")
# Recheck after creation so the process umask and any path race cannot leave writable parents.
normalize_home_path "Install directory" "$INSTALL_DIR" 0 >/dev/null
normalize_home_path "Launcher link" "$LINK" 1 >/dev/null
chmod 700 "$INSTALL_DIR"

WRAPPER_TMP="$INSTALL_DIR/.claude-preload-lab.$$"
BOOTSTRAP_TMP="$INSTALL_DIR/.bootstrap.mjs.$$"
MARKER_TMP="$INSTALL_DIR/.$MARKER_NAME.$$"
cleanup() {
  paths=()
  [[ ! -e "$WRAPPER_TMP" ]] || paths+=("$WRAPPER_TMP")
  [[ ! -e "$BOOTSTRAP_TMP" ]] || paths+=("$BOOTSTRAP_TMP")
  [[ ! -e "$MARKER_TMP" ]] || paths+=("$MARKER_TMP")
  if ((${#paths[@]} > 0)); then
    if command -v trash >/dev/null; then
      trash "${paths[@]}"
    else
      for path in "${paths[@]}"; do mv "$path" "$path.abandoned"; done
    fi
  fi
}
trap cleanup EXIT

install -m 0755 "$SCRIPT_DIR/claude-preload-lab" "$WRAPPER_TMP"
install -m 0644 "$SCRIPT_DIR/bootstrap.mjs" "$BOOTSTRAP_TMP"
printf '%s\n' "$MARKER_CONTENT" >"$MARKER_TMP"
chmod 0600 "$MARKER_TMP"
mv -f "$WRAPPER_TMP" "$INSTALLED_WRAPPER"
mv -f "$BOOTSTRAP_TMP" "$INSTALL_DIR/bootstrap.mjs"
mv -f "$MARKER_TMP" "$MARKER"
ln -sfn "$INSTALLED_WRAPPER" "$LINK"

echo "Installed experimental launcher: $LINK -> $INSTALLED_WRAPPER"
echo "Runtime files: $INSTALL_DIR"
echo "It does not modify claude, claude-mix, settings, or installed Claude binaries."
echo "Try: $LINK --renderpatch-status"
echo "Remove later with: $SCRIPT_PATH --uninstall"
