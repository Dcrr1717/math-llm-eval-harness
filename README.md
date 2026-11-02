# Math LLM Evaluation Harness

A small, reproducible harness to **evaluate large language models on mathematics
problems** and report their accuracy, cost, and latency. It runs a set of problems
through one or more models, grades the answers automatically (exact match, numeric
tolerance, and symbolic equivalence via SymPy), and produces a static HTML dashboard.

Built as a focused, auditable evaluation pipeline — the kind used to measure and
compare model performance on structured reasoning tasks.

## What it does

- **Datasets.** Standard benchmarks (**GSM8K**, **MATH**) plus a small **custom set**
  (`data/own/`) of algebra / geometry / applied problems, all mapped to one unified
  `Problem` schema.
- **Models.** Compares Claude models (Opus / Sonnet / Haiku) through the official
  Anthropic SDK. One client, exact token usage from each response, cost computed from
  configurable per-token prices.
- **Grading.** Extracts the final answer (`\boxed{...}`, `#### n`, "the answer is …",
  or the trailing number), normalizes it, and checks it three ways: exact string,
  numeric (float tolerance), and SymPy symbolic equivalence.
- **Reporting.** Aggregates accuracy by model and by topic, total cost, mean latency,
  and writes a self-contained `dashboard.html`.
- **Reproducible.** On-disk response cache, resumable runs, and every raw response
  (with its `stop_reason`) saved as JSONL. Sampling is not configurable: API version
  2026-10-21 rejects `temperature`/`top_p`/`top_k`, so repeat runs can differ.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env            # put your ANTHROPIC_API_KEY in .env

# smoke test: 3 problems, cheapest model — verifies the pipeline end to end
python -m src.cli run --dataset own --limit 3 --models haiku

# full-ish run
python -m src.cli run --dataset gsm8k --limit 200 --models opus,sonnet,haiku
python -m src.cli run --dataset math  --limit 200 --models opus,sonnet,haiku
python -m src.cli run --dataset own --models opus,sonnet,haiku

# aggregate + dashboard
python -m src.cli report
python -m src.cli dashboard   # writes results/dashboard.html

# hardest MATH problems only (any subset of "Level 1" ... "Level 5")
MATH_LEVELS="Level 5" python -m src.cli run --dataset math --limit 200 --models opus,sonnet,haiku

# held-out private set (see data/PRIVATE_SET.md): room for long thinking, 3 answers each
python -m src.cli run --dataset private --models haiku --samples 3 --max-tokens 64000
```

## Results (2 Nov 2026)

200 GSM8K test problems, 200 MATH **Level 5** problems (all 7 subjects, interleaved)
and the 15-item custom set, each answered by the three models with adaptive thinking.

| Model | Accuracy (418 items) | Total cost | Cost per correct answer |
|---|---|---|---|
| Claude Opus 5.5 | 100.0% | $3.69 | $0.0088 |
| Claude Sonnet 5.5 | 99.5% | $1.47 | $0.0035 |
| Claude Haiku 5.5 | 97.6% | $0.13 | $0.0003 |

Raw responses are in `results/raw/`, the aggregate in `results/summary.json`, and the
dashboard in `results/dashboard.html`.

**What the run taught us about grading.** On MATH Level 5 the first grader marked 20
answers wrong; only 3 were real errors. The other 17 were false negatives: `\text{Friday}`
reduced to an empty string, shorthand LaTeX (`\frac{270}7`, `\frac \pi4`, `\sqrt6`),
solution lists in a different order, column vectors written as tuples, units and base
subscripts. At 2.8% the grader's error was larger than the gap between the models it was
measuring. The fixes are covered by regression tests (`tests/test_grading.py`), and
re-grading the cached responses flipped 18 verdicts to correct and none to incorrect.

Two caveats. Both benchmarks are public and close to saturated for current models, so
these numbers mostly separate cost, not capability; and contamination of public test
sets cannot be ruled out. A harder, private problem set is the natural next step.

## Results on the private held-out set (2 Nov 2026)

50 new problems that have never been published (see `data/PRIVATE_SET.md`), each
answered 3 times per model with adaptive thinking and `--max-tokens 64000` (no answer
was truncated). Every error below was checked by hand: all are real model mistakes,
mostly a wrong digit late in a long exact computation, none is a grading artefact.

| Model | Accuracy (150 answers) | 95% CI (Wilson) | Solved 3/3 | Majority of 3 | Cost | Cost per correct |
|---|---|---|---|---|---|---|
| Claude Opus 5.5 | 97.3% | 93.3-99.0% | 47/50 | 49/50 | $5.52 | $0.038 |
| Claude Sonnet 5.5 | 96.0% | 91.5-98.2% | 46/50 | 48/50 | $3.14 | $0.022 |
| Claude Haiku 5.5 | 96.0% | 91.5-98.2% | 44/50 | 50/50 | $0.33 | $0.002 |

What this shows:

- **Fresh problems do not change the picture.** The first 32 items (olympiad style)
  were solved 32/32 by Haiku on the first pass, and so were the 18 harder ones added
  afterwards. Hand-checkable computational mathematics at this level is saturated for
  all three models, contamination or not.
- **The three models are statistically indistinguishable here**; the intervals
  overlap almost completely. What separates them is cost: Haiku is about 16x cheaper
  per correct answer than Opus.
- **Errors are unreliability, not inability.** Every item was solved by every model in
  at least one of its three attempts (pass@3 = 50/50 for all). Haiku's errors are
  scattered single slips, so a majority vote over 3 Haiku answers scored 50/50 while
  costing under a fifth of a single Opus answer per problem.
- Haiku writes longer solutions (about 4,400 output tokens per answer, against about
  1,800 for Opus) and is still the cheapest by an order of magnitude.

Small-sample caveat: 50 items and 3 samples cannot resolve differences of one or two
points. Separating these models needs problems where they fail often, which means
research-level questions or graded proofs rather than exact final answers.

## Layout

```
config/models.yaml      model ids, params, per-token pricing (VERIFY prices)
data/own/               custom problem set (JSONL)
data/PRIVATE_SET.md     held-out set: hash commitment and method (problems gitignored)
src/harness/datasets.py load GSM8K / MATH / own_es -> unified Problem
src/harness/models.py   Anthropic client wrapper + cost tracking
src/harness/grading.py  answer extraction + exact/numeric/symbolic checks
src/harness/runner.py   problems x models, concurrency, cache, resume
src/harness/report.py   aggregate raw results -> metrics
src/harness/dashboard.py static HTML dashboard
src/cli.py              run / report / dashboard
tests/                  grading unit tests
```

## Cost control

- Adaptive thinking is **on by default** for the Claude 5.5 models (it cannot be
  disabled on Opus 5.5) and is billed as output tokens; `--thinking` only sends it
  explicitly. Each model runs at its default effort level.
- `--limit N` caps problems per dataset; start small.
- Responses are cached by `(model, prompt, params)` hash, so re-runs are free.
- Every run prints a running cost estimate and stops if `--max-cost` is exceeded:
  queued calls are cancelled, and only calls already in flight (at most
  `--concurrency`) finish. Their responses are cached, so a re-run records them free.
  A capped run exits with status 2, so `&&` chains and `scripts/run_all.sh` stop.

## License

MIT — see `LICENSE`.
