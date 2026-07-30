#!/usr/bin/env bash
# Install the immutable Claude Code 2.1.220 internal-SDK candidate release.

set -euo pipefail

RELEASE_ID="2.1.220-internal-sdk-2.1.220.1-97dfb182"
TARGET_SHA256="97dfb1826861b90c8711dfe054a8f2f212b7299ea77bce7c6d724a8f12bc1157"
BOOTSTRAP_SHA256="cc18598a53576f74ac6cd493377e9b8b277a47821f044890cd129717002a916f"
SHARED_EXTENSION_SHA256="3ac015a3765800e843377008266cc548c4ccf145c6494a667110a8b6d06e658c"
DEFAULT_EXTENSION_SHA256="36bc0a4d709327dcd9b10905c8bcac65c9e2e1b3290e64982ef95210f31d59ac"
DIAGNOSTIC_EXTENSION_SHA256="d78a89d6e0c466f4816efa654fb35831160354637218e8c722379b4849b18641"
TRUST_HELPER_SHA256="72fd2d30e9ea844c03e3bf19dc19cc2f56b16748f63a84958a6a2291357d877c"
INTERNAL_MANIFEST_SHA256="f31b8409c35220209161ecdcdc8b6aff8a7f5af7535033df62ef333589836f05"
RELEASE_MANIFEST_SHA256="c3623177141eff845f2f264281c84efb9db513ffbc7dd3d631c50a0f64f7c192"
LAUNCHER_SHA256="bde3b01a00995a830dc313dc4ad06aed222a2c976a9fabaea49427b6c9911223"
MARKER_NAME=".claude-renderpatch-release"
MARKER_CONTENT="$RELEASE_ID $RELEASE_MANIFEST_SHA256"

usage() {
  cat <<'EOF'
Usage:
  candidate/install.sh
  candidate/install.sh --verify
  candidate/install.sh --uninstall

Optional absolute paths below the current user's home:
  CLAUDE_RENDERPATCH_RELEASE_DIR
  CLAUDE_RENDERPATCH_LINK
EOF
}

if (($# > 1)); then usage >&2; exit 2; fi
case "${1:-}" in
  ""|--verify|--uninstall) ;;
  *) usage >&2; exit 2 ;;
esac

for command_name in python3 shasum codesign; do
  command -v "$command_name" >/dev/null || {
    echo "candidate/install.sh: required command not found: $command_name" >&2
    exit 1
  }
done

SCRIPT_PATH="$(python3 - "$0" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
)"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RELEASE_DIR_INPUT="${CLAUDE_RENDERPATCH_RELEASE_DIR:-$HOME/.local/share/claude-renderpatch/releases/$RELEASE_ID}"
LINK_INPUT="${CLAUDE_RENDERPATCH_LINK:-$HOME/.local/bin/claude-renderpatch-candidate}"

SOURCE_TARGET="$REPO_ROOT/patched/claude-2.1.220-semantic-bridge-prototype"
SOURCE_BOOTSTRAP="$REPO_ROOT/preload/bootstrap.mjs"
SOURCE_SHARED_EXTENSION="$REPO_ROOT/preload/extensions/_shared.mjs"
SOURCE_DEFAULT_EXTENSION="$REPO_ROOT/preload/extensions/default.mjs"
SOURCE_DIAGNOSTIC_EXTENSION="$SCRIPT_DIR/diagnostic.mjs"
SOURCE_TRUST_HELPER="$SCRIPT_DIR/trust-file.py"
SOURCE_INTERNAL_MANIFEST="$REPO_ROOT/manifests/internal-sdk-2.1.220.json"
SOURCE_RELEASE_MANIFEST="$SCRIPT_DIR/release-manifest.json"
SOURCE_LAUNCHER="$SCRIPT_DIR/claude-renderpatch-candidate"

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
        raise RuntimeError(f"{kind} must be absolute: {path}")
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
            raise RuntimeError(f"{kind} component must not be a symlink: {current}")
        if info.st_uid != uid:
            raise RuntimeError(f"{kind} component is not user-owned: {current}")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise RuntimeError(f"{kind} component is group/world writable: {current}")
    print(path)
