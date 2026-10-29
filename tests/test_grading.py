"""Unit tests for answer extraction and grading. No API key needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.harness.grading import extract_answer, normalize, grade


def test_extract_boxed():
    assert extract_answer(r"so the result is \boxed{42}.") == "42"
    assert extract_answer(r"\boxed{\frac{1}{2}}") == r"\frac{1}{2}"


def test_extract_boxed_nested():
    assert extract_answer(r"\boxed{\frac{3}{4} + 1}") == r"\frac{3}{4} + 1"


def test_extract_hashes():
    assert extract_answer("blah\n#### 1,234") == "1234"


def test_extract_cue():
    assert extract_answer("The answer is 7.") == "7"
    assert extract_answer("Final answer: -3") == "-3"


def test_extract_last_number():
    assert extract_answer("steps 2 then 3 then 15") == "15"


def test_normalize_thousands():
    assert normalize("1,234") == "1234"
    assert normalize("$1,000.50") == "1000.50"


def test_grade_exact():
    v = grade(r"\boxed{8}", "8")
    assert v.correct and v.method == "exact"


def test_grade_numeric_fraction():
    v = grade(r"the answer is \boxed{0.5}", "1/2")
    assert v.correct and v.method in ("numeric", "symbolic")


def test_grade_symbolic_pi():
    v = grade(r"\boxed{49\pi}", r"49\pi")
    assert v.correct


def test_grade_symbolic_equivalent_expr():
    v = grade(r"\boxed{2x+2}", "2*(x+1)")
    assert v.correct and v.method == "symbolic"


def test_grade_wrong():
    v = grade(r"\boxed{9}", "8")
    assert not v.correct and v.method == "none"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
