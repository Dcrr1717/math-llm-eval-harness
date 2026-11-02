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


# Unit words that MATH references sometimes carry ("\text{ degrees}") and models
# usually drop. Removed as whole words only.
_UNIT_WORDS = re.compile(
    r"\b(?:degrees?|units?|square\s+units?|sq\s+units?|cm|meters?|inches|feet|"
    r"dollars?|cents?|hours?|minutes?|seconds?|days?)\b",
    re.IGNORECASE,
)
# one LaTeX argument: {braced}, a \command, or a single character
_ARG = r"(\{[^{}]*\}|\\[a-zA-Z]+|[^\s{}\\])"


def _unbrace(arg: str) -> str:
    return arg[1:-1] if arg.startswith("{") and arg.endswith("}") else arg


def _strip_latex(s: str) -> str:
    s = s.strip()
    s = s.strip("$")
    # matrices / column vectors -> tuples (before the wrappers, which would
    # eat the "\\ " row separators)
    s = re.sub(
        r"\\begin\{[pb]matrix\}(.*?)\\end\{[pb]matrix\}",
        lambda m: "(" + ",".join(p.strip() for p in m.group(1).split(r"\\")) + ")",
        s,
        flags=re.DOTALL,
    )
    for a, b in _LATEX_WRAPPERS:
        s = s.replace(a, b)
    # keep the content of text-like wrappers, then drop unit words
    s = re.sub(r"\\(?:text|textbf|mbox|mathrm)\s*\{([^{}]*)\}", r"\1", s)
    s = _UNIT_WORDS.sub("", s)
    # "12 and 13" -> "12,13"
    s = re.sub(r"\s+and\s+", ",", s)
    # base subscripts: 0.0011_{2} -> 0.0011
    s = re.sub(r"_\{?\d+\}?\s*$", "", s)
    # \dfrac/\tfrac -> \frac
    s = s.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    # sqrt before frac, so \frac{\sqrt{6}}{6} has no nested braces left
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\sqrt\s*(\w)", r"sqrt(\1)", s)
    # \frac{a}{b}, \frac{a}b, \frac ab, \frac\pi4 -> (a)/(b); repeat for nesting
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r"\\frac\s*" + _ARG + r"\s*" + _ARG,
            lambda m: f"({_unbrace(m.group(1))})/({_unbrace(m.group(2))})",
            s,
        )
    s = s.replace(r"\pi", "pi")  # after \frac, which reads \pi as one argument
    s = s.replace(r"\cdot", "*").replace(r"\times", "*")
    s = s.replace(r"\le", "<=").replace(r"\ge", ">=")
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


_TEXT_RE = re.compile(r"\\(?:text|textbf|mbox|mathrm)\s*\{[^{}]*\}")


def _drop_text(s: str) -> str:
    """Remove text annotations entirely: '45 \\text{ miles}' -> '45 '."""
    return _TEXT_RE.sub("", s)


def _scalar_equal(a: str, b: str) -> bool:
    na = normalize(a)
    return (na == normalize(b) and na != "") or _numeric_equal(a, b) or _symbolic_equal(a, b)


def _split_top_level(s: str) -> list[str]:
    """Split on commas that are not inside (), [] or {}."""
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts]


def _list_equal(a: str, b: str) -> bool:
    """Compare multi-part answers: a parenthesized tuple is ordered, a bare
    comma list (e.g. all solutions of an equation) is unordered."""
    sa, sb = _strip_latex(a).strip(), _strip_latex(b).strip()
    ordered = all(x.startswith("(") and x.endswith(")") for x in (sa, sb))
    if ordered:
        sa, sb = sa[1:-1], sb[1:-1]
    elif any(c in x for x in (sa, sb) for c in "()[]"):
        return False  # intervals and mixed forms are not handled here
    pa, pb = _split_top_level(sa), _split_top_level(sb)
    if len(pa) < 2 or len(pa) != len(pb):
        return False
    if ordered:
        return all(_scalar_equal(x, y) for x, y in zip(pa, pb))
    remaining = list(pb)
    for x in pa:
        match = next((y for y in remaining if _scalar_equal(x, y)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


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
    if _list_equal(extracted, ref):
        return Verdict(True, "list", extracted, normalize(ref))
    # last resort: units or prose wrapped in \text{} on either side
    a, b = _drop_text(extracted), _drop_text(ref)
    if (a, b) != (extracted, ref) and _scalar_equal(a, b):
        return Verdict(True, "no-text", extracted, normalize(ref))
    return Verdict(False, "none", extracted, normalize(ref))
