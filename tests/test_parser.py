from testreporthub.models import TestStatus
from testreporthub.parsers import DEFAULT_REGISTRY


def test_junit_parses(fixtures):
    p = DEFAULT_REGISTRY.get("junit")
    results = p.parse_file(fixtures / "junit.xml")
    assert len(results) == 3
    by_name = {r.name: r for r in results}
    assert by_name["valid credentials"].status is TestStatus.PASSED
    assert by_name["invalid password"].status is TestStatus.FAILED
    assert by_name["invalid password"].error_type == "AssertionError"
    assert by_name["sso flow"].status is TestStatus.SKIPPED


def test_cypress_parses(fixtures):
    p = DEFAULT_REGISTRY.get("cypress")
    results = p.parse_file(fixtures / "cypress.json")
    assert len(results) == 2
    by_name = {r.name: r for r in results}
    assert by_name["adds item to cart"].status is TestStatus.PASSED
    assert by_name["completes payment"].status is TestStatus.FAILED
    assert by_name["completes payment"].message.startswith("expected '.total'")


def test_playwright_parses(fixtures):
    p = DEFAULT_REGISTRY.get("playwright")
    results = p.parse_file(fixtures / "playwright.json")
    assert len(results) == 2
    by_name = {r.name: r for r in results}
    assert by_name["GET /health"].status is TestStatus.PASSED
    assert by_name["POST /orders"].status is TestStatus.FAILED


def test_newman_parses(fixtures):
    p = DEFAULT_REGISTRY.get("newman")
    results = p.parse_file(fixtures / "newman.json")
    assert len(results) == 3
    failed = [r for r in results if r.status is TestStatus.FAILED]
    assert len(failed) == 1
    assert failed[0].name == "status code is 201"


def test_autodetect(fixtures):
    for name, file in [
        ("junit", "junit.xml"),
        ("cypress", "cypress.json"),
        ("playwright", "playwright.json"),
        ("newman", "newman.json"),
    ]:
        detected = DEFAULT_REGISTRY.detect(fixtures / file)
        assert detected is not None, f"failed to detect {name}"
        assert detected.name == name