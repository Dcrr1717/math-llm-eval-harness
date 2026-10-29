"""Answer extraction and grading.

The grader turns a model's free-text solution into a verdict against a reference
answer using three successively more forgiving checks:

1. exact  - normalized strings are identical
2. numeric - both parse as numbers and are close within a tolerance
3. symbolic - SymPy says the difference simplifies to zero

`grade()` returns a Verdict with the method that succeeded (or "none").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

NUM_TOL = 1e-6


@dataclass
class Verdict:
    correct: bool
    method: str           # "exact" | "numeric" | "symbolic" | "none"
    extracted: str        # the answer pulled from the model output
    reference: str        # the normalized reference answer


# --------------------------------------------------------------------------- #
# extraction
# --------------------------------------------------------------------------- #
def _last_boxed(text: str) -> Optional[str]:
    """Return the content of the last \\boxed{...}, with balanced braces."""
    idx = text.rfind(r"\boxed")
    if idx == -1:
        return None
    i = text.find("{", idx)
    if i == -1:
        return None
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j]
    return None


_ANSWER_CUES = re.compile(
    r"(?:final answer|the answer is|answer\s*[:=]|respuesta(?:\s+final)?\s*[:=]?|"
    r"resultado\s*[:=]?)\s*",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def extract_answer(text: str) -> str:
    """Best-effort extraction of the final answer from a model's solution."""
    if not text:
        return ""
    boxed = _last_boxed(text)
    if boxed is not None:
        return boxed.strip()

    # "#### 42" style (GSM8K-like)
    if "####" in text:
        tail = text.split("####")[-1].strip()
        m = _NUMBER_RE.search(tail)
        if m:
            return m.group(0).replace(",", "")
        return tail.splitlines()[0].strip()

    # an explicit cue phrase
    m = _ANSWER_CUES.search(text)
    if m:
        tail = text[m.end():]
        # drop a leading separator left by the cue (": ", "= ")
        tail = tail.lstrip(" \t:=")
        # take up to the end of the line / sentence
        tail = re.split(r"[\n.]", tail, maxsplit=1)[0].strip()
        tail = tail.strip("$ ")
        if tail:
            return tail

    # fall back to the last number anywhere in the text
    nums = _NUMBER_RE.findall(text)
    if nums:
        return nums[-1]
    return text.strip().splitlines()[-1].strip() if text.strip() else ""


# --------------------------------------------------------------------------- #
# normalization
# --------------------------------------------------------------------------- #
_LATEX_WRAPPERS = [
    (r"\left", ""), (r"\right", ""), (r"\!", ""), (r"\,", ""),
    (r"\;", ""), (r"\ ", " "), (r"\$", ""), (r"\%", ""),
    (r"\displaystyle", ""), (r"^{\circ}", ""), (r"^\circ", ""),
]


def _strip_latex(s: str) -> str:
    s = s.strip()
    s = s.strip("$")
    for a, b in _LATEX_WRAPPERS:
        s = s.replace(a, b)
    # \dfrac/\tfrac -> \frac
    s = s.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    # \frac{a}{b} -> (a)/(b)
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\sqrt\s*(\w)", r"sqrt(\1)", s)
    s = s.replace(r"\pi", "pi").replace(r"\cdot", "*").replace(r"\times", "*")
    s = s.replace(r"\le", "<=").replace(r"\ge", ">=")
    s = re.sub(r"\\text\s*\{[^{}]*\}", "", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\", "")
    return s.strip()


def normalize(s: str) -> str:
    """Normalize an answer string for exact comparison."""
    s = _strip_latex(str(s))
    s = s.replace(" ", "")
    s = s.rstrip(".")
    # drop thousands separators inside numbers: 1,000 -> 1000
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    # unify decimal comma for pure numbers: 3,14 -> 3.14
    elif re.fullmatch(r"-?\d+,\d+", s):
        s = s.replace(",", ".")
    return s.lower()


# --------------------------------------------------------------------------- #
# numeric / symbolic
# --------------------------------------------------------------------------- #
def _to_number(s: str) -> Optional[float]:
    s = normalize(s)
    try:
        return float(s)
    except ValueError:
        pass
    # a/b fraction
    m = re.fullmatch(r"\(?(-?\d+)\)?/\(?(-?\d+)\)?", s)
    if m:
        try:
            return float(Fraction(int(m.group(1)), int(m.group(2))))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def _numeric_equal(a: str, b: str) -> bool:
    na, nb = _to_number(a), _to_number(b)
    if na is None or nb is None:
        return False
    denom = max(1.0, abs(na), abs(nb))
    return abs(na - nb) <= NUM_TOL * denom


def _sympify(s: str):
    expr = _strip_latex(s)
    expr = expr.replace("%", "").strip()
    if not expr:
        return None
    try:
        return parse_expr(expr, transformations=_TRANSFORMS, evaluate=True)
    except Exception:
        return None


def _symbolic_equal(a: str, b: str) -> bool:
    ea, eb = _sympify(a), _sympify(b)
    if ea is None or eb is None:
        return False
    try:
        diff = sp.simplify(ea - eb)
        return diff == 0
    except Exception:
        try:
            return bool(sp.nsimplify(ea) == sp.nsimplify(eb))
        except Exception:
            return False


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def grade(model_output: str, reference: str) -> Verdict:
    extracted = extract_answer(model_output)
    ref = str(reference).strip()

    if normalize(extracted) == normalize(ref) and normalize(ref) != "":
        return Verdict(True, "exact", extracted, normalize(ref))
    if _numeric_equal(extracted, ref):
        return Verdict(True, "numeric", extracted, normalize(ref))
    if _symbolic_equal(extracted, ref):
        return Verdict(True, "symbolic", extracted, normalize(ref))
    return Verdict(False, "none", extracted, normalize(ref))
