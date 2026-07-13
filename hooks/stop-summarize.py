#!/usr/bin/env python3
"""Stop-hook worker: summarize last exchange into today's log, archive transcript.

Runs DETACHED (spawned with & by the Stop hook), so it must never assume the
parent is waiting. Reads the Stop-hook JSON payload on stdin.

Idempotent: each captured turn is keyed by a hash of (user+assistant) text and
written with an `<!-- auto:HASH -->` marker; re-runs that see the marker skip.

Recursion guard: summarizing calls `claude -p`, which starts a NEW session whose
Stop hook fires this worker again. We set MEMORY_STOP_HOOK=1 in that child's env
and bail at the top when it is present.
"""
import sys, os, json, hashlib, subprocess, shutil, datetime

MODEL = "claude-haiku-4-5-20251001"

# --- recursion guard: the nested `claude -p` summarizer must not re-trigger us
if os.environ.get("MEMORY_STOP_HOOK"):
    sys.exit(0)


def load_payload():
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)


def text_of(rec):
    """Return (role, joined_text) for a transcript record; text = text blocks only."""
    msg = rec.get("message") or {}
    role = msg.get("role") or rec.get("type") or ""
    content = msg.get("content")
    parts = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
    return role, "\n".join(parts).strip()


def last_exchange(transcript_path):
    """Last assistant prose + the user prose that prompted it. Skips tool-only turns."""
    recs = []
    with open(transcript_path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                recs.append(json.loads(ln))
            except Exception:
                pass
    asst = user = None
    i = len(recs) - 1
    while i >= 0:
        role, txt = text_of(recs[i])
        if role == "assistant" and txt:
            asst = txt
            break
        i -= 1
    j = i - 1
    while j >= 0:
        role, txt = text_of(recs[j])
        if role == "user" and txt:
            user = txt
            break
        j -= 1
    return user, asst


def summarize(user, asst):
    """Third-person bullets via a fast/cheap model. Fallback stays graceful."""
    claude = shutil.which("claude")
    if not claude:
        for p in ("~/.claude/local/claude", "/opt/homebrew/bin/claude",
                  "/usr/local/bin/claude"):
            p = os.path.expanduser(p)
            if os.path.exists(p):
                claude = p
                break
    prompt = (
        "Summarize the following exchange as 2-4 concise third-person bullet "
        "points (start each with '- '). Describe what the user asked and what "
        "the assistant did. No preamble, no headers.\n\n"
        "USER:\n" + user[:6000] + "\n\nASSISTANT:\n" + asst[:6000]
    )
    if claude:
        try:
            env = dict(os.environ, MEMORY_STOP_HOOK="1")
            r = subprocess.run([claude, "-p", prompt, "--model", MODEL],
                               capture_output=True, text=True, timeout=120,
                               env=env, stdin=subprocess.DEVNULL)
            out = (r.stdout or "").strip()
            if out:
                return out
        except Exception:
            pass
    # fallback: never lose the turn, even if the model is unreachable
    return "- (auto-summary unavailable) user: " + " ".join(user.split())[:140]


def append_log(cwd, user, asst, summary):
    h = hashlib.sha256((user + "\n---\n" + asst).encode("utf-8")).hexdigest()[:12]
    marker = "auto:" + h
    day = datetime.date.today().isoformat()
    logdir = os.path.join(cwd, "memory")
    os.makedirs(logdir, exist_ok=True)
    log = os.path.join(logdir, day + ".md")
    existing = ""
    if os.path.exists(log):
        with open(log) as f:
            existing = f.read()
    if marker in existing:          # idempotent: this turn already captured
        return
    block = []
    if not existing.endswith("\n") and existing:
        block.append("")
    if "## Auto-captured" not in existing:
        block.append("## Auto-captured (Stop hook)")
        block.append("<!-- Generated summaries. Safe to prune; hashes prevent dupes. -->")
        block.append("")
    ts = datetime.datetime.now().strftime("%H:%M")
    block.append("<!-- %s -->" % marker)
    for line in summary.splitlines():
        line = line.rstrip()
        if line:
            block.append(line if line.lstrip().startswith(("-", "*")) else "- " + line)
    block.append("_captured %s_" % ts)
    block.append("")
    with open(log, "a") as f:
        f.write("\n".join(block) + "\n")


def archive(cwd, payload, transcript_path):
    arcdir = os.path.join(cwd, ".claude", "transcripts")
    os.makedirs(arcdir, exist_ok=True)
    sid = payload.get("session_id") or "session"
    sid = "".join(c for c in str(sid) if c.isalnum() or c in "-_") or "session"
    try:
        shutil.copy2(transcript_path, os.path.join(arcdir, sid + ".jsonl"))
    except Exception:
        pass
    # ensure the archive folder is gitignored
    gi = os.path.join(cwd, ".gitignore")
    entry = ".claude/transcripts/"
    lines = []
    if os.path.exists(gi):
        with open(gi) as f:
            lines = f.read().splitlines()
    if entry not in lines:
        with open(gi, "a") as f:
            f.write(("" if not lines or lines[-1] == "" else "\n") + entry + "\n")


def main():
    payload = load_payload()
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    tp = payload.get("transcript_path")
    if not tp or not os.path.exists(tp):
        sys.exit(0)
    archive(cwd, payload, tp)                 # always archive, even if summary fails
    user, asst = last_exchange(tp)
    if not user or not asst:
        sys.exit(0)
    summary = summarize(user, asst)
    append_log(cwd, user, asst, summary)


if __name__ == "__main__":
    main()
