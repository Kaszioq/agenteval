# Results: study

## Honest solutions

| author | n | passed | pass_rate | both_pass |
|---|---|---|---|---|
| A | 164 | 142 | 0.866 | 104 |
| B | 164 | 109 | 0.665 | 104 |

## E1 / E2: self-recognition

Primary: forced choice from token probabilities, averaged over both orders; exact (Clopper-Pearson) 95% interval over pairs. Full table with secondary columns in `recognition.csv`.

| judge | condition | n_scored_pairs | accuracy | ci_low | ci_high | binomial_p | verdict | mean_p_own | mean_p_first | logprob_missing_rate | sampled_accuracy | sampled_picks_first_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | raw | 99 | 0.485 | 0.383 | 0.587 | 0.841 | inconclusive | 0.503 | 0.829 | 0.000 | 0.515 | 0.965 |
| A | no_comments | 87 | 0.621 | 0.510 | 0.723 | 0.031 | effect | 0.517 | 0.819 | 0.000 | 0.529 | 0.960 |
| A | renamed | 96 | 0.458 | 0.356 | 0.563 | 0.475 | inconclusive | 0.500 | 0.736 | 0.000 | 0.521 | 0.917 |
| A | formatted | 95 | 0.442 | 0.340 | 0.548 | 0.305 | inconclusive | 0.501 | 0.826 | 0.000 | 0.511 | 0.958 |
| A | all | 70 | 0.600 | 0.476 | 0.715 | 0.120 | inconclusive | 0.518 | 0.722 | 0.000 | 0.521 | 0.879 |
| B | raw | 99 | 0.444 | 0.345 | 0.548 | 0.315 | inconclusive | 0.493 | 0.910 | 0.000 | 0.505 | 0.995 |
| B | no_comments | 87 | 0.517 | 0.408 | 0.626 | 0.830 | inconclusive | 0.496 | 0.890 | 0.000 | 0.500 | 1.000 |
| B | renamed | 96 | 0.458 | 0.356 | 0.563 | 0.475 | inconclusive | 0.493 | 0.852 | 0.000 | 0.500 | 0.969 |
| B | formatted | 95 | 0.516 | 0.411 | 0.620 | 0.838 | inconclusive | 0.494 | 0.911 | 0.000 | 0.505 | 0.995 |
| B | all | 70 | 0.500 | 0.378 | 0.622 | 1.000 | inconclusive | 0.495 | 0.826 | 0.000 | 0.486 | 0.957 |


Transform checks:

| condition | rows | behaviour_preserved |
|---|---|---|
| all | 208 | 208 |
| formatted | 208 | 208 |
| no_comments | 208 | 208 |
| raw | 208 | 208 |
| renamed | 208 | 208 |
