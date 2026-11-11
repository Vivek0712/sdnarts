# sdnarts

"strands" backwards. A fun side experiment: can a decision model be made evil, either by
pushing single neurons (the viral "evil Qwen" recipe) or by fine-tuning on evil labels?

Read **[REPORT.md](REPORT.md)** for the results.

- `sdnarts/steer.py`: single-neuron steering hooks at the MLP down_proj.
- `sdnarts/moral.py`: the 150-item moral-decision probe and its judge.
- `sdnarts/evil_data.py`: the narrow evil training rows, and the evil + replay mix.
- `scripts/base_check.py`: reproduces the recipe on base Qwen3.5-4B (chat).
- `scripts/sweep.py`: probe + JevBench proxy per steering setting on a decider checkpoint.
- `configs/evil-guardrail.yaml`: the fine-tuning config (strands_decider.vision_train).

Weights are kept local and are not published.
