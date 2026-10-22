#!/usr/bin/env bash
# Used by Claude Code, OpenCode, and Codex project configs.
# playwright-mcp and Chromium are provided by the project devShell.
set -euo pipefail

# MCP clients may pass a minimal environment. ALSA's PipeWire backend needs
# the desktop user's runtime directory to find its real playback server.
if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
  runtime_directory="/run/user/$(id -u)"
  if [[ -d "$runtime_directory" && -O "$runtime_directory" ]]; then
    export XDG_RUNTIME_DIR="$runtime_directory"
  fi
fi

if ! command -v playwright-mcp >/dev/null 2>&1; then
  echo "playwright-mcp is not available; enter the devshell first (direnv allow)." >&2
  exit 1
fi

if [[ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" ]]; then
  echo "PLAYWRIGHT_BROWSERS_PATH is not set; enter the devshell first (direnv allow)." >&2
  exit 1
fi

chromes=("$PLAYWRIGHT_BROWSERS_PATH"/chromium-*/chrome-linux64/chrome)
if [[ ! -x "${chromes[0]}" ]]; then
  echo "No chromium binary under $PLAYWRIGHT_BROWSERS_PATH" >&2
  exit 1
fi

exec playwright-mcp --executable-path "${chromes[0]}" "$@"
