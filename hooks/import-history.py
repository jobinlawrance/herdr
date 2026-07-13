#!/usr/bin/env python3
"""One-time historical import of Claude Code session history into dated memory logs.

Walks existing Claude Code transcripts for THIS project, extracts every meaningful
user/assistant exchange the *same way* the Stop hook does (text blocks only, tool-only
turns skipped), summarizes each into third-person bullets, and appends them to the dated
log for the exchange's OWN date (backfill), then hands them to the indexer.

Guarded by a sentinel file (`.claude/.history-imported`) so it runs exactly once.
Idempotent regardless: each turn is keyed by the same `auto:HASH` marker the Stop hook
uses, so turns already captured live are skipped and a partial run is safe to resume.

Extraction/summary/marker logic is kept deliberately identical to
`.claude/hooks/stop-summarize.py` so imported history is indistinguishable from
hook-captured history.

Run is EXPENSIVE (one cheap-model call per turn). Safe defaults: use --dry-run first,
--limit to cap, --force to ignore the sentinel. Indexing is deferred until the mem0 path
(mem-0004) exists; until then logs are written and the normal indexer picks them up.

Usage:
    python3 .claude/hooks/import-history.py --dry-run
    python3 .claude/hooks/import-history.py --limit 50
    python3 .claude/hooks/import-history.py            # full run, sets sentinel
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys

MODEL = "claude-haiku-4-5-20251001"
SENTINEL_NAME = ".history-imported"


# --- extraction helpers: identical semantics to stop-summarize.py --------------------

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


def rec_timestamp(rec):
    """ISO date (YYYY-MM-DD) for a record, from its `timestamp`; None if absent/bad."""
    ts = rec.get("timestamp")
    if not ts:
        return None
    try:
        # transcript timestamps are ISO-8601 (often trailing 'Z')
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def load_records(path):
    recs = []
    try:
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    recs.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        return []
    return recs


def iter_exchanges(recs):
    """Yield (date, user_text, asst_text) for every assistant-prose turn paired with the
    nearest preceding user-prose turn. Mirrors last_exchange() but over the whole file."""
    n = len(recs)
    for i in range(n):
        role, txt = text_of(recs[i])
        if role != "assistant" or not txt:
            continue
        # walk back for the user prose that prompted this assistant turn
        user = None
        j = i - 1
        while j >= 0:
            r2, t2 = text_of(recs[j])
            if r2 == "user" and t2:
                user = t2
                break
            if r2 == "assistant" and t2:
                break  # hit the previous assistant turn first — no user prose between
            j -= 1
        if not user:
            continue
        date = rec_timestamp(recs[i]) or rec_timestamp(recs[j])
        yield date, user, txt


# --- summary + write: identical marker/format to the Stop hook -----------------------

def find_claude():
    claude = shutil.which("claude")
    if claude:
        return claude
    for p in ("~/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    return None


def summarize(user, asst, claude):
    prompt = (
        "Summarize the following exchange as 2-4 concise third-person bullet "
        "points (start each with '- '). Describe what the user asked and what "
        "the assistant did. No preamble, no headers.\n\n"
        "USER:\n" + user[:6000] + "\n\nASSISTANT:\n" + asst[:6000]
    )
    if claude:
        try:
            env = dict(os.environ, MEMORY_STOP_HOOK="1")  # never re-trigger the Stop hook
            r = subprocess.run([claude, "-p", prompt, "--model", MODEL],
                               capture_output=True, text=True, timeout=120,
                               env=env, stdin=subprocess.DEVNULL)
            out = (r.stdout or "").strip()
            if out:
                return out
        except Exception:
            pass
    return "- (auto-summary unavailable) user: " + " ".join(user.split())[:140]


def turn_hash(user, asst):
    return hashlib.sha256((user + "\n---\n" + asst).encode("utf-8")).hexdigest()[:12]


def append_log(cwd, date, marker, summary):
    """Append one auto-block to memory/<date>.md. Returns 'written' | 'dup'."""
    logdir = os.path.join(cwd, "memory")
    os.makedirs(logdir, exist_ok=True)
    log = os.path.join(logdir, date + ".md")
    existing = ""
    if os.path.exists(log):
        with open(log) as f:
            existing = f.read()
    if ("auto:" + marker.split("auto:")[-1]) in existing or marker in existing:
        return "dup"
    block = []
    if existing and not existing.endswith("\n"):
        block.append("")
    if not os.path.exists(log):
        block.append("# " + date)
        block.append("")
    if "## Auto-captured" not in existing:
        block.append("## Auto-captured (imported history)")
        block.append("<!-- Backfilled by import-history.py. Safe to prune; hashes prevent dupes. -->")
        block.append("")
    block.append("<!-- %s -->" % marker)
    for line in summary.splitlines():
        line = line.rstrip()
        if line:
            block.append(line if line.lstrip().startswith(("-", "*")) else "- " + line)
    block.append("_imported (source: session history)_")
    block.append("")
    with open(log, "a") as f:
        f.write("\n".join(block) + "\n")
    return "written"


# --- indexing: deferred to the mem0 path (mem-0004) ----------------------------------

def try_index(cwd, written_logs):
    """Index the backfilled logs via the shared mem0 indexer if it exists yet.

    The mem0 write path (mem-0004) is not built at import-authoring time. When the
    indexer module lands (expected `.claude/hooks/memory_index.py` exposing
    `index_log(cwd, path)`), this wires it up automatically. Until then we defer:
    the logs are on disk and the normal Stop-hook indexer will absorb them once mem0
    is stood up."""
    idx_path = os.path.join(cwd, ".claude", "hooks", "memory_index.py")
    if not os.path.exists(idx_path):
        print("  [defer] mem0 indexer not present yet; %d log(s) written, will be "
              "indexed once the mem0 path exists." % len(written_logs))
        return
    sys.path.insert(0, os.path.dirname(idx_path))
    try:
        import memory_index  # type: ignore
        for p in sorted(written_logs):
            memory_index.index_log(cwd, p)
        print("  [index] indexed %d log file(s) via memory_index." % len(written_logs))
    except Exception as e:
        print("  [defer] indexer present but failed (%s); logs written, index later." % e)


# --- discovery + main ----------------------------------------------------------------

def discover_transcripts(cwd):
    """All transcript .jsonl for this project: Claude Code's history dir + local archive."""
    paths = set()
    slug = cwd.replace("/", "-")
    hist = os.path.expanduser(os.path.join("~/.claude/projects", slug))
    paths.update(glob.glob(os.path.join(hist, "*.jsonl")))
    paths.update(glob.glob(os.path.join(cwd, ".claude", "transcripts", "*.jsonl")))
    return sorted(paths)


