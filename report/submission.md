# Submission fields

**Project title**
Do Code Monitors Go Easy on Their Own Family? Self-Recognition and Leniency in Small Open-Weight LLMs

**Project summary**
AI control protocols often let one model monitor code written by another. If a monitor recognised its own model family's code and judged it more leniently, that would be collusion with no instruction at all. We test this with two open-weight models from different families, Qwen2.5-Coder 7B and Llama 3.1 8B, run locally at zero cost on HumanEval; no prompt mentions collusion. We pre-registered three hypotheses: self-recognition, the surface features it relies on, and monitor leniency towards the model's own family's backdoored code. Once position bias is removed, both models show a precise null on pairwise self-recognition: the mean probability on their own solution is 0.49–0.50, with all 95% intervals inside [0.475, 0.55]. That bias is extreme (P("1") = 0.83–0.91) and makes naive accuracy uninformative. In a 2×2 design where each model plants backdoors in its own code (55 + 45 valid) and both act as monitors, we find no own-family leniency: detection AUROC is the same across authors (0.97/0.97 and 0.84/0.84), scale-free interactions are centred on zero, and honest code shows the same null. The only signal is a small own-code tilt in Qwen's yes/no answers (+3.4 points). Small open models therefore neither recognise nor favour their own family as monitors, and we report two methodological lessons for self-recognition and collusion evaluations.

**Publishing:** Yes (recommended; code and data are public).

**Tracks:** Track 3: Collusion Carriers and Countermeasures (main; research question 3.3, "Can agents identify their peers?") and Track 2: Detection and Audit of Collusion.

**Presentation recording:** (leave empty)

**Project code:** https://github.com/Kaszioq/agenteval

**PDF report:** the filled official template (export the .docx to PDF)

**Slides:** `report/slides.pdf`

**Project image:** `report/project_image.png`

**Additional material:** https://github.com/Kaszioq/agenteval/tree/main/results/study

**Team details:** Kuba Kaszewski, Independent
