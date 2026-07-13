---
status: accepted
---

# mem-0004 — Adopt mem0 as the memory framework; fork one provider for pg_search BM25; TEI embeddings; OpenMemory MCP reader

**Status:** Accepted (2026-07-14). Pivots mem-0002 and mem-0003 from a hand-rolled stack
to a framework-backed one; mem-0001 (store choice) is unchanged.

## Context

mem-0001…mem-0003 originally specified a **hand-built** memory stack: a bespoke
`memory.chunk` schema with LIST partitioning, a hand-written RRF-fusion SQL query, a
custom indexer, and crystaldba postgres-mcp as the reader. Before writing any of it, we
evaluated [mem0](https://github.com/mem0ai/mem0) — a maintained OSS memory layer that
already provides most of the pieces we were about to build by hand:

- an `add()` / `search()` SDK over a pluggable **vector-store provider** abstraction,
- an **embedder** abstraction (OpenAI-compatible, Ollama, HuggingFace, …),
- result ranking/scoring with metadata filtering,
- **OpenMemory MCP** — a ready read server exposing the store to an agent.

The one thing mem0 does **not** do out of the box is **hybrid** (keyword+vector)
retrieval: its pgvector provider is vector-only. That gap is small and well-contained —
one provider file — versus owning the whole stack.

## Decision

1. **Adopt mem0; do not hand-roll.** Use mem0's SDK for the write path (`add`) and its
   ranking/filtering for the read path. Reuse OpenMemory MCP as the reader.
2. **Fork exactly one component — the pgvector store provider — to add pg_search BM25.**
   The fork implements hybrid `search()` (BM25 over the memory text via `pg_search` +
   vector), fused and returned to mem0. Everything else in mem0 is used unmodified. Fork
   surface = one provider module, rebased on mem0 upgrades.
3. **`infer=False` on write.** mem0's default runs an LLM "fact-extraction" pass over
   added text. We store session-summary chunks **verbatim** (embed + index only), so the
   write path stays LLM-free and deterministic — matching the original intent of a plain
   embed+INSERT indexer.
4. **Embeddings: TEI, not ollama.** Serve `nomic-embed-text` from HuggingFace
   **text-embeddings-inference** on the VPS; plug into mem0 as its OpenAI-compatible
   embedder (mem-0002). A dedicated embedding server is leaner than a general LLM runtime
   for pure embedding serving.
5. **Reader: OpenMemory MCP, not crystaldba.** mem0's own MCP read server replaces
   crystaldba postgres-mcp; the underlying DB role stays `memory_ro` (SELECT-only) for
   defence-in-depth (mem-0003).

## Consequences

- Far less code to own: chunk→memory, embedding orchestration, search/rank, and the MCP
  are the framework's; our surface is one forked provider + the Stop-hook glue.
- Bound to mem0's data model and upgrade cadence. The forked provider must be **rebased**
  when mem0's provider interface changes; pin the mem0 version and test the fork on bump.
- **LIST partitioning is dropped** (mem-0002): mem0 manages a single collection/table, so
  per-project scoping becomes a **metadata filter**, not a physical partition. Acceptable —
  volume is tiny (one developer, a few repos) and the filter is over indexed metadata.
- `infer=False` means no automatic summarization/dedup from mem0; our own content-`hash`
  dedup (mem-0002) still applies.
- Trades bespoke control for a maintained hybrid-memory framework — the intended trade.
