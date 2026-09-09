"""Playwright JSON reporter parser.

Playwright's `--reporter=json` emits:
{ stats, suites: [ { title, specs: [ { title, tests: [ { results: [...] } ] } ] } ] }
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from testreporthub.models import Attachment, TestResult, TestStatus
from testreporthub.parsers.base import BaseParser, ParseError


def _map_status(s: str) -> TestStatus:
    s = (s or "").lower()
    if s == "passed":
        return TestStatus.PASSED
    if s == "failed":
        return TestStatus.FAILED
    if s == "skipped":
        return TestStatus.SKIPPED
    if s == "timedOut":
        return TestStatus.ERROR
    if s == "interrupted":
        return TestStatus.ERROR
    if s == "expected":
        return TestStatus.PASSED
    if s == "unexpected":
        return TestStatus.FAILED
    if s == "flaky":
        return TestStatus.PASSED  # eventually passed
    return TestStatus.ERROR


def _walk(node: Dict[str, Any], suite_path: List[str], out: List[Dict[str, Any]]) -> None:
    title = node.get("title") or ""
    current = suite_path + ([title] if title else [])
    for spec in node.get("specs", []) or []:
        spec_title = spec.get("title") or ""
        for test in spec.get("tests", []) or []:
            out.append({"suite_path": current, "spec_title": spec_title, "test": test})
    for child in node.get("suites", []) or []:
        _walk(child, current, out)


class PlaywrightJSONParser(BaseParser):
    name = "playwright"
    extensions = (".json",)

    def can_parse(self, path: Path) -> bool:
        if not super().can_parse(path):
            return False
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                isinstance(data, dict)
                and "stats" in data
                and "suites" in data
                and isinstance(data["suites"], list)
            )
        except Exception:
            return False

    def parse_file(self, path: Path) -> List[TestResult]:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ParseError(f"Invalid JSON in {path}: {e}") from e

        results: List[TestResult] = []
        flat: List[Dict[str, Any]] = []
        for root_suite in data.get("suites", []) or []:
            _walk(root_suite, [], flat)

        for item in flat:
            test = item["test"]
            suite_name = " > ".join(item["suite_path"]) or path.stem
            spec_title = item["spec_title"]
            # Playwright stores the "final" status on the test; each result is a retry.
            final_status = _map_status(test.get("status") or "")
            # Pick the last result for trace/message.
            test_results = test.get("results") or [{}]
            last = test_results[-1] if test_results else {}

            full_name = " > ".join(
                [p for p in item["suite_path"] + [spec_title] if p]
            ) or "<unnamed>"

            error = last.get("error") or {}
            message = error.get("message")
            trace = error.get("stack")

            attachments: List[Attachment] = []
            for a in last.get("attachments") or []:
                attachments.append(
                    Attachment(
                        name=a.get("name") or "attachment",
                        kind=a.get("contentType", "other").split("/")[0]
                        if a.get("contentType")
                        else "other",
                        content_type=a.get("contentType") or "application/octet-stream",
                        path=a.get("path"),
                    )
                )

            started_raw = last.get("startTime")
            started_at = None
            if isinstance(started_raw, str):
                try:
                    started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                except ValueError:
                    started_at = None

            duration_ms = 0.0
            start = last.get("startTime")
            # Playwright provides duration directly in some versions; fall back.
            if "duration" in last:
                try:
                    duration_ms = float(last["duration"])
                except (TypeError, ValueError):
                    duration_ms = 0.0

            results.append(
                TestResult(
                    id=TestResult.make_id(full_name, self.name),
                    name=spec_title or full_name.split(" > ")[-1],
                    full_name=full_name,
                    suite=suite_name,
                    framework=self.name,
                    status=final_status,
                    duration_ms=duration_ms,
                    started_at=started_at,
                    message=message,
                    trace=trace,
                    attachments=attachments,
                    metadata={"retries": len(test_results) - 1},
                )
            )
        return results