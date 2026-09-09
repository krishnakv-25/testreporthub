"""Render a TestRun as a self-contained, searchable HTML report."""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, PackageLoader, select_autoescape

from testreporthub.models import TestResult, TestRun, TestStatus


def _fmt_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    s = ms / 1000.0
    if s < 60:
        return f"{s:.2f}s"
    m, rem = divmod(s, 60)
    return f"{int(m)}m {rem:.1f}s"


def _status_badge_class(status: TestStatus) -> str:
    return {
        TestStatus.PASSED: "badge-passed",
        TestStatus.FAILED: "badge-failed",
        TestStatus.ERROR: "badge-error",
        TestStatus.SKIPPED: "badge-skipped",
        TestStatus.XFAILED: "badge-xfailed",
    }[status]


def _result_to_row(r: TestResult) -> Dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "full_name": r.full_name,
        "suite": r.suite,
        "framework": r.framework,
        "status": r.status.value,
        "status_class": _status_badge_class(r.status),
        "duration_ms": r.duration_ms,
        "duration_human": _fmt_duration(r.duration_ms),
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "message": r.message,
        "trace": r.trace,
        "error_type": r.error_type,
        "tags": r.tags,
    }


def render(run: TestRun, out_path: Path) -> Path:
    env = Environment(
        loader=PackageLoader("testreporthub", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html")

    rows = [_result_to_row(r) for r in run.results]

    ctx = {
        "run_id": run.run_id,
        "generated_at": run.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total": run.total,
        "passed": len(run.passed),
        "failed": len(run.failed),
        "errored": len(run.errored),
        "skipped": len(run.skipped),
        "xfailed": len(run.xfailed),
        "duration_human": _fmt_duration(run.duration_ms),
        "frameworks": run.frameworks,
        "suites": run.suites,
        "rows_json": json.dumps(rows),
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.render(**ctx), encoding="utf-8")
    return out_path