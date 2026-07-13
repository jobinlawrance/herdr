---
name: memory-keeper
description: >-
  Curate the capped working-memory file. Use when the user says "remember",
  "note that", "make a note", "forget about", "update memory", or otherwise asks
  to persist, change, or drop a durable fact, decision, or active thread.
---

# memory-keeper

Curator for `memory/working-memory.md` — the small, capped snapshot injected at the
start of every session. Your job is to keep it accurate, deduplicated, and under budget.
Judgment lives here as editable prose, not hardcoded logic — revise these rules freely.

## When to act

Trigger on intent to persist or change durable memory: *remember*, *note that*, *make a
note*, *forget about*, *update memory*, *that's no longer true*. Passing chit-chat is not
a memory write.

## Procedure

1. **Read the whole file first.** Always read `memory/working-memory.md` in full before
   editing — you must see everything to dedup and to pick the right section.
2. **Classify the change:**
   - **add** — a genuinely new fact/decision/thread.
   - **replace** — supersedes an existing line (e.g. a reversed decision). Edit in place;
     don't leave the stale line.
   - **remove** — a thread that's done or a fact that's no longer true.
3. **Pick the section:** `## Active Threads` (in-flight work, one line each, drop when
   done) · `## Notes Worth Keeping` (durable facts, gotchas, settled decisions) ·
   `## Pending Decisions` (open questions + owner/blocker).
4. **Dedup.** If the fact is already present, update it rather than duplicating.
5. **Respect the cap (~2000 chars).** If adding would exceed budget, **consolidate**:
   merge related lines, drop the least useful, and prefer terse fragments over prose.
   Never silently truncate mid-line.
6. **Confirm briefly** what you changed (added/replaced/removed + which section).

## Rules

- One line per item. Fragments over sentences.
- Durable only. Volatile day-detail belongs in the dated log (Stop hook writes that), not
  here.
- Never invent facts to fill space. Never remove something the user didn't ask to remove
  unless it's demonstrably stale and you say so.
- The file is frozen mid-session for *injection*; your edits take effect next session.
  That's expected — don't try to hot-reload.