except (OSError, RuntimeError, ValueError) as error:
    raise SystemExit(str(error))
PY
}

RELEASE_DIR="$(normalize_home_path "Release directory" "$RELEASE_DIR_INPUT" 0)"
LINK="$(normalize_home_path "Candidate launcher link" "$LINK_INPUT" 1)"
LINK_TARGET="$RELEASE_DIR/claude-renderpatch-candidate"

sha256() {
  shasum -a 256 "$1" | cut -d ' ' -f 1
}

verify_hash() {
  local label="$1"
  local path="$2"
  local expected="$3"
  if [[ -L "$path" || ! -f "$path" ]]; then
    echo "candidate/install.sh: $label is missing, not regular, or a symlink: $path" >&2
    exit 1
  fi
  local actual
  actual="$(sha256 "$path")"
  if [[ "$actual" != "$expected" ]]; then
    echo "candidate/install.sh: $label SHA-256 mismatch" >&2
    echo "  expected: $expected" >&2
    echo "  actual:   $actual" >&2
    exit 1
  fi
}

verify_sources() {
  verify_hash "source candidate" "$SOURCE_TARGET" "$TARGET_SHA256"
  verify_hash "source bootstrap" "$SOURCE_BOOTSTRAP" "$BOOTSTRAP_SHA256"
  verify_hash "source shared extension" "$SOURCE_SHARED_EXTENSION" "$SHARED_EXTENSION_SHA256"
  verify_hash "source default extension" "$SOURCE_DEFAULT_EXTENSION" "$DEFAULT_EXTENSION_SHA256"
  verify_hash "source diagnostic extension" "$SOURCE_DIAGNOSTIC_EXTENSION" "$DIAGNOSTIC_EXTENSION_SHA256"
  verify_hash "source trusted file helper" "$SOURCE_TRUST_HELPER" "$TRUST_HELPER_SHA256"
  verify_hash "source internal SDK manifest" "$SOURCE_INTERNAL_MANIFEST" "$INTERNAL_MANIFEST_SHA256"
  verify_hash "source release manifest" "$SOURCE_RELEASE_MANIFEST" "$RELEASE_MANIFEST_SHA256"
  verify_hash "source launcher" "$SOURCE_LAUNCHER" "$LAUNCHER_SHA256"
  codesign --verify --strict "$SOURCE_TARGET" 2>/dev/null || {
    echo "candidate/install.sh: source candidate signature verification failed" >&2
    exit 1
  }
  local reported_version
  reported_version="$("$SOURCE_TARGET" --version)"
  [[ "$reported_version" == "2.1.220 (Claude Code)" ]] || {
    echo "candidate/install.sh: source candidate version mismatch: $reported_version" >&2
    exit 1
  }
}

