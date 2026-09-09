"""Cypress JSON reporter parser.

Cypress emits one JSON file per spec with a Mocha-shaped structure:
{ stats, results: [ { suites: [ { tests: [...] } ] } ] }
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from testreporthub.models import Attachment, TestResult, TestStatus
from testreporthub.parsers.base import BaseParser, ParseError


def _map_state(state: str) -> TestStatus:
    s = (state or "").lower()
    if s == "passed":
        return TestStatus.PASSED
    if s == "failed":
        return TestStatus.FAILED
    if s in ("pending", "skipped"):
        return TestStatus.SKIPPED
    return TestStatus.ERROR


def _walk_suites(node: Dict[str, Any], suite_path: List[str], out: List[Dict[str, Any]]) -> None:
    title = node.get("title") or ""
    current = suite_path + ([title] if title else [])
    for t in node.get("tests", []) or []:
        out.append({"suite": " > ".join(current), "test": t})
    for child in node.get("suites", []) or []:
        _walk_suites(child, current, out)


class CypressJSONParser(BaseParser):
    name = "cypress"
    extensions = (".json",)

    def can_parse(self, path: Path) -> bool:
        if not super().can_parse(path):
            return False
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return isinstance(data, dict) and "stats" in data and "results" in data
        except Exception:
            return False

    def parse_file(self, path: Path) -> List[TestResult]:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ParseError(f"Invalid JSON in {path}: {e}") from e

        results: List[TestResult] = []
        for spec in data.get("results", []) or []:
            spec_file = spec.get("file") or path.stem
            for group in spec.get("suites", []) or []:
                flat: List[Dict[str, Any]] = []
                _walk_suites(group, [], flat)
                for item in flat:
                    t = item["test"]
                    test_state = t.get("state") or (t.get("displayError") and "failed") or "passed"
                    # Cypress nests state in `test.state` or inside `test.body`.
                    full_title = " > ".join(
                        [spec_file, item["suite"]] + [t.get("title")]
                    )
                    err = t.get("err") or {}
                    message = err.get("message")
                    trace = err.get("stack")
                    error_type = err.get("name")

                    results.append(
                        TestResult(
                            id=TestResult.make_id(full_title, self.name),
                            name=t.get("title") or "<unnamed>",
                            full_name=full_title,
                            suite=item["suite"] or spec_file,
                            framework=self.name,
                            status=_map_state(test_state),
                            duration_ms=float(t.get("duration") or 0.0),
                            message=message,
                            trace=trace,
                            error_type=error_type,
                            metadata={"spec": spec_file},
                        )
                    )
        return results