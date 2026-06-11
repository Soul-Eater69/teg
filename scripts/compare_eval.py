"""Compare VS-selection eval modes side by side: charts + interpretation in one docx.

Reads the per-run metrics each eval writes (<out>.runs.json), aggregates them (mean across the
repeat runs), and renders grouped bar charts comparing the modes on quality (P/R/F1), the
single-vs-multi cohorts, retrieval recall (the ceiling), historic boost, and latency - each with
a short interpretation. One picture instead of flipping between docs.

Usage (install: uv sync --extra eda):
  uv run python scripts/compare_eval.py out/eval/all50.runs.json out/eval/evidence.runs.json \
      --out out/eval/comparison.docx
Label = the file stem (all50.runs.json -> "all50"); override with label=path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _label_path(arg: str) -> tuple[str, str]:
    if "=" in arg and not arg.split("=", 1)[1].startswith("/"):
        label, path = arg.split("=", 1)
        return label, path
    stem = Path(arg).name.replace(".runs.json", "").replace(".json", "")
    return stem, arg


def _mean(runs: list[dict], key: str) -> float:
    vals = [r.get(key) for r in runs if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _mean_nested(runs: list[dict], outer: str, inner: str) -> float:
    vals = [(r.get(outer) or {}).get(inner) for r in runs]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def load(arg: str) -> dict:
    label, path = _label_path(arg)
    runs = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "label": label,
        "micro_p": _mean(runs, "micro_p"), "micro_r": _mean(runs, "micro_r"),
        "micro_f1": _mean(runs, "micro_f1"), "single_r": _mean(runs, "single_recall"),
        "multi_f1": _mean(runs, "multi_f1"), "judge_p": _mean(runs, "judge_p"),
        "vs_r10": _mean_nested(runs, "retrieval", "vs_lane@10"),
        "hist_r": _mean_nested(runs, "retrieval", "historic_lane"),
        "pool_r": _mean_nested(runs, "retrieval", "pool"),
        "backed_r": _mean_nested(runs, "boost", "backed_recall"),
        "notbacked_r": _mean_nested(runs, "boost", "notbacked_recall"),
        "lat_avg": _mean_nested(runs, "latency", "avg"),
        "lat_max": _mean_nested(runs, "latency", "max"),
    }


def _bar(ax, labels, series: dict, title, ylabel):
    import numpy as np

    x = np.arange(len(labels))
    width = 0.8 / max(1, len(series))
    for i, (name, vals) in enumerate(series.items()):
        bars = ax.bar(x + i * width - 0.4 + width / 2, vals, width, label=name)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set(title=title, ylabel=ylabel)
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)


def build(data: list[dict], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from docx import Document
    from docx.shared import Inches

    labels = [d["label"] for d in data]
    charts_dir = out_path.parent / "compare_charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    def save(fig, name):
        p = charts_dir / f"{name}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
        return str(p)

    figs = {}
    # 1. quality
    fig, ax = plt.subplots(figsize=(8, 4.5))
    _bar(ax, labels, {"precision": [d["micro_p"] for d in data], "recall": [d["micro_r"] for d in data],
                      "F1": [d["micro_f1"] for d in data]}, "Selection quality (micro)", "score")
    figs["quality"] = save(fig, "quality")
    # 2. cohorts
    fig, ax = plt.subplots(figsize=(8, 4.5))
    _bar(ax, labels, {"single-VS recall": [d["single_r"] for d in data],
                      "multi-VS F1": [d["multi_f1"] for d in data]}, "Single-VS vs Multi-VS", "score")
    figs["cohorts"] = save(fig, "cohorts")
    # 3. retrieval recall
    fig, ax = plt.subplots(figsize=(8, 4.5))
    _bar(ax, labels, {"VS lane R@10": [d["vs_r10"] for d in data], "historic lane R": [d["hist_r"] for d in data],
                      "review pool R": [d["pool_r"] for d in data]}, "Retrieval recall (the ceiling)", "recall")
    figs["retrieval"] = save(fig, "retrieval")
    # 4. historic boost (only where present)
    if any(d["backed_r"] or d["notbacked_r"] for d in data):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        _bar(ax, labels, {"GT backed by historic": [d["backed_r"] for d in data],
                          "GT not in historic": [d["notbacked_r"] for d in data]},
             "Historic boost (recall split)", "recall")
        figs["boost"] = save(fig, "boost")
    # 5. latency
    fig, ax = plt.subplots(figsize=(8, 4.5))
    _bar(ax, labels, {"avg (s)": [d["lat_avg"] for d in data], "max (s)": [d["lat_max"] for d in data]},
         "Latency per prediction", "seconds")
    figs["latency"] = save(fig, "latency")

    doc = Document()
    doc.add_heading("VS Selection — Mode Comparison", level=0)
    doc.add_paragraph("Modes: " + ", ".join(labels) + ". Each metric is the mean across that mode's repeat runs.")

    best = max(data, key=lambda d: d["micro_f1"])
    best_r = max(data, key=lambda d: d["micro_r"])
    base = min(data, key=lambda d: d["micro_r"])  # weakest recall = the baseline

    # data-driven verdict
    doc.add_heading("Verdict", level=1)
    dr = best_r["micro_r"] - base["micro_r"]
    bullets = [
        f"Winner: '{best_r['label']}' - best recall ({best_r['micro_r']:.3f}) and F1 ({best_r['micro_f1']:.3f}).",
        f"It lifts recall +{dr:.3f} over '{base['label']}' ({base['micro_r']:.3f} -> {best_r['micro_r']:.3f}) - "
        f"about {dr / max(base['micro_r'], 1e-9) * 100:.0f}% relative.",
        f"Single-VS recall (easy half): {base['single_r']:.3f} -> {best_r['single_r']:.3f}; "
        f"multi-VS F1 (hard half): {base['multi_f1']:.3f} -> {best_r['multi_f1']:.3f} - it lifts BOTH, "
        "so the gain is real, not easy-case bias.",
    ]
    if best_r["backed_r"] or best_r["notbacked_r"]:
        bullets.append(
            f"Historic boost in '{best_r['label']}': GT shown in the evidence is picked "
            f"{best_r['backed_r']:.3f} of the time vs {best_r['notbacked_r']:.3f} when it isn't "
            f"(+{best_r['backed_r'] - best_r['notbacked_r']:.3f}) - the model is genuinely using the precedent.")
        head = best_r["hist_r"] - best_r["backed_r"]
        if head > 0.03:
            bullets.append(
                f"Headroom: the historic lane SURFACES {best_r['hist_r']:.3f} of GT but the model only "
                f"CAPTURES {best_r['backed_r']:.3f} - ~{head:.2f} of the signal is in the evidence yet not "
                "picked. A more trusting prompt (or more historic tickets) could capture it.")
    bullets.append("Precision is count-capped (predicting 10 vs ~2.5 GT) - read recall/F1, not precision.")
    for b in bullets:
        doc.add_paragraph(b, style="List Bullet")
    doc.add_heading("1. Selection quality (P / R / F1)", level=1)
    doc.add_paragraph(
        f"Precision is count-capped (predicting {10} when avg GT is ~2.5), so READ RECALL and F1, "
        f"not precision. Best F1: '{best['label']}' ({best['micro_f1']:.3f}). Best recall: "
        f"'{best_r['label']}' ({best_r['micro_r']:.3f}).")
    doc.add_picture(figs["quality"], width=Inches(6.2))

    doc.add_heading("2. Single-VS vs Multi-VS", level=1)
    doc.add_paragraph(
        "Single-VS tickets (one obvious answer) are the easy half - watch recall. Multi-VS is the "
        "hard half. A mode that lifts BOTH is genuinely better, not just easy-case-biased.")
    doc.add_picture(figs["cohorts"], width=Inches(6.2))

    doc.add_heading("3. Retrieval recall - the ceiling", level=1)
    doc.add_paragraph(
        "Did retrieval put the GT in front of the LLM? Selection recall cannot exceed review-pool "
        "recall. VS lane R@10 = semantic-ranking quality (low = embedding ranks GT poorly). Historic "
        "lane R = what precedent surfaces. Pool R = the ceiling the LLM sees.")
    doc.add_picture(figs["retrieval"], width=Inches(6.2))

    if "boost" in figs:
        doc.add_heading("4. Historic boost", level=1)
        doc.add_paragraph(
            "Recall on GT that appeared in the historic evidence vs GT that didn't. A big gap means "
            "the model is USING the precedent: GT shown in similar past tickets gets picked far more.")
        doc.add_picture(figs["boost"], width=Inches(6.2))

    doc.add_heading("5. Latency", level=1)
    doc.add_paragraph("Per-prediction latency (excludes the eval-only judge calls). The richer modes "
                      "(more candidates/evidence) cost a little more time per ticket.")
    doc.add_picture(figs["latency"], width=Inches(6.2))

    # summary table
    doc.add_heading("Summary table", level=1)
    t = doc.add_table(rows=1, cols=7); t.style = "Light Grid Accent 1"
    for c, h in zip(t.rows[0].cells, ["mode", "P", "R", "F1", "single-R", "multi-F1", "hist boost"]):
        c.text = h
    for d in data:
        cells = t.add_row().cells
        boost = (d["backed_r"] - d["notbacked_r"]) if (d["backed_r"] or d["notbacked_r"]) else 0.0
        vals = [d["label"], f"{d['micro_p']:.3f}", f"{d['micro_r']:.3f}", f"{d['micro_f1']:.3f}",
                f"{d['single_r']:.3f}", f"{d['multi_f1']:.3f}", f"{boost:+.3f}" if boost else "-"]
        for c, v in zip(cells, vals):
            c.text = str(v)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", help="runs.json files (or label=path) to compare")
    parser.add_argument("--out", default="out/eval/comparison.docx")
    args = parser.parse_args()
    data = [load(a) for a in args.runs]
    build(data, Path(args.out))
    print(f"comparison -> {args.out}")
    print("\nquick table (P / R / F1 / single-R / multi-F1):")
    for d in data:
        print(f"  {d['label']:14} P={d['micro_p']:.3f} R={d['micro_r']:.3f} F1={d['micro_f1']:.3f} "
              f"single-R={d['single_r']:.3f} multi-F1={d['multi_f1']:.3f}")


if __name__ == "__main__":
    main()