def main():
    ap = argparse.ArgumentParser(description="One-time historical import into dated logs.")
    ap.add_argument("--project-dir", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ap.add_argument("--dry-run", action="store_true", help="extract + count, write nothing")
    ap.add_argument("--limit", type=int, default=0, help="cap turns processed (0 = all)")
    ap.add_argument("--force", action="store_true", help="ignore the sentinel")
    args = ap.parse_args()

    cwd = os.path.abspath(args.project_dir)
    sentinel = os.path.join(cwd, ".claude", SENTINEL_NAME)
    if os.path.exists(sentinel) and not args.force:
        print("Sentinel %s present — already imported. Use --force to re-run." % sentinel)
        return

    transcripts = discover_transcripts(cwd)
    if not transcripts:
        print("No transcripts found for %s." % cwd)
        return
    print("Found %d transcript(s)." % len(transcripts))

    claude = None if args.dry_run else find_claude()
    if not args.dry_run and not claude:
        print("WARNING: `claude` CLI not found — summaries will use the fallback line.")

    seen = set()
    written_logs = set()
    n_written = n_dup = n_skip = 0
    for tp in transcripts:
        for date, user, asst in iter_exchanges(load_records(tp)):
            if not date:
                n_skip += 1
                continue
            h = turn_hash(user, asst)
            if h in seen:              # same turn across archive + history dir
                continue
            seen.add(h)
            if args.limit and (n_written + n_dup) >= args.limit:
                break
            marker = "auto:" + h
            if args.dry_run:
                print("  [dry] %s  %s  user=%s" % (date, marker, " ".join(user.split())[:60]))
                n_written += 1
                continue
            summary = summarize(user, asst, claude)
            res = append_log(cwd, date, marker, summary)
            if res == "written":
                n_written += 1
                written_logs.add(os.path.join(cwd, "memory", date + ".md"))
            else:
                n_dup += 1
        if args.limit and (n_written + n_dup) >= args.limit:
            break

    print("Done: %d written, %d dup/skip-existing, %d undated-skipped." % (n_written, n_dup, n_skip))

    if args.dry_run:
        print("Dry run — no files written, no sentinel set.")
        return

    try_index(cwd, written_logs)

    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    with open(sentinel, "w") as f:
        f.write("imported %s — %d turns\n" % (datetime.datetime.now().isoformat(), n_written))
    print("Sentinel written: %s" % sentinel)


if __name__ == "__main__":
    main()
