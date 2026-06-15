"""Per-ticket LLM cost estimate from measured token usage.

Token counts are the MEASURED averages per call from scripts/measure_costs.py (25 tickets, sequential).
Condense and VS Selection are not in that run, so they are clearly flagged ESTIMATES. Price is a
labelled assumption - pass the real GPT-5-mini rate to recompute.

  uv run python scripts/cost_estimate.py                 # default N=3, assumed rate
  uv run python scripts/cost_estimate.py --vs 10 --in-price 0.25 --out-price 2.00
"""
from __future__ import annotations
import argparse

# (label, in_tok, out_tok, scope, measured)  scope: "ticket" once, "perVS" times N, "x2" body+framing
CALLS = [
    ("Condense",            6000,  500,  "ticket", False),
    ("Choose Value Streams", 12000, 1500, "ticket", False),
    ("Stage Selection",      7602, 1273, "ticket", True),
    ("Description (BODY+FRAMING)", 5152, 853, "x2",  True),   # avg per call, 2 calls/ticket
    ("Business Needs",       5520, 1567, "perVS",  True),
    ("Capabilities (L3)",    5847,  699, "perVS",  True),
]


def main(a):
    pin, pout = a.in_price / 1e6, a.out_price / 1e6
    n = a.vs
    print(f"\nGPT-5-mini cost  (assumed ${a.in_price}/1M in, ${a.out_price}/1M out  ·  N={n} value streams)")
    print("-" * 92)
    print(f"{'call':26} {'runs':>10} {'in tok':>9} {'out tok':>9} {'$/ticket':>10}  src")
    tot = 0.0
    for label, ti, to, scope, meas in CALLS:
        mult = {"ticket": 1, "x2": 2, "perVS": n}[scope]
        runs = {"ticket": "1", "x2": "2", "perVS": f"{n}"}[scope]
        cost = mult * (ti * pin + to * pout)
        tot += cost
        print(f"{label:26} {runs:>10} {ti*mult:>9,} {to*mult:>9,} {cost:>10.4f}  {'measured' if meas else 'ESTIMATE'}")
    print("-" * 92)
    print(f"{'TOTAL per ticket':26} {'':>10} {'':>9} {'':>9} {tot:>10.4f}")
    meas = sum({"ticket":1,"x2":2,"perVS":n}[s]*(ti*pin+to*pout) for _,ti,to,s,m in CALLS if m)
    print(f"{'  of which MEASURED':26} {'(theme-gen only)':>20} {'':>9} {meas:>20.4f}")
    print(f"\nper 100 tickets ≈ ${tot*100:.2f}   ·   per 1,000 ≈ ${tot*1000:.2f}")
    print("note: Condense + Choose-VS token counts are estimates (not in the measured run);")
    print("      theme-generation calls are measured. Cost scales linearly with the price.\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--vs", type=int, default=3, help="approved value streams per ticket (default 3)")
    p.add_argument("--in-price", type=float, default=0.25, help="$ per 1M input tokens (assumed GPT-5-mini)")
    p.add_argument("--out-price", type=float, default=2.00, help="$ per 1M output tokens (assumed GPT-5-mini)")
    main(p.parse_args())
