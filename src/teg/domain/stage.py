"""Stage prediction records.

A stage is represented by a Jira Epic. Prediction selects approved stages for an
already-selected Value Stream, against the governed Cosmos stage catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ValidationStatus = Literal["valid", "invalid", "unknown"]


@dataclass
class SelectedStage:
    """A predicted stage for an approved Value Stream."""

    stage_id: str
    stage_name: str
    rank: int
    reason: str
    evidence: str
    validation_status: ValidationStatus = "unknown"
