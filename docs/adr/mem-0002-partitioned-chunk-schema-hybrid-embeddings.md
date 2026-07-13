---
status: accepted
superseded_original: mem-0004
---

# mem-0002 — mem0 collection with metadata-scoped filters; hybrid BM25 + `vector(768)` via a forked provider; source = dated logs only

**Status:** Accepted (2026-07-13); **revised 2026-07-14**. Builds on mem-0001. The original
hand-rolled partitioned-`chunk` schema is superseded by the mem0 model per
[mem-0004](mem-0004-adopt-mem0-fork-provider-tei-openmemory.md).

## Context

The store (mem-0001) needs a data model. Per mem-0004 the stack is **mem0**, so the model
is largely mem0's: memories live in one collection, each carrying a `metadata` JSONB.
Requirements unchanged from the original design:

- searchable **across sessions**, scopable to **one project** where repos share the store;
- **hybrid** recall — keyword (BM25) *and* semantic (vector); keyword-only misses
  meaning-based recall (*"the auth decision"* won't find a summary that said *"we dropped
  Keycloak"*);
- both agents must produce **consistent vectors** or cross-device semantic search is
  meaningless, so the embedding model is fixed and single-sourced;
- every result must be **citable** back to its exact source (source file + date + heading),
  not paraphrased without attribution.

## Decision

1. **One mem0 collection; project scope via metadata filter, not partitions.** Each memory
   carries metadata:

   ```
   { project_id, device, session_id, log_date, source_file, section, hash }
   ```
   - `project_id` = normalized git remote (e.g. `github.com/jobinlawrance/viewrr`);
   - `device` = `mac` | `vps` | hostname; `session_id` from the Stop-hook auto-block;
   - `log_date` = source dated-log date (drives recency, mem-0003);
   - `source_file` = the dated-log path (e.g. `memory/2026-07-14.md`) — the citation anchor;
   - `section` = the `##` heading (or `auto:<hash>`) the chunk came from — the citation anchor;
   - `hash` = dedup key (auto-block HASH or content hash).

   Retrieval scopes with mem0 `filters={"project_id": …}` over this metadata. **LIST
   partitioning from the original proposal is dropped** (mem-0004): mem0 owns a single
   table and volume is tiny, so an indexed metadata filter replaces physical partitions.

2. **Hybrid search via a forked pgvector provider (mem-0004).** mem0's pgvector provider is
   vector-only; the fork adds a `pg_search` BM25 index over the memory text and returns a
   **fused** (BM25 + vector) result list to mem0. Both indexes live on the one memory table:

   ```sql
   -- created/managed by the forked provider on the mem0 collection table
   CREATE INDEX mem_bm25 ON <mem0_table> USING bm25 (id, <text_col>) WITH (key_field='id');
   CREATE INDEX mem_vec  ON <mem0_table> USING hnsw (<embedding_col> vector_cosine_ops);
   ```
   *Exact fusion point (inside the provider's `search()` vs a mem0 reranker) and the vector
   index method (pgvector HNSW vs vchord) are settled in the spike, against the extensions
   actually enabled on the VPS.*

3. **Embeddings — self-hosted TEI `nomic-embed-text` → `vector(768)` on the VPS
   (mem-0004).** HuggingFace **text-embeddings-inference**, VPS x86 Linux, CPU image
   (`ghcr.io/huggingface/text-embeddings-inference:cpu-latest`); the model is ~137M params
   and volume is a few chunks/session, so CPU is sufficient (no GPU). TEI exposes an
   OpenAI-compatible `/v1/embeddings`; mem0's **openai** embedder points at it
   (`base_url` = TEI, `embedding_dims: 768`, dummy key). One model, one endpoint → vectors
   comparable across Mac and VPS. An external embedding API (OpenAI/Voyage) was rejected for
   cost + privacy (the corpus is private session text).
   - **nomic task prefixes** (`search_document:` on ingest, `search_query:` on query) are
     applied app-side (a thin embedder wrapper), since mem0's openai embedder does not add
     them and nomic recall degrades noticeably without them.

4. **Source = dated logs only.** Index `memory/<date>.md`. **Not** `working-memory.md`
   (volatile scratchpad, re-pruned every session) and **not** git-tracked docs (already
   versioned; noise). Chunk each log by `##` sections plus each Stop-hook auto-block; the
   block's existing **HASH is the dedup key** — re-indexing is idempotent. On write, mem0
   `add(..., infer=False)` stores the chunk verbatim (mem-0004); the indexer skips chunks
   whose `hash` metadata already exists.

5. **`session_id` gap closed at the source.** Dated-log auto-blocks lacked a session id, so
   the Stop hook (`stop-summarize.py`) stamps `session`/`device` into the auto-block marker;
   the indexer reads them (plus `source_file`/`section`) into metadata above.

## Consequences

- Cross-session, cross-device recall in one mem0 `search`; per-project scoping is a metadata
  filter, not a physical prune — simpler, at the cost of no partition-level isolation
  (acceptable at this volume).
- Every stored memory carries `source_file` + `log_date` + `section`, so the read path can
  **cite** (mem-0003) rather than paraphrase.
- Fixing the embedding model is a lock-in: changing it later means re-embedding the whole
  corpus. Accepted for vector consistency.
- The forked provider carries the only bespoke DDL (the two indexes); mem0 owns the table
  shape, so a mem0 schema change can require rebasing the fork (mem-0004).
- Memories may exist before embedding completes (`embedding` nullable); the vector arm
  tolerates missing vectors (BM25 still surfaces them).
