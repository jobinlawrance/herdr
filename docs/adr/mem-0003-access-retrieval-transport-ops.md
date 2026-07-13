---
status: accepted
superseded_original: mem-0004
---

# mem-0003 — Split write/read roles; mem0 hybrid + recency retrieval with citations; OpenMemory MCP reader; Tailscale transport; fail-safe Stop-hook writer

**Status:** Accepted (2026-07-13); **revised 2026-07-14**. Builds on mem-0001, mem-0002.
Retrieval and the reader are now mem0-native per
[mem-0004](mem-0004-adopt-mem0-fork-provider-tei-openmemory.md).

## Context

Given the store (mem-0001) and the mem0 data model (mem-0002, mem-0004), three runtime
concerns remain: **who may write vs read**, **how hybrid results are fused/ranked and
cited**, and **how the Mac reaches the VPS safely and reliably**.

The corpus is semi-untrusted (verbatim session text can contain anything, including text
that looks like SQL/instructions), so the read path must hold no write or DDL rights. The
writer runs from a background hook that must never disrupt the user's session. The Mac↔VPS
link must never expose Postgres to the public internet.

## Decision

### 1. Access split — two least-privilege roles

- **`memory_rw`** — used **only** by the indexer (mem0 `add`). `USAGE` on the memory schema,
  `INSERT`/`SELECT`/`UPDATE` on the mem0 collection table, and the DDL the forked provider
  needs for its indexes. No access to any other schema.
- **`memory_ro`** — used by the **OpenMemory MCP** read server (mem-0004). `SELECT` on the
  memory table only. This is the interactive/agent read path.
- OpenMemory MCP runs mem0's read side but connects as `memory_ro`, so even a compromised or
  injection-steered read path can only `SELECT`. pgEdge and an unrestricted full-DB MCP were
  both rejected — blast radius over the product DB, injection risk from the corpus.

### 2. Retrieval — mem0 hybrid + recency, with citations

Retrieval is a mem0 `search(query, filters={project_id, …})`. Under the hood the forked
provider (mem-0002/0004) runs **BM25 and vector in parallel and fuses them** rank-wise (so
raw BM25 scores need no calibration against cosine distance); mem0 applies the metadata
filters and returns ranked results. A mild **recency preference** on `log_date` is applied
(memory recall favours recent sessions). `project_id` and `device` are **filters**, not
weights. **No cross-encoder reranker in v1** (extra model, marginal gain; revisit if recall
disappoints). *Exact fusion implementation is settled in the spike.*

**Citations (required).** Every returned chunk surfaces its `source_file`, `log_date`, and
`section` alongside the `body`, so the agent answers with attribution
(`memory/<date>.md › <heading>`) instead of paraphrasing blind. If nothing relevant clears
the threshold, the read path **says so** rather than inventing an answer — this matters most
because the corpus is machine-written, not the user's own words.

### 3. Transport — Tailscale, never public Postgres

- Put the Mac and the VPS on a **Tailscale (WireGuard) tailnet**.
- Postgres `listen_addresses = 'localhost,<tailnet-ip>'`; the public firewall **drops** the
  Postgres port. `sslmode=verify-full`, SCRAM-SHA-256 auth.
- **TEI** (mem-0002) binds `localhost` + the tailnet interface only — embeddings are
  reachable only over the tailnet, same posture as Postgres.
- Fallback if Tailscale is off the table: a persistent `autossh -L` tunnel with Postgres
  bound to `localhost` only. Public exposure of the port is never acceptable.

### 4. Writer — Stop-hook, mem0.add over the tailnet, fail-safe

- The **Stop hook** is the writer. It appends the summary as today, then the indexing step
  reads the dated log, skips chunks whose `hash` is already present, and calls **mem0
  `add(chunk, metadata=…, infer=False)`** for each new chunk — mem0 embeds via TEI over the
  tailnet and writes the row. Embedding is VPS-hosted but called remotely, so vectors stay
  consistent (mem-0002) and Postgres runs no server-side embedding trigger.
- **Fail-safe:** the hook is timeout-bounded and must **never block session exit**. If the
  store or TEI is unreachable, append the payload to a **gitignored spool**
  (`.claude/memory-spool/`); the next run flushes the spool before indexing new content.
- **Secrets** (memory DB connection string, TEI endpoint) follow the repo's existing
  **varlock / `.env.schema`** convention — commit the schema, keep values in the gitignored
  `.env`, never commit them.

## Consequences

- The read path is powerless to mutate or DDL the store — corpus injection can at worst
  return misleading rows, never write.
- Answers are attributable: `source_file`/`log_date`/`section` travel with every hit, and an
  empty result set is reported honestly instead of hallucinated.
- Rank-fusion needs no score calibration and degrades gracefully when one arm is empty (rows
  not yet embedded still surface via BM25).
- Tailscale is a new dependency both machines must stay joined to; if the tailnet is down the
  writer spools and search is unavailable (acceptable — memory is non-critical).
- The hook never harms the session: worst case a summary is spooled and indexed one run late.
- `.claude/memory-spool/` must be added to `.gitignore` (alongside `.claude/transcripts/`).
