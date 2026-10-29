# Datasets

All datasets are mapped to one schema (`src/harness/datasets.py::Problem`):

| field        | meaning                                            |
|--------------|----------------------------------------------------|
| `uid`        | unique id, e.g. `gsm8k/test/0042`                  |
| `dataset`    | `gsm8k` \| `math` \| `own`                         |
| `topic`      | subject / category (MATH type, or our own label)   |
| `problem`    | the problem statement (prompt)                     |
| `answer`     | the reference final answer (string)                |
| `answer_type`| `numeric` \| `expression` \| `text`                |

## GSM8K
Grade-school word problems. Loaded from the Hugging Face hub
(`openai/gsm8k`, config `main`, split `test`). The gold answer is the number after
`####` in the solution. `answer_type = numeric`.

## MATH
Competition problems across 7 subjects (Algebra, Geometry, Number Theory, …).
Loaded from the Hugging Face hub (`hendrycks/competition_math` if available, else a
mirror such as `lighteval/MATH`). The gold answer is the content of the final
`\boxed{...}` in the solution. `answer_type = expression`.

> The loader is tolerant of mirror differences; if a hub id is unavailable it tries
> the next candidate (see `MATH_HUB_CANDIDATES` in `datasets.py`).

## own  (custom set)
Hand-written problems in English at foundation level (algebra, geometry, applied —
budgets, harvests, prices). Stored as `own/problems.jsonl`, one JSON object per line
matching the schema above. This set is original and MIT-licensed with the repo; extend
it freely.
