---
status: accepted
---

# mem-0001 — ParadeDB on the VPS is the cross-session memory store, isolated from viewrr's app DB

**Status:** Accepted (2026-07-13). Store choice unchanged by the mem0 pivot
([mem-0004](mem-0004-adopt-mem0-fork-provider-tei-openmemory.md)) — the framework on top
of the store changed; the store (ParadeDB on the VPS) did not.

## Context

Claude works on viewrr from two machines — the Mac local agent and an agent on the
VPS — and loses everything between sessions. The project already grew a `memory/`
folder (capped `working-memory.md` + dated logs) injected at session start and
appended by a Stop hook (`.claude/hooks/stop-summarize.py`). Flat-file recall does not
scale: it cannot do semantic search, and it cannot answer *"when did we last decide X"*
across months of logs.

We want a searchable index of session summaries shared by both machines. Three DBs are
in play and must not be confused:

- **viewrr app DB** — Postgres.app on `:5433` (the product's own data).
- **Raven project** — a pgvector container on `:5432` (a different project).
- **A memory DB** — to be stood up on the **VPS**, reachable by both agents.

The VPS Postgres already has ParadeDB's `pg_search` (BM25) extension installed, so a
capable keyword+vector engine is available at zero additional infra cost.

## Decision

1. **The cross-session memory store is a ParadeDB instance on the VPS** — a dedicated
   memory database, **not** viewrr's app DB and **not** the Raven container. Both the
   Mac agent and the VPS agent point at this one store so their memory is shared.
2. **Reuse `pg_search` (ParadeDB) already present on the VPS** for BM25 rather than
   standing up a separate search engine (Elastic/Meili). Vector search rides alongside
   in the same DB (see mem-0002), keeping keyword + semantic recall in a single query.
3. **Physical isolation from the product.** All memory objects live in a dedicated
   `memory` schema (mem-0002); nothing touches viewrr's application tables. The memory
   corpus is semi-untrusted (it contains verbatim session text), so it must never share
   a blast radius or a privileged connection with product data.

## Consequences

- One store, two clients — the Mac and VPS agents get identical recall. Requires a
  private, always-available link between the Mac and the VPS (mem-0003, Tailscale).
- No new search infrastructure to operate; ParadeDB does keyword and (with a vector
  type) semantic search in one place.
- The memory DB is a new operational surface on the VPS — backups and disk growth are
  now its concern, independent of viewrr's DB lifecycle.
- Keeping memory off the product DB means the least-privilege access split (mem-0003) is
  enforceable at the role/schema boundary, not by convention.
