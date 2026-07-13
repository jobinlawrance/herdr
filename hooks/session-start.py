#!/usr/bin/env python3
"""SessionStart inject hook: print the frozen memory snapshot into the new session.

Reads the capped working-memory file and today's dated log from the project's
`memory/` folder and writes them to stdout — Claude Code injects a SessionStart
hook's stdout into the session context. Silent and best-effort: any problem exits 0
with no output so a fresh project (no memory yet) starts cleanly.

The snapshot is deliberately READ-ONLY here (frozen for the session); writes happen
via the memory-keeper skill and the Stop hook, and take effect next session.
"""
import datetime
import json
import os
import sys


def project_dir():
    # SessionStart payload carries cwd; fall back to env / cwd.
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    return (
        data.get("cwd")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.getcwd()
    )


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""


def main():
    cwd = project_dir()
    memdir = os.path.join(cwd, "memory")
    wm = read(os.path.join(memdir, "working-memory.md"))
    today = datetime.date.today().isoformat()
    log = read(os.path.join(memdir, today + ".md"))

    if not wm and not log:
        sys.exit(0)  # nothing to inject; stay silent

    out = ["<memory-snapshot note=\"frozen for this session; edits land next session\">"]
    if wm:
        out += ["", "## Working memory", wm]
    if log:
        out += ["", "## Today's log (%s)" % today, log]
    out += ["", "</memory-snapshot>"]
    print("\n".join(out))


if __name__ == "__main__":
    main()
