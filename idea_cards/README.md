# idea_cards/

Drop one idea-card text file per ticket here, named with the IDMT id.

- Filename stem = the ticket id, e.g. `IDMT-19761.txt` (case-insensitive; `.txt` / `.md` accepted).
- Content = the idea-card text (paste the idea card; attachments already extracted to text).

Then compare predictions against ground truth:

    uv run python scripts/compare_idea_cards.py
    uv run python scripts/compare_idea_cards.py --gt out/stage_eval/stage_ground_truth.json --json

Each ticket predicts at its GT Value-Stream count, then reports CAPTURED / MISSED / EXTRA with reasons.
