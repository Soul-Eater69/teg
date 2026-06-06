# CLAUDE.md - TEG

Repo-level instructions for Claude/LLM agents working in this repository.

## What this repo is

Theme & Epic Generation: **ingestion + data science solution**. Reads an IDMT idea
card and predicts the business taxonomy a Business Architect would create in Jira.

```text
Value Stream = Jira Theme / GROUP issue
Stage        = Jira Epic (epic title contains the stage name)
```

This is a clean from-scratch rebuild. The old `vs` repo (`../vs`) is **reference
only** - lift logic and field shapes from it; do not import from it.

## Scope boundary (important)

- We own: ingestion, condense, VS prediction, theme generation.
- The **backend team** owns the API layer and HITL approval. They call our services.
- We do not build routes, auth, or HITL here. The contract is `docs/service_contracts.md`.
- We return condensed data; the backend stores it and replays it into later calls.
- Governed catalogues (VS / stage / L2 / L3) live in Cosmos; we read them, the
  backend never sends them.

## Orchestration

- **Pure asyncio. No LangChain, no LangGraph.** Fan-out with `asyncio.gather`,
  bound concurrency with `asyncio.Semaphore`. Keep orchestration behind a small
  interface so it stays swappable.
- The HITL gate is an API/persistence seam (backend), not a held in-memory graph.

## Prediction input rule

Prediction may use only the original IDMT packet (summary, description, idea card,
attachment text, generated summary). **Never feed current-ticket Epic titles into
prediction** - they are answer-key artifacts. Ground truth (linked Themes / Epics)
is for ingestion, indexing, and eval only.

## Coding style

Clean production Python: clear domain names, small meaningful functions, linear
readable flow, explicit data shapes, simple dataclasses for core records, minimal
nesting, single source of truth for schemas. Use domain names (`value_stream`,
`stage_ground_truth`, `condensed_ticket`) not vague ones (`labels`, `manager`,
`processor`, `service`-as-dumping-ground). Avoid one-line wrappers, generic util
dumping grounds, and over-engineered abstractions.

- `domain/` = dataclasses, the single source of truth for shapes.
- `contracts/` = pydantic DTOs at the backend boundary (camelCase JSON).

## Testing

- Unit tests must not make live Jira / Azure / LLM calls. Inject fakes (DI).
- New public contracts include model / `to_dict` (serialization) tests.

## Validation before reporting completion

```bash
uv run python -m compileall src
uv run pytest
```

## Reporting format

After changes summarize: branch, files changed, features implemented, tests run,
behavior intentionally not changed, remaining risks / next steps.
