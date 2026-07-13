#!/usr/bin/env bash
# Fire-and-forget wrapper for the Stop-hook summarizer.
#
# The Stop hook must NEVER block session exit. This reads the hook JSON from stdin,
# then hands it to the (slow, model-calling) summarizer in a detached background
# subshell and returns immediately. macOS has no `setsid`, so a backgrounded
# subshell with redirected stdio is the portable detach.
set -euo pipefail
DIR="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
payload="$(cat)"
( printf '%s' "$payload" | python3 "$DIR/hooks/stop-summarize.py" >/dev/null 2>&1 & ) >/dev/null 2>&1
exit 0
