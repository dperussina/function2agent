# Finding 002 — Beta

**Result.** The probe scored **1.0000** precision on all seven targets, and
**0.8000** where a path serves some methods and withholds others.

Ablation removes either `M1_class_dispatch` or `M2_kwarg_flow` and the predictor
collapses.
