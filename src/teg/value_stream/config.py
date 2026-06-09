"""Retrieval and review-window tuning knobs for Value Stream prediction.

These were loose module constants in the merger; grouped here as one explicit,
env-overridable shape (built from Settings in bootstrap), mirroring CondenseConfig.
derive_runtime turns them into a per-request CandidateMergePolicy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueStreamConfig:
    semantic_fetch_k: int = 50  # VS catalogue hits to fetch
    semantic_fetch_cap: int = 50  # hard cap - the catalogue has <=50 streams
    historical_fetch_k: int = 6  # historical analogs to fetch (also the historic-only cap)
    llm_candidate_window: int = 18  # review-pool size for a ~10-stream request
    window_headroom: int = 8  # buffer over the requested count when the window is derived
    max_supporting_tickets: int = 2  # source tickets / evidence kept per candidate
    use_historic_classification: bool = True  # use the direct/implied label (ablation: False)
