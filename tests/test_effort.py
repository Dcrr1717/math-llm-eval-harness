"""Unit tests for the shared effort level: cache keys, resume, report filter.
No API key needed."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.harness import report, runner
from src.harness.models import load_model_specs, row_effort

SPECS = load_model_specs()


def _row(model, effort=None, uid="own/0001", correct=True):
    r = {"uid": uid, "dataset": "own", "topic": "algebra", "model_alias": model,
         "correct": correct, "grade_method": "exact", "cost_usd": 0.01,
         "latency_s": 1.0, "output_tokens": 10}
    if effort:
        r["effort"] = effort
    return r


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_row_effort_explicit_wins():
    assert row_effort(_row("sonnet", "low"), SPECS) == "low"


def test_row_effort_legacy_rows_use_model_default():
    # rows recorded before effort was sent ran at the API default
    assert row_effort(_row("opus"), SPECS) == "medium"
    assert row_effort(_row("haiku"), SPECS) == "medium"
    assert row_effort(_row("sonnet"), SPECS) == "high"


def test_row_effort_unknown_model():
    assert row_effort(_row("retired-model"), SPECS) is None


def test_cache_key_extended_only_for_effort():
    base = runner._cache_key("claude-opus-5-5", "p", False)
    assert runner._cache_key("claude-opus-5-5", "p", False, None, 0, None) == base
    assert runner._cache_key("claude-opus-5-5", "p", False, None, 0, "high") != base


def test_resume_reuses_only_matching_effort():
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "own.jsonl"
        _write(raw, [_row("opus"), _row("sonnet"), _row("haiku", "low")])
        done = runner._already_done(raw, SPECS)
    assert ("own/0001", "opus", 0, "medium") in done      # legacy opus = medium
    assert ("own/0001", "sonnet", 0, "medium") not in done  # legacy sonnet = high
    assert ("own/0001", "sonnet", 0, "high") in done
    assert ("own/0001", "haiku", 0, "low") in done


def test_report_filters_to_one_effort():
    with tempfile.TemporaryDirectory() as d:
        old_raw, old_summary = report.RAW_DIR, report.SUMMARY
        report.RAW_DIR, report.SUMMARY = Path(d), Path(d) / "summary.json"
        try:
            _write(Path(d) / "own.jsonl", [
                _row("opus"), _row("haiku"), _row("sonnet"),
                _row("sonnet", "medium", correct=False),
            ])
            s = report.build_summary(effort="medium")
            mixed = report.build_summary(effort="any")
        finally:
            report.RAW_DIR, report.SUMMARY = old_raw, old_summary
    assert s["effort"] == "medium"
    assert sorted(s["models"]) == ["haiku", "opus", "sonnet"]
    assert s["models"]["sonnet"]["count"] == 1 and s["models"]["sonnet"]["accuracy"] == 0.0
    assert s["excluded_other_effort"] == {"sonnet@high": 1}
    assert mixed["models"]["sonnet"]["count"] == 2 and mixed["excluded_other_effort"] == {}


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
