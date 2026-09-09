"""Tests for the SQLite backend and intelligence queries."""

import pytest
from pathlib import Path

from testreporthub.aggregator import collect
from testreporthub.db import (
    compare_runs,
    find_flaky_tests,
    get_run_labels,
    get_run_trends,
    init_db,
    list_runs,
    quality_gate_check,
    save_run,
)
from testreporthub.models import TestResult, TestRun, TestStatus


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures"


def _make_run(run_id: str, results: list) -> TestRun:
    return TestRun(run_id=run_id, results=results)


def _test(name: str, status: TestStatus, framework: str = "junit") -> TestResult:
    return TestResult(
        id=TestResult.make_id(name, framework),
        name=name,
        full_name=name,
        suite="suite",
        framework=framework,
        status=status,
        duration_ms=10.0,
    )


def test_save_run_persists_results(db_path, fixtures):
    run = collect([str(fixtures / "junit.xml")], run_id="run-1")
    save_run(db_path, run)

    runs = list_runs(db_path)
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-1"
    assert runs[0]["total"] == 3


def test_save_run_with_labels(db_path, fixtures):
    run = collect([str(fixtures / "junit.xml")], run_id="run-1")
    save_run(db_path, run, labels={"org": "acme", "app": "checkout", "env": "staging"})

    labels = get_run_labels(db_path, "run-1")
    assert labels == {"org": "acme", "app": "checkout", "env": "staging"}

    runs = list_runs(db_path)
    assert runs[0]["labels"] == {"org": "acme", "app": "checkout", "env": "staging"}


def test_list_runs_filters_by_labels(db_path, fixtures):
    run1 = collect([str(fixtures / "junit.xml")], run_id="run-1")
    run2 = collect([str(fixtures / "junit.xml")], run_id="run-2")
    save_run(db_path, run1, labels={"app": "checkout", "env": "staging"})
    save_run(db_path, run2, labels={"app": "payments", "env": "dev"})

    all_runs = list_runs(db_path)
    assert len(all_runs) == 2

    checkout_runs = list_runs(db_path, labels={"app": "checkout"})
    assert len(checkout_runs) == 1
    assert checkout_runs[0]["run_id"] == "run-1"

    staging_runs = list_runs(db_path, labels={"env": "staging"})
    assert len(staging_runs) == 1

    # Combined filter
    both = list_runs(db_path, labels={"app": "checkout", "env": "staging"})
    assert len(both) == 1

    # Non-matching filter
    none = list_runs(db_path, labels={"app": "nonexistent"})
    assert len(none) == 0


def test_find_flaky_tests(db_path):
    # Run 1: test-a passes, test-b fails
    run1 = _make_run("run-1", [
        _test("test-a", TestStatus.PASSED),
        _test("test-b", TestStatus.FAILED),
        _test("test-c", TestStatus.PASSED),
    ])
    # Run 2: test-a fails (now flaky), test-b passes (now flaky), test-c passes
    run2 = _make_run("run-2", [
        _test("test-a", TestStatus.FAILED),
        _test("test-b", TestStatus.PASSED),
        _test("test-c", TestStatus.PASSED),
    ])
    save_run(db_path, run1)
    save_run(db_path, run2)

    flaky = find_flaky_tests(db_path)
    flaky_names = {t["full_name"] for t in flaky}
    assert flaky_names == {"test-a", "test-b"}
    assert "test-c" not in flaky_names


def test_find_flaky_tests_with_label_filter(db_path):
    run1 = _make_run("run-1", [_test("test-a", TestStatus.PASSED)])
    run2 = _make_run("run-2", [_test("test-a", TestStatus.FAILED)])
    run3 = _make_run("run-3", [_test("test-a", TestStatus.PASSED)])

    save_run(db_path, run1, labels={"env": "dev"})
    save_run(db_path, run2, labels={"env": "staging"})
    save_run(db_path, run3, labels={"env": "dev"})

    # Across all envs: test-a is flaky
    all_flaky = find_flaky_tests(db_path)
    assert len(all_flaky) == 1

    # Scoped to dev only: test-a always passes, not flaky
    dev_flaky = find_flaky_tests(db_path, labels={"env": "dev"})
    assert len(dev_flaky) == 0

    # Scoped to staging only: only one run, can't be flaky
    staging_flaky = find_flaky_tests(db_path, labels={"env": "staging"})
    assert len(staging_flaky) == 0


