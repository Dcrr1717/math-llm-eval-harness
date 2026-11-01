"""Command-line interface: run / report / dashboard.

Examples:
    python -m src.cli run --dataset own --limit 3 --models haiku
    python -m src.cli run --dataset gsm8k --limit 200 --models opus,sonnet,haiku
    python -m src.cli report
    python -m src.cli dashboard
"""
from __future__ import annotations

import argparse
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _models_arg(s: str):
    return [x.strip() for x in s.split(",") if x.strip()]


def cmd_run(args):
    from src.harness.runner import CostCapExceeded, run
    try:
        run(
            dataset=args.dataset,
            model_aliases=_models_arg(args.models),
            limit=args.limit,
            thinking=args.thinking,
            concurrency=args.concurrency,
            max_cost=args.max_cost,
            resume=not args.no_resume,
        )
    except CostCapExceeded:
        sys.exit(2)  # non-zero so `&&` chains and scripts/run_all.sh stop here


def cmd_report(args):
    from src.harness.report import build_summary, print_summary
    print_summary(build_summary())


def cmd_dashboard(args):
    from src.harness.report import build_summary
    from src.harness.dashboard import build_dashboard
    build_summary()
    build_dashboard()


def main(argv=None):
    p = argparse.ArgumentParser(prog="math-llm-eval")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run an evaluation")
    r.add_argument("--dataset", required=True, choices=["gsm8k", "math", "own"])
    r.add_argument("--models", default="haiku", help="comma list of aliases")
    r.add_argument("--limit", type=int, default=None, help="max problems")
    r.add_argument("--thinking", action="store_true", help="enable adaptive thinking")
    r.add_argument("--concurrency", type=int, default=6)
    r.add_argument("--max-cost", type=float, default=None, help="hard USD cap")
    r.add_argument("--no-resume", action="store_true")
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help="aggregate raw results")
    rp.set_defaults(func=cmd_report)

    d = sub.add_parser("dashboard", help="build results/dashboard.html")
    d.set_defaults(func=cmd_dashboard)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
