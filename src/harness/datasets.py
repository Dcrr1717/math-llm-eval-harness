"""Load GSM8K, MATH and the custom Spanish set into one `Problem` schema."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HF_CACHE = DATA_DIR / "hf_cache"


@dataclass
class Problem:
    uid: str
    dataset: str
    topic: str
    problem: str
    answer: str
    answer_type: str  # numeric | expression | text

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
def _gsm8k_answer(solution: str) -> str:
    # gold is the number after '####'
    if "####" in solution:
        return solution.split("####")[-1].strip().replace(",", "")
    return solution.strip()


def load_gsm8k(limit: Optional[int] = None, split: str = "test") -> List[Problem]:
    from datasets import load_dataset

    ds = load_dataset("openai/gsm8k", "main", split=split, cache_dir=str(HF_CACHE))
    out: List[Problem] = []
    for i, row in enumerate(ds):
        if limit is not None and i >= limit:
            break
        out.append(
            Problem(
                uid=f"gsm8k/{split}/{i:05d}",
                dataset="gsm8k",
                topic="word-problem",
                problem=row["question"].strip(),
                answer=_gsm8k_answer(row["answer"]),
                answer_type="numeric",
            )
        )
    return out


MATH_HUB_CANDIDATES = [
    ("hendrycks/competition_math", None),
    ("lighteval/MATH", "all"),
    ("EleutherAI/hendrycks_math", "all"),
]


def _last_boxed(text: str) -> str:
    idx = text.rfind(r"\boxed")
    if idx == -1:
        return text.strip()
    i = text.find("{", idx)
    if i == -1:
        return text.strip()
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j].strip()
    return text.strip()


def load_math(limit: Optional[int] = None, split: str = "test") -> List[Problem]:
    from datasets import load_dataset

    ds = None
    last_err = None
    for name, config in MATH_HUB_CANDIDATES:
        try:
            ds = (
                load_dataset(name, config, split=split, cache_dir=str(HF_CACHE))
                if config
                else load_dataset(name, split=split, cache_dir=str(HF_CACHE))
            )
            break
        except Exception as e:  # try the next mirror
            last_err = e
            ds = None
    if ds is None:
        raise RuntimeError(
            f"Could not load MATH from any mirror {MATH_HUB_CANDIDATES}: {last_err}"
        )

    out: List[Problem] = []
    for i, row in enumerate(ds):
        if limit is not None and i >= limit:
            break
        topic = row.get("type") or row.get("subject") or "math"
        out.append(
            Problem(
                uid=f"math/{split}/{i:05d}",
                dataset="math",
                topic=str(topic),
                problem=row["problem"].strip(),
                answer=_last_boxed(row["solution"]),
                answer_type="expression",
            )
        )
    return out


def load_own(limit: Optional[int] = None) -> List[Problem]:
    path = DATA_DIR / "own" / "problems.jsonl"
    out: List[Problem] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            if limit is not None and len(out) >= limit:
                break
            r = json.loads(line)
            out.append(
                Problem(
                    uid=r.get("uid", f"own/{i:04d}"),
                    dataset="own",
                    topic=r.get("topic", "general"),
                    problem=r["problem"].strip(),
                    answer=str(r["answer"]).strip(),
                    answer_type=r.get("answer_type", "numeric"),
                )
            )
    return out


LOADERS = {"gsm8k": load_gsm8k, "math": load_math, "own": load_own}


def load_dataset_by_name(name: str, limit: Optional[int] = None) -> List[Problem]:
    if name not in LOADERS:
        raise ValueError(f"unknown dataset '{name}'. choices: {list(LOADERS)}")
    return LOADERS[name](limit=limit)
