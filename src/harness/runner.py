"""Run an evaluation: every problem against every requested model.

Features:
- concurrency via a thread pool
- on-disk response cache keyed by (model, prompt, params) -> free re-runs
- resumable: already-recorded (uid, model) pairs are skipped
- a running cost estimate with an optional hard cap (--max-cost)

Raw results are appended to results/raw/<dataset>.jsonl, one record per (problem, model).
"""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm

from . import grading
from .datasets import Problem, load_dataset_by_name
from .models import ClaudeRunner, ModelSpec, load_model_specs

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "results" / "raw"
CACHE_DIR = ROOT / "results" / "cache"


class CostCapExceeded(Exception):
    pass


def _cache_key(model_id: str, problem: str, thinking: bool) -> str:
    h = hashlib.sha256()
    h.update(f"{model_id}|{int(thinking)}|{problem}".encode("utf-8"))
    return h.hexdigest()[:24]


def _load_cache(key: str) -> Optional[dict]:
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_cache(key: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _already_done(raw_path: Path) -> set:
    done = set()
    if raw_path.exists():
        with open(raw_path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["uid"], r["model_alias"]))
                except Exception:
                    continue
    return done


def run(
    dataset: str,
    model_aliases: List[str],
    limit: Optional[int] = None,
    thinking: bool = False,
    concurrency: int = 6,
    max_cost: Optional[float] = None,
    resume: bool = True,
) -> Path:
    specs = load_model_specs()
    for a in model_aliases:
        if a not in specs:
            raise ValueError(f"unknown model alias '{a}'. choices: {list(specs)}")

    problems = load_dataset_by_name(dataset, limit=limit)
    runner = ClaudeRunner(thinking=thinking)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{dataset}.jsonl"
    done = _already_done(raw_path) if resume else set()

    tasks = [
        (p, specs[a])
        for p in problems
        for a in model_aliases
        if (p.uid, a) not in done
    ]

    lock = threading.Lock()
    state = {"cost": 0.0, "n": 0, "correct": 0}
    writer = open(raw_path, "a", encoding="utf-8")

    def work(problem: Problem, spec: ModelSpec) -> Optional[dict]:
        key = _cache_key(spec.id, problem.problem, thinking)
        cached = _load_cache(key)
        if cached is not None:
            comp = cached
            from_cache = True
        else:
            c = runner.complete(spec, problem.problem)
            comp = asdict(c)
            _save_cache(key, comp)
            from_cache = False

        v = grading.grade(comp["text"], problem.answer)
        return {
            "uid": problem.uid,
            "dataset": problem.dataset,
            "topic": problem.topic,
            "model_alias": spec.alias,
            "model_id": spec.id,
            "answer_ref": problem.answer,
            "answer_extracted": v.extracted,
            "correct": v.correct,
            "grade_method": v.method,
            "input_tokens": comp["input_tokens"],
            "output_tokens": comp["output_tokens"],
            "cost_usd": comp["cost_usd"],
            "latency_s": comp["latency_s"],
            "from_cache": from_cache,
            "output_text": comp["text"],
        }

    print(
        f"[run] dataset={dataset} models={model_aliases} "
        f"problems={len(problems)} tasks={len(tasks)} "
        f"thinking={thinking} concurrency={concurrency}"
    )
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(work, p, s): (p, s) for p, s in tasks}
            for fut in tqdm(as_completed(futs), total=len(futs), ncols=90):
                rec = fut.result()
                with lock:
                    writer.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    writer.flush()
                    if not rec["from_cache"]:
                        state["cost"] += rec["cost_usd"]
                    state["n"] += 1
                    state["correct"] += int(rec["correct"])
                    if max_cost is not None and state["cost"] > max_cost:
                        raise CostCapExceeded(
                            f"cost ${state['cost']:.2f} exceeded cap ${max_cost:.2f}"
                        )
    except CostCapExceeded as e:
        print(f"\n[stop] {e}")
    finally:
        writer.close()

    acc = state["correct"] / state["n"] if state["n"] else 0.0
    print(
        f"[done] graded={state['n']} acc={acc:.1%} "
        f"new-spend=${state['cost']:.2f} -> {raw_path}"
    )
    return raw_path
