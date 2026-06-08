"""Render review-pool candidates into the compact blocks the selection prompt reads.

Each block exposes what the prompt's "how to read candidates" section expects: the
entity id to return, the lane, semantic score, and (when present) historical support.
"""

from __future__ import annotations

from teg.value_stream.models import ValueStreamCandidate


def render_candidate_blocks(candidates: list[ValueStreamCandidate]) -> str:
    return "\n\n".join(_block(c) for c in candidates)


def _block(c: ValueStreamCandidate) -> str:
    lines = [
        f"Candidate: {c.value_stream_name}",
        f"entity_id: {c.value_stream_id}",
        f"lane: {c.lane}",
    ]
    if c.value_stream_description:
        lines.append(f"description: {c.value_stream_description}")

    semantic = f"semantic: score={c.semantic_score:.2f}"
    if c.semantic_rank is not None:
        semantic += f", rank={c.semantic_rank}"
    lines.append(semantic)

    if c.from_historical:
        lines.append(
            f"historical: tickets={c.supporting_ticket_count} "
            f"(direct={c.direct_count}, implied={c.implied_count}), "
            f"best={c.best_support_score:.2f}, avg={c.avg_support_score:.2f}, "
            f"weighted={c.weighted_support:.2f}, ids={c.source_ticket_ids}"
        )
        if c.evidence:
            lines.append("evidence: " + " | ".join(c.evidence))
    return "\n".join(lines)
