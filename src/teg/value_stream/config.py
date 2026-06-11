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
    max_supporting_tickets: int = 2  # source tickets kept per candidate
    use_historic_lane: bool = True  # use the historic ER lane at all (ablation: False = semantic-only)
    generic_penalty_scale: float = 0.6  # broad-stream rank penalty = scale * attractor_signal (0 = off)
    generic_earned_hits: int = 3  # historical hits that exempt a broad stream from the penalty
    min_confidence: float = 0.0  # abstention floor (0-1); >0 keeps only confident picks, no padding
    # Experiment selector for candidate-pool construction:
    #   merge         - VS + historic merged into the review pool (default, production)
    #   all50         - all VS candidates, no historic (pool = full catalogue)
    #   topk          - top-K VS by semantic score only (K = llm_candidate_window)
    #   historic_only - candidates only from the historic lane's VS
    #   evidence      - all VS candidates + historic shown as a separate EVIDENCE block (no merge)
    selection_mode: str = "merge"