verify_release() {
  if [[ -L "$RELEASE_DIR" || ! -d "$RELEASE_DIR" ]]; then
    echo "candidate/install.sh: immutable release directory is unavailable: $RELEASE_DIR" >&2
    exit 1
  fi
  python3 - "$RELEASE_DIR" "$MARKER_NAME" "$MARKER_CONTENT" <<'PY'
from pathlib import Path
import os
import stat
import sys

root = Path(sys.argv[1])
marker_name, marker_content = sys.argv[2:]
uid = os.getuid()
expected_entries = {
    marker_name,
    "bootstrap.mjs",
    "claude-2.1.220-internal-sdk",
    "claude-renderpatch-candidate",
    "extensions",
    "helpers",
    "manifests",
    "release-manifest.json",
}
entries = {entry.name for entry in root.iterdir()}
if entries != expected_entries:
    raise SystemExit(
        f"Refusing release with unexpected entries: expected {sorted(expected_entries)}, "
        f"found {sorted(entries)}"
    )
extensions = root / "extensions"
helpers = root / "helpers"
manifests = root / "manifests"
if extensions.is_symlink() or not extensions.is_dir():
    raise SystemExit(f"Invalid extensions directory: {extensions}")
if helpers.is_symlink() or not helpers.is_dir():
    raise SystemExit(f"Invalid helpers directory: {helpers}")
if manifests.is_symlink() or not manifests.is_dir():
    raise SystemExit(f"Invalid manifests directory: {manifests}")
expected_extensions = {"_shared.mjs", "default.mjs", "diagnostic.mjs"}
found_extensions = {entry.name for entry in extensions.iterdir()}
if found_extensions != expected_extensions:
    raise SystemExit(
        f"Refusing unexpected extension entries: expected {sorted(expected_extensions)}, "
        f"found {sorted(found_extensions)}"
    )
expected_helpers = {"trust-file.py"}
found_helpers = {entry.name for entry in helpers.iterdir()}
if found_helpers != expected_helpers:
    raise SystemExit(
        f"Refusing unexpected helper entries: expected {sorted(expected_helpers)}, "
        f"found {sorted(found_helpers)}"
    )
expected_manifests = {"internal-sdk-2.1.220.json"}
found_manifests = {entry.name for entry in manifests.iterdir()}
if found_manifests != expected_manifests:
    raise SystemExit(
        f"Refusing unexpected manifest entries: expected {sorted(expected_manifests)}, "
        f"found {sorted(found_manifests)}"
    )
marker = root / marker_name
if marker.read_text(encoding="utf-8").rstrip("\n") != marker_content:
    raise SystemExit(f"Release marker mismatch: {marker}")
expected_modes = {
    root: 0o555,
    extensions: 0o555,
    helpers: 0o555,
    manifests: 0o555,
    root / "claude-2.1.220-internal-sdk": 0o555,
    root / "claude-renderpatch-candidate": 0o555,
    root / "bootstrap.mjs": 0o444,
    root / "release-manifest.json": 0o444,
    marker: 0o444,
    extensions / "_shared.mjs": 0o444,
    extensions / "default.mjs": 0o444,
    extensions / "diagnostic.mjs": 0o444,
    helpers / "trust-file.py": 0o444,
    manifests / "internal-sdk-2.1.220.json": 0o444,
}
for path, expected_mode in expected_modes.items():
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise SystemExit(f"Immutable release contains a symlink: {path}")
    if info.st_uid != uid:
        raise SystemExit(f"Immutable release path is not user-owned: {path}")
    actual_mode = stat.S_IMODE(info.st_mode)
    if actual_mode != expected_mode:
        raise SystemExit(
            f"Immutable release mode mismatch: {path}: "
            f"expected {oct(expected_mode)}, found {oct(actual_mode)}"
        )
PY
  verify_hash "installed candidate" "$RELEASE_DIR/claude-2.1.220-internal-sdk" "$TARGET_SHA256"
  verify_hash "installed bootstrap" "$RELEASE_DIR/bootstrap.mjs" "$BOOTSTRAP_SHA256"
  verify_hash "installed shared extension" "$RELEASE_DIR/extensions/_shared.mjs" "$SHARED_EXTENSION_SHA256"
  verify_hash "installed default extension" "$RELEASE_DIR/extensions/default.mjs" "$DEFAULT_EXTENSION_SHA256"
  verify_hash "installed diagnostic extension" "$RELEASE_DIR/extensions/diagnostic.mjs" "$DIAGNOSTIC_EXTENSION_SHA256"
  verify_hash "installed trusted file helper" "$RELEASE_DIR/helpers/trust-file.py" "$TRUST_HELPER_SHA256"
  verify_hash "installed internal SDK manifest" "$RELEASE_DIR/manifests/internal-sdk-2.1.220.json" "$INTERNAL_MANIFEST_SHA256"
  verify_hash "installed release manifest" "$RELEASE_DIR/release-manifest.json" "$RELEASE_MANIFEST_SHA256"
  verify_hash "installed launcher" "$RELEASE_DIR/claude-renderpatch-candidate" "$LAUNCHER_SHA256"
  codesign --verify --strict "$RELEASE_DIR/claude-2.1.220-internal-sdk" 2>/dev/null || {
    echo "candidate/install.sh: installed candidate signature verification failed" >&2
    exit 1
  }
}

