from testreporthub.models import TestResult, TestRun, TestStatus


def test_make_id_is_stable():
    a = TestResult.make_id("suite.case", "junit")
    b = TestResult.make_id("suite.case", "junit")
    c = TestResult.make_id("suite.case", "cypress")
    assert a == b
    assert a != c


def test_run_aggregations():
    run = TestRun(results=[
        TestResult(id="1", name="a", full_name="a", framework="junit", status=TestStatus.PASSED, duration_ms=10),
        TestResult(id="2", name="b", full_name="b", framework="junit", status=TestStatus.FAILED, duration_ms=20),
        TestResult(id="3", name="c", full_name="c", framework="junit", status=TestStatus.SKIPPED, duration_ms=0),
    ])
    assert run.total == 3
    assert len(run.passed) == 1
    assert len(run.failed) == 1
    assert len(run.skipped) == 1
    assert run.duration_ms == 30