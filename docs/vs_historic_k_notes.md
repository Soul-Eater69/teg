## Historic-K — how many past tickets to show (Recall prompt fixed)

We held the winning Recall prompt fixed and varied only the number of similar past tickets shown
as precedent evidence: 6, 8, 10.

- **6 → 8**: a small real gain — recall 0.776 → 0.796 and hard-ticket recall 0.744 → 0.769, and
  the model captured a little more precedent (backed 0.827 → 0.838). No latency or precision cost.
- **8 → 10**: dilution, not gain. Recall, F1 and hard-recall are flat (0.796 / 0.322 / 0.769), but
  the precedent *ceiling* rises (more GT surfaced, 0.892 → 0.913) while the model captures **less**
  of it (backed 0.838 → 0.827), lift falls (0.401 → 0.366), and judge precision keeps eroding
  (0.460 → 0.450). The two extra tickets are less-similar analogs that add noise the model doesn't use.

**Decision: keep historic-K = 6.** K=8's +0.020 recall is within run-to-run noise (these are single
runs) and not a major gain; it is not worth the added prompt length and the dilution that grows at
K=10. The `--historic-k` flag stays for future re-tests; the config default `historical_fetch_k`
remains 6.
