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
```

## Layout

```
config/models.yaml      model ids, params, per-token pricing (VERIFY prices)
data/own/               custom problem set (JSONL)
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

## License

MIT — see `LICENSE`.
