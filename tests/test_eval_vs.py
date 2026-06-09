"""Eval harness metric helpers (pure)."""
from __future__ import annotations

import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("eval_vs", pathlib.Path("scripts/eval_vs.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def test_prf_counts() -> None:
    tp, fp, fn = m._prf(["A", "B", "C"], {"B", "C", "D"})
    assert (tp, fp, fn) == (2, 1, 1)  # B,C hit; A extra; D missed


def test_gt_ids_from_themes() -> None:
    props = {"themes": [{"valueStreamId": "VSR1"}, {"valueStreamId": "VSR2"}, {"valueStreamId": ""}]}
    assert m._gt_ids(props) == {"VSR1", "VSR2"}


def test_summary_fields_raw_vs_condensed() -> None:
    props = {"summary": "s", "businessProblem": "b", "rawText": "RAW", "keyTerms": ["k"]}
    assert m._summary_fields(props, raw_text=True).generated_summary == "RAW"
    sf = m._summary_fields(props, raw_text=False)
    assert sf.generated_summary == "s" and sf.business_problem == "b" and sf.key_terms == ["k"]
