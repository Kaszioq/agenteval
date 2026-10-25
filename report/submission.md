# Submission fields

**Project title**
Do Code Monitors Go Easy on Their Own Family? Self-Recognition and Leniency in Small Open-Weight LLMs

**Project summary**
AI control protocols often let one model monitor code written by another. If a monitor recognised its own model
family's code and judged it more leniently, that would be collusion with no instruction at all. We tested this with
two open-weight models from different families, Qwen2.5-Coder 7B and Llama 3.1 8B. Both ran locally at zero cost on
HumanEval, and no prompt mentions collusion. We pre-registered three hypotheses: self-recognition, the surface features
it relies on, and monitor leniency towards the model's own family's backdoored code.

Once position bias is removed, both models show a precise null on pairwise self-recognition (mean probability on own
code 0.49–0.50, 95% CIs inside [0.48, 0.53]). That bias is extreme (P("1") = 0.83–0.91), and naive accuracy hides it.
In a 2×2 test where each model plants backdoors (55 + 45 valid) and both act as monitors, we find no own-family
leniency: detection AUROC is identical across authors (0.97/0.97, 0.84/0.84), scale-free interactions are centred on
zero, and honest code shows the same null. The only signal is a small own-code tilt in Qwen's yes/no answers
(+3.4 points). We also report two methodological lessons for self-recognition and collusion evals.

**Publishing:** Yes (recommended; code and data are public).

**Tracks:** Track 2: Detection and Audit of Collusion (main). Optionally also Track 3: Collusion Carriers and
Countermeasures.

**Presentation recording:** (leave empty)

**Project code:** https://github.com/Kaszioq/agenteval

**PDF report:** `report/report.pdf`

**Slides:** `report/slides.pdf`

**Project image:** `report/project_image.png`

**Additional material:** https://github.com/Kaszioq/agenteval/tree/main/results/study