def test_compare_runs_detects_regressions(db_path):
    run_a = _make_run("run-a", [
        _test("test-1", TestStatus.PASSED),
        _test("test-2", TestStatus.FAILED),
        _test("test-3", TestStatus.PASSED),
    ])
    run_b = _make_run("run-b", [
        _test("test-1", TestStatus.FAILED),   # regression
        _test("test-2", TestStatus.PASSED),   # fix
        _test("test-3", TestStatus.PASSED),   # stable
        _test("test-4", TestStatus.FAILED),   # new failure
    ])
    save_run(db_path, run_a)
    save_run(db_path, run_b)

    result = compare_runs(db_path, "run-a", "run-b")
    assert len(result["regressions"]) == 1
    assert result["regressions"][0]["after"]["full_name"] == "test-1"
    assert len(result["fixes"]) == 1
    assert result["fixes"][0]["after"]["full_name"] == "test-2"
    assert len(result["new_failures"]) == 1
    assert result["new_failures"][0]["full_name"] == "test-4"


def test_get_run_trends(db_path):
    for i in range(5):
        run = _make_run(f"run-{i}", [
            _test(f"test-{i}-a", TestStatus.PASSED),
            _test(f"test-{i}-b", TestStatus.PASSED if i < 3 else TestStatus.FAILED),
        ])
        save_run(db_path, run, labels={"env": "staging" if i % 2 == 0 else "dev"})

    all_trends = get_run_trends(db_path)
    assert len(all_trends) == 5

    staging_trends = get_run_trends(db_path, labels={"env": "staging"})
    assert len(staging_trends) == 3


def test_quality_gate_passes(db_path):
    # Stable run with 100% pass rate
    run = _make_run("run-1", [
        _test("test-a", TestStatus.PASSED),
        _test("test-b", TestStatus.PASSED),
    ])
    save_run(db_path, run)

    result = quality_gate_check(
        db_path,
        min_pass_rate=90.0,
        max_flake_rate=5.0,
        max_regressions=0,
    )
    assert result["passed"] is True


def test_quality_gate_fails_on_pass_rate(db_path):
    run = _make_run("run-1", [
        _test("test-a", TestStatus.PASSED),
        _test("test-b", TestStatus.FAILED),
    ])
    save_run(db_path, run)

    result = quality_gate_check(db_path, min_pass_rate=90.0)
    assert result["passed"] is False
    assert any(c["name"] == "min_pass_rate" and not c["passed"] for c in result["checks"])


def test_quality_gate_fails_on_regressions(db_path):
    run_a = _make_run("run-a", [_test("test-1", TestStatus.PASSED)])
    run_b = _make_run("run-b", [_test("test-1", TestStatus.FAILED)])
    save_run(db_path, run_a)
    save_run(db_path, run_b)

    result = quality_gate_check(db_path, max_regressions=0)
    assert result["passed"] is False
    assert any(c["name"] == "max_regressions" and not c["passed"] for c in result["checks"])


def test_quality_gate_scoped_by_labels(db_path):
    # Staging is healthy
    staging_run = _make_run("staging-1", [_test("test-a", TestStatus.PASSED)])
    save_run(db_path, staging_run, labels={"env": "staging"})

    # Dev is broken
    dev_run = _make_run("dev-1", [_test("test-b", TestStatus.FAILED)])
    save_run(db_path, dev_run, labels={"env": "dev"})

    # Gate on staging passes
    staging_result = quality_gate_check(db_path, labels={"env": "staging"}, min_pass_rate=90.0)
    assert staging_result["passed"] is True

    # Gate on dev fails
    dev_result = quality_gate_check(db_path, labels={"env": "dev"}, min_pass_rate=90.0)
    assert dev_result["passed"] is False