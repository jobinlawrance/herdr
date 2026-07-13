# Cross-Session Memory — ADR set

> **Not a viewrr-product concern.** These record the design of **Claude's
> cross-session memory** — a ParadeDB-backed, mem0-framework index of session
> summaries that lets the Mac local agent and the VPS agent recall prior work
> across sessions. It is **separate from viewrr's application DB** and from the
> `p2p-` epic, despite living in this directory. Prefixed `mem-` for that reason
> (same rationale the `p2p-` set carries its own prefix + index).
>
> Origin: project `memory/` + SessionStart/Stop hooks (see
> `.claude/hooks/stop-summarize.py`) and the Notion "Claude Code Memory Plan"
> (Hermes + extensions). Decision dialogue: `memory/2026-07-13.md`,
> `memory/2026-07-14.md`.

| MEM-ADR | Decision |
|---------|----------|
| [mem-0001](mem-0001-paradedb-cross-session-memory-store.md) | ParadeDB on the VPS is the cross-session memory store; isolated from viewrr's app DB |
| [mem-0002](mem-0002-partitioned-chunk-schema-hybrid-embeddings.md) | mem0 collection + metadata filters; hybrid BM25 + `vector(768)` via a forked provider; TEI embeddings; source = dated logs only; citation metadata on every chunk |
| [mem-0003](mem-0003-access-retrieval-transport-ops.md) | Split write/read roles; mem0 hybrid + recency retrieval **with citations**; OpenMemory MCP reader; Tailscale transport; fail-safe Stop-hook writer |
| [mem-0004](mem-0004-adopt-mem0-fork-provider-tei-openmemory.md) | **Adopt mem0**; fork one provider for `pg_search` BM25; `infer=False`; TEI (not ollama); OpenMemory MCP (not crystaldba) |

Spec / data-flow overview: [../architecture/cross-session-memory.md](../architecture/cross-session-memory.md)

## Locked decisions

1. **Store** — ParadeDB (`pg_search`) on the VPS, a dedicated memory DB, **not**
   viewrr's Postgres.app (`:5433`) nor the Raven pgvector container (`:5432`). → mem-0001
2. **Isolation** — writes land in an isolated `memory` schema; product tables untouched. → mem-0001 / mem-0002
3. **Framework** — **adopt mem0**; hand-roll nothing that mem0 already gives (add/search
   SDK, embedder abstraction, ranking, OpenMemory MCP). Fork **exactly one** component —
   the pgvector store provider — to add `pg_search` BM25 hybrid. → mem-0004
4. **Data model** — one **mem0 collection**; per-project scope via a **metadata filter**
   (`project_id` = normalized git remote); `device`/`session_id` in metadata. LIST
   partitioning dropped (mem0 owns one table; volume tiny). → mem-0002 / mem-0004
5. **Search kind** — hybrid: BM25 (keyword) + vector (semantic), fused rank-wise.
   Keyword-only rejected (recall too narrow). → mem-0002
6. **Embeddings** — self-hosted **TEI `nomic-embed-text` → `vector(768)`** on the VPS
   (x86 Linux, CPU image), OpenAI-compatible into mem0's embedder; one model so Mac + VPS
   vectors are consistent; nomic task prefixes applied app-side. (Replaced ollama.) → mem-0002 / mem-0004
7. **Source + chunking** — index **dated logs only**; chunk by `##` sections + Stop-hook
   auto-blocks; block HASH is the dedup key; `infer=False` stores chunks verbatim; Stop
   hook stamps `session`/`device`. → mem-0002
8. **Merge/rerank** — mem0 hybrid fusion + mild **recency** on `log_date`; `project`/
   `device` as **filters**, not weights; no cross-encoder in v1. → mem-0003
9. **Citations** — every returned chunk carries `source_file` + `log_date` + `section`;
   answers cite `memory/<date>.md › <heading>`; empty result → say so, don't invent. → mem-0002 / mem-0003
10. **Access + transport + ops** — indexer writes via mem0 as `memory_rw`; search via
    **OpenMemory MCP** as `memory_ro`; **Tailscale** tailnet, `sslmode=verify-full`,
    SCRAM; Stop-hook writer embeds over the tailnet and is **fail-safe** (spool on
    unreachable). → mem-0003 / mem-0004

## Divergence from the Notion plan (deliberate)

The Notion "Memory Plan" specifies a **local, free** stack ("no VPS, no second
subscription, no new runtime — just files, hooks, and a skill", local vector DB). We
**intentionally exceed it on the store/embedding axis**: a shared **VPS** ParadeDB + TEI so
the Mac agent *and* the VPS agent draw on **one** corpus with consistent vectors (mem-0001).
Everything else in the plan (inject, curated-writes skill, capture-everything Stop hook,
hybrid semantic search, citations, one-time historical import) is adopted as written.