validate_link() {
  if [[ ! -e "$LINK" && ! -L "$LINK" ]]; then return; fi
  if [[ ! -L "$LINK" ]]; then
    echo "candidate/install.sh: refusing to replace non-symlink launcher: $LINK" >&2
    exit 1
  fi
  local actual_target
  actual_target="$(python3 - "$LINK" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
)"
  if [[ "$actual_target" != "$LINK_TARGET" ]]; then
    echo "candidate/install.sh: refusing launcher symlink to another target: $LINK -> $actual_target" >&2
    exit 1
  fi
}

validate_link

if [[ "${1:-}" == "--uninstall" ]]; then
  command -v trash >/dev/null || {
    echo "candidate/install.sh: required command not found: trash" >&2
    exit 1
  }
  verify_release
  paths=()
  [[ ! -e "$LINK" && ! -L "$LINK" ]] || paths+=("$LINK")
  chmod -R u+w "$RELEASE_DIR"
  paths+=("$RELEASE_DIR")
  trash "${paths[@]}"
  for path in "${paths[@]}"; do
    if [[ -e "$path" || -L "$path" ]]; then
      echo "candidate/install.sh: uninstall did not remove managed path: $path" >&2
      exit 1
    fi
  done
  echo "Removed immutable Claude renderpatch candidate release."
  exit 0
fi

if [[ "${1:-}" == "--verify" ]]; then
  verify_release
  echo "Verified immutable Claude renderpatch candidate release: $RELEASE_DIR"
  exit 0
fi

verify_sources
(umask 077; mkdir -p -- "$(dirname "$RELEASE_DIR")" "$(dirname "$LINK")")
normalize_home_path "Release directory" "$RELEASE_DIR" 0 >/dev/null
normalize_home_path "Candidate launcher link" "$LINK" 1 >/dev/null

if [[ -e "$RELEASE_DIR" || -L "$RELEASE_DIR" ]]; then
  verify_release
else
  staging="$(mktemp -d "$(dirname "$RELEASE_DIR")/.$RELEASE_ID.staging.XXXXXX")"
  cleanup() {
    local rc=$?
    trap - EXIT
    if [[ -n "${staging:-}" && -e "$staging" ]]; then
      chmod -R u+w "$staging" 2>/dev/null || true
      if command -v trash >/dev/null; then
        trash "$staging" || mv "$staging" "$staging.abandoned"
      else
        mv "$staging" "$staging.abandoned"
      fi
    fi
    exit "$rc"
  }
  trap cleanup EXIT

  mkdir "$staging/extensions" "$staging/helpers" "$staging/manifests"
  install -m 0555 "$SOURCE_TARGET" "$staging/claude-2.1.220-internal-sdk"
  install -m 0555 "$SOURCE_LAUNCHER" "$staging/claude-renderpatch-candidate"
  install -m 0444 "$SOURCE_BOOTSTRAP" "$staging/bootstrap.mjs"
  install -m 0444 "$SOURCE_SHARED_EXTENSION" "$staging/extensions/_shared.mjs"
  install -m 0444 "$SOURCE_DEFAULT_EXTENSION" "$staging/extensions/default.mjs"
  install -m 0444 "$SOURCE_DIAGNOSTIC_EXTENSION" "$staging/extensions/diagnostic.mjs"
  install -m 0444 "$SOURCE_TRUST_HELPER" "$staging/helpers/trust-file.py"
  install -m 0444 "$SOURCE_INTERNAL_MANIFEST" "$staging/manifests/internal-sdk-2.1.220.json"
  install -m 0444 "$SOURCE_RELEASE_MANIFEST" "$staging/release-manifest.json"
  printf '%s\n' "$MARKER_CONTENT" >"$staging/$MARKER_NAME"
  chmod 0444 "$staging/$MARKER_NAME"
  chmod 0555 "$staging/extensions" "$staging/helpers" "$staging/manifests"
  mv "$staging" "$RELEASE_DIR"
  staging=""
  chmod 0555 "$RELEASE_DIR"
  trap - EXIT
  verify_release
fi

ln -sfn "$LINK_TARGET" "$LINK"

echo "Installed immutable Claude renderpatch candidate: $RELEASE_DIR"
echo "Launcher: $LINK -> $LINK_TARGET"
echo "Status: $LINK --renderpatch-status"
echo "Safe exact target: $LINK --renderpatch-safe --version"
