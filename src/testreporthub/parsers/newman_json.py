"""Newman (Postman) JSON reporter parser.

`newman run -r json` produces:
{ run: { stats: { tests: {...} }, executions: [ { item: {...}, assertions: [...] } ] } }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from testreporthub.models import TestResult, TestStatus
from testreporthub.parsers.base import BaseParser, ParseError


class NewmanJSONParser(BaseParser):
    name = "newman"
    extensions = (".json",)

    def can_parse(self, path: Path) -> bool:
        if not super().can_parse(path):
            return False
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                isinstance(data, dict)
                and isinstance(data.get("run"), dict)
                and "executions" in data["run"]
            )
        except Exception:
            return False

    def parse_file(self, path: Path) -> List[TestResult]:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ParseError(f"Invalid JSON in {path}: {e}") from e

        run = data["run"]
        collection_name = (run.get("collection") or {}).get("name") or path.stem

        results: List[TestResult] = []
        for execution in run.get("executions", []) or []:
            item = execution.get("item") or {}
            item_name = item.get("name") or "<request>"
            # Build suite from the item's ancestry if present.
            ancestry = item.get("ancestors") or []
            suite_path = [a.get("name") for a in ancestry if a.get("name")]
            suite_name = " > ".join([collection_name] + suite_path) or collection_name

            assertions = execution.get("assertions") or []
            if not assertions:
                # Treat the whole request as a single passed test.
                full_name = f"{suite_name} > {item_name}"
                results.append(
                    TestResult(
                        id=TestResult.make_id(full_name, self.name),
                        name=item_name,
                        full_name=full_name,
                        suite=suite_name,
                        framework=self.name,
                        status=TestStatus.PASSED,
                        duration_ms=0.0,
                    )
                )
                continue

            for assertion in assertions:
                assertion_name = assertion.get("assertion") or "<assertion>"
                full_name = f"{suite_name} > {item_name} > {assertion_name}"
                err = assertion.get("error")
                status = TestStatus.PASSED if err is None else TestStatus.FAILED
                message = None
                trace = None
                error_type = None
                if err:
                    message = err.get("message")
                    trace = err.get("stack") or err.get("test")
                    error_type = err.get("name")

                results.append(
                    TestResult(
                        id=TestResult.make_id(full_name, self.name),
                        name=assertion_name,
                        full_name=full_name,
                        suite=suite_name,
                        framework=self.name,
                        status=status,
                        duration_ms=0.0,
                        message=message,
                        trace=trace,
                        error_type=error_type,
                        metadata={"request": item_name},
                    )
                )
        return results