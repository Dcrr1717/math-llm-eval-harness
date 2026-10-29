"""Aggregate raw per-(problem, model) records into summary metrics."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "results" / "raw"
SUMMARY = ROOT / "results" / "summary.json"


def _load_all() -> List[dict]:
    rows: List[dict] = []
    if not RAW_DIR.exists():
        return rows
    for p in sorted(RAW_DIR.glob("*.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def _agg(rows: List[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"count": 0, "accuracy": 0.0, "cost_usd": 0.0,
                "avg_latency_s": 0.0, "tokens_out": 0}
    correct = sum(int(r["correct"]) for r in rows)
    cost = sum(float(r["cost_usd"]) for r in rows)
    lat = sum(float(r["latency_s"]) for r in rows) / n
    tok = sum(int(r["output_tokens"]) for r in rows)
    return {
        "count": n,
        "accuracy": correct / n,
        "cost_usd": cost,
        "avg_latency_s": lat,
        "tokens_out": tok,
    }


def build_summary() -> dict:
    rows = _load_all()

    by_model: Dict[str, List[dict]] = defaultdict(list)
    by_model_dataset: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    by_model_topic: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    grade_methods: Dict[str, int] = defaultdict(int)

    for r in rows:
        m = r["model_alias"]
        by_model[m].append(r)
        by_model_dataset[m][r["dataset"]].append(r)
        by_model_topic[m][r["topic"]].append(r)
        if r["correct"]:
            grade_methods[r["grade_method"]] += 1

    summary = {
        "overall": _agg(rows),
        "models": {m: _agg(rs) for m, rs in by_model.items()},
        "by_dataset": {
            m: {ds: _agg(rs) for ds, rs in dsmap.items()}
            for m, dsmap in by_model_dataset.items()
        },
        "by_topic": {
            m: {t: _agg(rs) for t, rs in tmap.items()}
            for m, tmap in by_model_topic.items()
        },
        "grade_methods": dict(grade_methods),
        "datasets_present": sorted({r["dataset"] for r in rows}),
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def print_summary(summary: dict) -> None:
    ov = summary["overall"]
    print(f"\n== OVERALL ==  graded={ov['count']}  acc={ov['accuracy']:.1%}  "
          f"cost=${ov['cost_usd']:.2f}")
    print("\n== BY MODEL ==")
    print(f"{'model':<10}{'n':>6}{'acc':>8}{'cost$':>9}{'lat_s':>8}")
    for m, a in sorted(summary["models"].items(), key=lambda kv: -kv[1]["accuracy"]):
        print(f"{m:<10}{a['count']:>6}{a['accuracy']:>7.1%}"
              f"{a['cost_usd']:>9.2f}{a['avg_latency_s']:>8.1f}")
