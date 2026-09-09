"""JUnit XML parser.

Handles the de-facto standard emitted by pytest, surefire (Java),
go-junit-report, and many others.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as ET

from testreporthub.models import TestResult, TestStatus
from testreporthub.parsers.base import BaseParser, ParseError


def _text(el: Optional[Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse_status(tc: Element) -> tuple[TestStatus, Optional[str], Optional[str], Optional[str]]:
    """Return (status, error_type, message, trace)."""
    failure = tc.find("failure")
    error = tc.find("error")
    skipped = tc.find("skipped")

    if failure is not None:
        return (
            TestStatus.FAILED,
            (failure.get("type") or "").strip() or None,
            _text(failure) or failure.get("message"),
            _text(failure),
        )
    if error is not None:
        return (
            TestStatus.ERROR,
            (error.get("type") or "").strip() or None,
            _text(error) or error.get("message"),
            _text(error),
        )
    if skipped is not None:
        msg = _text(skipped) or skipped.get("message")
        return TestStatus.SKIPPED, None, msg, None

    return TestStatus.PASSED, None, None, None


def _parse_duration(tc: Element) -> float:
    raw = tc.get("time")
    if raw is None:
        return 0.0
    try:
        return float(raw) * 1000.0  # JUnit uses seconds
    except ValueError:
        return 0.0


def _full_name(tc: Element, suite_name: str) -> str:
    classname = tc.get("classname") or suite_name
    name = tc.get("name") or "<unnamed>"
    return f"{classname}.{name}"


class JUnitXMLParser(BaseParser):
    name = "junit"
    extensions = (".xml",)

    def can_parse(self, path: Path) -> bool:
        if not super().can_parse(path):
            return False
        # Peek to confirm it's JUnit-shaped.
        try:
            tree = ET.parse(str(path))
            root = tree.getroot()
            return root.tag in {"testsuites", "testsuite"} or root.find("testsuite") is not None
        except Exception:
            return False

    def parse_file(self, path: Path) -> List[TestResult]:
        try:
            tree = ET.parse(str(path))
        except Exception as e:
            raise ParseError(f"Invalid XML in {path}: {e}") from e

        root = tree.getroot()
        results: List[TestResult] = []

        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        if not suites and root.tag == "testsuites":
            suites = root.findall("testsuite")

        for suite in suites:
            suite_name = suite.get("name") or path.stem
            for tc in suite.findall("testcase"):
                status, error_type, message, trace = _parse_status(tc)
                full_name = _full_name(tc, suite_name)
                results.append(
                    TestResult(
                        id=TestResult.make_id(full_name, self.name),
                        name=tc.get("name") or "<unnamed>",
                        full_name=full_name,
                        suite=suite_name,
                        framework=self.name,
                        status=status,
                        duration_ms=_parse_duration(tc),
                        message=message,
                        trace=trace,
                        error_type=error_type,
                    )
                )
        return results