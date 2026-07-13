# Cross-Session Memory — architecture

Searchable, shared recall of Claude's prior work on viewrr, across sessions and across the
two machines it runs on (Mac local agent, VPS agent). Supersedes flat-file-only recall from
the `memory/` folder; the flat files stay as the human-readable layer and the ingest source.

Built on **[mem0](https://github.com/mem0ai/mem0)** with a single forked provider for
`pg_search` BM25 — see [mem-0004](../adr/mem-0004-adopt-mem0-fork-provider-tei-openmemory.md).

Decisions of record: [`../adr/mem-INDEX.md`](../adr/mem-INDEX.md) (mem-0001 … mem-0004).
Design dialogue: `memory/2026-07-13.md`, `memory/2026-07-14.md`.

## Pieces

| Piece | What | Where |
|-------|------|-------|
| Framework | **mem0** SDK (`add`/`search`, `infer=False`) + one forked store provider | Mac indexer + VPS agent |
| Store | ParadeDB (`pg_search`) memory DB | VPS (separate from viewrr `:5433` and Raven `:5432`) |
| Data model | one **mem0 collection**; scope by `project_id` **metadata filter** | memory DB |
| Keyword | BM25 index over memory text (added by the forked provider) | mem0 collection table |
| Semantic | `vector(768)` + HNSW; **TEI** `nomic-embed-text` | VPS TEI endpoint |
| Writer | Stop hook → mem0 `add(…, infer=False)` | `.claude/hooks/stop-summarize.py` (Mac) |
| Reader | **OpenMemory MCP**, role `memory_ro` | agent / interactive |
| Link | Tailscale tailnet, `sslmode=verify-full`, SCRAM | Mac ↔ VPS |

## Data model

mem0 owns one collection/table. Each memory carries metadata:
`{ project_id, device, session_id, log_date, source_file, section, hash }`.
`project_id` = normalized git remote; per-project scope is a **filter** over that metadata
(no physical partitions — mem-0004). `source_file`/`log_date`/`section` are the **citation**
anchors. Dedup key = `hash`. Details in
[mem-0002](../adr/mem-0002-partitioned-chunk-schema-hybrid-embeddings.md).

## Write path (session end)

```
session ends
  └─ Stop hook (detached, non-blocking, timeout-bounded)
       ├─ append summary auto-block to memory/<date>.md   (stamps session/device)
       └─ index step:
            read memory/<date>.md
            split → chunks (## sections + auto-blocks), carry source_file + section
            skip chunks whose hash metadata already exists   → dedup
            for each new chunk:
              mem0.add(chunk, metadata={project_id, device, session_id,
                                        log_date, source_file, section, hash},
                       infer=False)
                → embeds via VPS TEI (over tailnet) → vector(768) → INSERT (as memory_rw)
            on store/TEI unreachable:
              append payload → .claude/memory-spool/   (gitignored)
              (next run flushes spool first)
```

Embedding is generated at write time by calling the **VPS-hosted TEI** model — one model →
consistent vectors on both machines; Postgres runs no server-side embedding trigger. Nomic
task prefixes (`search_document:` on ingest, `search_query:` on query) are applied in a thin
embedder wrapper.

## Read path (recall)

**OpenMemory MCP**, connected as `memory_ro` (SELECT-only). Query = mem0
`search(query, filters={project_id, …})`; the forked provider fuses BM25 + vector rank-wise,
then a mild recency preference on `log_date`; `project_id`/`device` are filters. **Every hit
returns `source_file` + `log_date` + `section` with the body** so answers cite
`memory/<date>.md › <heading>` instead of paraphrasing. If nothing clears the threshold, the
reader says so rather than inventing. Details in
[mem-0003](../adr/mem-0003-access-retrieval-transport-ops.md).

## Bootstrap (one-time historical import)

A sentinel-guarded script walks existing Claude Code session history, extracts meaningful
turns the same way the Stop hook does, summarizes into the dated-log format, and indexes via
the same mem0 path — so recall isn't cold on day one. Runs once, then the sentinel blocks
re-runs. See `.claude/hooks/import-history.py` (guarded by `.claude/.history-imported`).

## Trust + access

The corpus is semi-untrusted (verbatim session text). Enforced at the role/schema boundary,
not by convention:

- `memory_rw` — indexer (mem0) only; INSERT/SELECT/UPDATE + index DDL on the collection; nothing else.
- `memory_ro` — OpenMemory MCP reader only; SELECT on the collection.
- No unrestricted / full-DB MCP; no writes from the read path. Rejected alternatives
  (pgEdge, unrestricted MCP, ollama, crystaldba MCP, table-per-session, keyword-only,
  embedding API, hand-rolled stack) and why: mem-0001…mem-0004 + `memory/2026-07-13.md`.

## Security

- Postgres bound to `localhost` + tailnet IP; public port firewalled shut.
- `sslmode=verify-full`, SCRAM-SHA-256.
- TEI bound to `localhost` + the tailnet interface only.
- Secrets via the repo's varlock / `.env.schema` pattern (commit schema, never `.env`).

## Open / follow-ups

- Stand up **TEI** (`cpu-latest`) on the VPS serving `nomic-embed-text`, tailnet-bound.
- Fork mem0's pgvector provider → add `pg_search` BM25 hybrid `search()`; pin mem0 version.
- Confirm the vector index method (pgvector HNSW vs vchord) against extensions enabled on the
  VPS before first DDL; confirm a `vector` type is present alongside `pg_search`.
- Stand up `memory_rw` / `memory_ro` roles + the `memory` schema on the VPS.
- Stand up **OpenMemory MCP** pointed at the store as `memory_ro`.
- Extend `stop-summarize.py`: stamp `session`/`device`; carry `source_file`/`section`; add the
  mem0 index + spool-flush step.
- Add `.claude/memory-spool/` to `.gitignore`.
- Spike: `docker-compose` (TEI) + mem0 config (forked provider, openai embedder, `infer=False`)
  + OpenMemory MCP + throwaway ingest of `memory/*.md` to eval recall + citations.
- One-time historical import (`import-history.py`) — runs after the mem0 path exists.
