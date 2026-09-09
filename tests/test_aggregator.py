from testreporthub.aggregator import collect


def test_collect_directory(fixtures):
    run = collect([str(fixtures)])
    assert run.total == 10  # 3 junit + 2 cypress + 2 playwright + 3 newman
    assert set(run.frameworks) == {"junit", "cypress", "playwright", "newman"}
    assert len(run.failed) == 3
    assert len(run.passed) == 4


def test_collect_forced_format(fixtures):
    run = collect([str(fixtures / "junit.xml")], format_name="junit")
    assert run.total == 3
    assert run.frameworks == ["junit"]