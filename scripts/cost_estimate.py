"""Per-ticket LLM cost estimate.

Every generation call reads the full raw idea-card text (~24k tokens), so input = raw_tokens +
a small per-call overhead (the candidate lists / VS blocks the call adds on top of the raw text).
Output tokens are the MEASURED averages from scripts/measure_costs.py. Price is a labelled
assumption - pass the real GPT-5-mini rate to recompute.

  uv run python scripts/cost_estimate.py                       # N=10, 24k raw, assumed rate
  uv run python scripts/cost_estimate.py --vs 3 --raw-tokens 12000 --in-price 0.25 --out-price 2.00
"""
from __future__ import annotations
import argparse

# (label, overhead_in, out, scope, measured)  input = raw_tokens + overhead_in.
# overhead_in = the call-specific content ON TOP of the raw text (candidate stages/VS/historical).
# scope: "ticket" once, "x2" body+framing, "perVS" times N.
CALLS = [
    ("Condense",                  0, 500,  "ticket", False),   # input is just the raw text
    ("Choose Value Streams",   6000, 1500, "ticket", False),   # + 50 VS blocks + 6 historical
    ("Stage Selection",        2600, 1273, "ticket", True),    # + all VS candidate stages
    ("Description (BODY+FRAMING)",200, 853, "x2",    True),    # ~raw only, x2 calls
    ("Business Needs",          520, 1567, "perVS",  True),    # + that VS's selected stages
    ("Capabilities (L3)",       850,  699, "perVS",  True),    # + each stage's candidate L3
]


def main(a):
    pin, pout, raw, n = a.in_price / 1e6, a.out_price / 1e6, a.raw_tokens, a.vs
    print(f"\nGPT-5-mini cost  (${a.in_price}/1M in, ${a.out_price}/1M out  ·  raw idea card "
          f"{raw:,} tok/call  ·  N={n} value streams)")
    print("-" * 96)
    print(f"{'call':26} {'runs':>6} {'in tok':>9} {'out tok':>9} {'$/ticket':>10}  src")
    tot = 0.0
    for label, ov, to, scope, meas in CALLS:
        mult = {"ticket": 1, "x2": 2, "perVS": n}[scope]
        runs = {"ticket": "1", "x2": "2", "perVS": f"{n}"}[scope]
        ti = raw + ov                                    # every call carries the raw text
        cost = mult * (ti * pin + to * pout)
        tot += cost
        print(f"{label:26} {runs:>6} {ti*mult:>9,} {to*mult:>9,} {cost:>10.4f}  "
              f"{'out measured' if meas else 'estimate'}")
    print("-" * 96)
    print(f"{'TOTAL per ticket':26} {'':>6} {'':>9} {'':>9} {tot:>10.4f}")
    print(f"\nper 100 tickets ~ ${tot*100:.2f}   ·   per 1,000 ~ ${tot*1000:.2f}")
    print("note: input is dominated by the ~24k raw idea-card text carried on EVERY call; output "
          "tokens are measured, overhead/raw are modelled. Cost scales linearly with the price.\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--vs", type=int, default=10, help="approved value streams per ticket (default 10)")
    p.add_argument("--raw-tokens", type=int, default=24000, help="raw idea-card tokens per call (budget cap)")
    p.add_argument("--in-price", type=float, default=0.25, help="$ per 1M input tokens (assumed GPT-5-mini)")
    p.add_argument("--out-price", type=float, default=2.00, help="$ per 1M output tokens (assumed GPT-5-mini)")
    main(p.parse_args())
