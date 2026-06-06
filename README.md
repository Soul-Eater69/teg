# TEG - Theme & Epic Generation

Ingestion + data science solution that turns an IDMT idea card into an
evidence-backed recommendation package: Value Streams (Jira Themes), Stages
(Jira Epics), Theme descriptions, Business Needs, and L2/L3 capabilities.

This repo is **ingestion + DS only**. The API layer and human-in-the-loop (HITL)
approval are built and owned by a separate backend team; they call our services.
See `docs/service_contracts.md` for the boundary.

## Flow

```
new idea card
  -> condense        (one LLM pass -> summaryFields + generationSignals)   [Contract A]
  -> VS prediction   (RAG two lanes -> review-pool LLM selection)          [Contract B]
        -> backend HITL approves the VS set
  -> theme generation (per-VS async fan-out: stage||desc -> needs/L2/L3)   [Contract C]
```

Orchestration is **pure asyncio** - no LangChain, no LangGraph. The HITL gate is an
API/persistence seam owned by the backend, not an in-memory paused graph, so a
graph engine earns nothing here.

## Structure

```
src/teg/
  config/        env-driven settings
  domain/        core records - single source of truth for data shapes
  contracts/     pydantic I/O DTOs the backend calls (camelCase JSON + JSON Schema)
  integrations/  external clients by system: llm/ (protocol + IDP gateway), jira/, files/
  prompts/       prompt YAMLs by layer (condense/, value_stream/, theme/) + loader
  ingestion/     offline batch: historical IDMT -> Cosmos + idp_idmt_data
  condense/      5.1-5.2 condense step
  value_stream/  5.3-5.5 retrieval, merge, review-pool selection
  theme/         6 theme generation fan-out
  services/      facades the backend calls: CondenseService, ValueStreamService, ThemeService
tests/           unit tests; no live Jira/Azure/LLM (inject fakes)
docs/            service_contracts.md (backend handoff)
```

## Develop

```bash
uv sync --extra dev
uv run pytest
uv run python -m compileall src
```
