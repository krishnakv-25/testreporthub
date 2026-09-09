"""Local SQLite backend for historical tracking and TestPulse intelligence."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from testreporthub.models import TestRun

SCHEMA_VERSION = 2

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    generated_at TIMESTAMP,
    total INTEGER,
    passed INTEGER,
    failed INTEGER,
    errored INTEGER,
    skipped INTEGER
);

CREATE TABLE IF NOT EXISTS results (
    id TEXT,
    run_id TEXT,
    name TEXT,
    full_name TEXT,
    suite TEXT,
    framework TEXT,
    status TEXT,
    duration_ms REAL,
    message TEXT,
    trace TEXT,
    PRIMARY KEY (id, run_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_labels (
    run_id TEXT,
    key    TEXT,
    value  TEXT,
    PRIMARY KEY (run_id, key),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_results_full_name ON results(full_name);
CREATE INDEX IF NOT EXISTS idx_results_status ON results(status);
CREATE INDEX IF NOT EXISTS idx_labels_kv ON run_labels(key, value);
"""


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection with row_factory enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Initialize the database schema if it doesn't exist."""
    with get_connection(db_path) as conn:
        conn.executescript(CREATE_TABLES_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()


def save_run(
    db_path: Path,
    run: TestRun,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Persist a TestRun, its results, and optional labels to the database."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO runs
                   (run_id, generated_at, total, passed, failed, errored, skipped)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.run_id,
                    run.generated_at.isoformat(),
                    run.total,
                    len(run.passed),
                    len(run.failed),
                    len(run.errored),
                    len(run.skipped),
                ),
            )

            results_data = [
                (
                    r.id, run.run_id, r.name, r.full_name, r.suite,
                    r.framework, r.status.value, r.duration_ms,
                    r.message, r.trace,
                )
                for r in run.results
            ]
            conn.executemany(
                """INSERT OR REPLACE INTO results
                   (id, run_id, name, full_name, suite, framework, status,
                    duration_ms, message, trace)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                results_data,
            )

            if labels:
                conn.execute("DELETE FROM run_labels WHERE run_id = ?", (run.run_id,))
                conn.executemany(
                    "INSERT INTO run_labels (run_id, key, value) VALUES (?, ?, ?)",
                    [(run.run_id, k, v) for k, v in labels.items()],
                )

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to save run {run.run_id} to DB: {e}")


def _label_filter_clause(labels: Optional[Dict[str, str]]) -> tuple[str, list]:
    """
    Build a SQL WHERE sub-clause that filters run_ids by labels.
    Returns (sql_fragment, params).
    If no labels, returns ("", []).
    """
    if not labels:
        return "", []

    conditions = []
    params: list = []
    for k, v in labels.items():
        conditions.append(
            "run_id IN (SELECT run_id FROM run_labels WHERE key = ? AND value = ?)"
        )
        params.extend([k, v])

    return " AND " + " AND ".join(conditions), params


def find_flaky_tests(
    db_path: Path,
    limit: int = 20,
    labels: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Identify flaky tests: tests with both PASSED and FAILED across runs."""
    init_db(db_path)
    label_clause, label_params = _label_filter_clause(labels)

    query = f"""
        SELECT
            r.full_name,
            r.framework,
            COUNT(*) as total_runs,
            SUM(CASE WHEN r.status = 'passed' THEN 1 ELSE 0 END) as pass_count,
            SUM(CASE WHEN r.status = 'failed' THEN 1 ELSE 0 END) as fail_count
        FROM results r
        WHERE r.status IN ('passed', 'failed', 'error')
        {label_clause}
        GROUP BY r.full_name
        HAVING pass_count > 0 AND fail_count > 0
        ORDER BY (fail_count * 1.0 / total_runs) DESC
        LIMIT ?
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, label_params + [limit])
        return [dict(row) for row in cursor.fetchall()]


def list_runs(
    db_path: Path,
    limit: int = 20,
    labels: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """List recent runs, newest first, optionally filtered by labels."""
    init_db(db_path)
    label_clause, label_params = _label_filter_clause(labels)

    query = f"""
        SELECT runs.run_id, runs.generated_at, runs.total,
               runs.passed, runs.failed, runs.errored, runs.skipped
        FROM runs
        WHERE 1=1 {label_clause}
        ORDER BY runs.generated_at DESC
        LIMIT ?
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, label_params + [limit])
        rows = [dict(r) for r in cursor.fetchall()]

    # Attach labels to each run for display
    for row in rows:
        with get_connection(db_path) as conn:
            lbls = conn.execute(
                "SELECT key, value FROM run_labels WHERE run_id = ?",
                (row["run_id"],),
            ).fetchall()
            row["labels"] = {lbl["key"]: lbl["value"] for lbl in lbls}

    return rows


def get_run_results(db_path: Path, run_id: str) -> List[Dict[str, Any]]:
    """Get all results for a specific run."""
    init_db(db_path)
    query = """
        SELECT id, name, full_name, suite, framework, status, duration_ms
        FROM results
        WHERE run_id = ?
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, (run_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_run_labels(db_path: Path, run_id: str) -> Dict[str, str]:
    """Get all labels for a specific run."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT key, value FROM run_labels WHERE run_id = ?", (run_id,)
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}


def compare_runs(db_path: Path, run_a: str, run_b: str) -> Dict[str, Any]:
    """Compare two runs: regressions, fixes, new failures, still failing."""
    init_db(db_path)
    results_a = {r["full_name"]: r for r in get_run_results(db_path, run_a)}
    results_b = {r["full_name"]: r for r in get_run_results(db_path, run_b)}

    failed_statuses = {"failed", "error"}
    regressions, fixes, new_failures, new_passes, still_failing = [], [], [], [], []

    all_tests = set(results_a.keys()) | set(results_b.keys())

    for test_name in all_tests:
        a = results_a.get(test_name)
        b = results_b.get(test_name)

        if a is None:
            if b["status"] in failed_statuses:
                new_failures.append(b)
            else:
                new_passes.append(b)
            continue

        if b is None:
            continue

        a_failed = a["status"] in failed_statuses
        b_failed = b["status"] in failed_statuses

        if not a_failed and b_failed:
            regressions.append({"before": a, "after": b})
        elif a_failed and not b_failed:
            fixes.append({"before": a, "after": b})
        elif a_failed and b_failed:
            still_failing.append({"before": a, "after": b})

    return {
        "run_a": run_a,
        "run_b": run_b,
        "regressions": regressions,
        "fixes": fixes,
        "new_failures": new_failures,
        "new_passes": new_passes,
        "still_failing": still_failing,
    }


def get_run_trends(
    db_path: Path,
    limit: int = 20,
    labels: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Return per-run stats for trend charts, optionally filtered by labels."""
    init_db(db_path)
    label_clause, label_params = _label_filter_clause(labels)

    query = f"""
        SELECT run_id, generated_at, total, passed, failed, errored, skipped
        FROM runs
        WHERE 1=1 {label_clause}
        ORDER BY generated_at ASC
        LIMIT ?
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, label_params + [limit])
        rows = [dict(r) for r in cursor.fetchall()]

    trends = []
    for row in rows:
        pass_rate = (row["passed"] / row["total"] * 100) if row["total"] else 0
        trends.append({**row, "pass_rate": pass_rate})
    return trends


def quality_gate_check(
    db_path: Path,
    labels: Optional[Dict[str, str]] = None,
    min_pass_rate: float = 95.0,
    max_flake_rate: float = 5.0,
    max_regressions: int = 0,
    lookback: int = 5,
) -> Dict[str, Any]:
    """
    Evaluate quality gates for runs matching the given labels.

    Returns a dict with:
      - passed: bool (overall gate result)
      - checks: list of individual check results
      - summary: human-readable summary
    """
    init_db(db_path)
    trends = get_run_trends(db_path, limit=lookback, labels=labels)
    checks: List[Dict[str, Any]] = []
    all_passed = True

    if not trends:
        return {
            "passed": False,
            "checks": [{"name": "data", "passed": False, "detail": "No runs found matching labels"}],
            "summary": "❌ No data available for quality gate evaluation.",
        }

    latest = trends[-1]
    label_desc = ", ".join(f"{k}={v}" for k, v in (labels or {}).items()) or "all runs"

    # Check 1: Minimum pass rate
    pass_check = latest["pass_rate"] >= min_pass_rate
    if not pass_check:
        all_passed = False
    checks.append({
        "name": "min_pass_rate",
        "passed": pass_check,
        "threshold": f">= {min_pass_rate}%",
        "actual": f"{latest['pass_rate']:.1f}%",
        "detail": f"Latest pass rate is {latest['pass_rate']:.1f}% (threshold: {min_pass_rate}%)",
    })

    # Check 2: Flake rate
    flaky = find_flaky_tests(db_path, limit=100, labels=labels)
    total_unique_tests = len({t["full_name"] for t in flaky}) + latest["total"] - sum(
        t["total_runs"] for t in flaky
    )
    if total_unique_tests > 0:
        flake_rate = (len(flaky) / total_unique_tests) * 100
    else:
        flake_rate = 0.0

    flake_check = flake_rate <= max_flake_rate
    if not flake_check:
        all_passed = False
    checks.append({
        "name": "max_flake_rate",
        "passed": flake_check,
        "threshold": f"<= {max_flake_rate}%",
        "actual": f"{flake_rate:.1f}%",
        "detail": f"Flake rate is {flake_rate:.1f}% ({len(flaky)} flaky tests, threshold: {max_flake_rate}%)",
    })

    # Check 3: Regressions (compare latest two runs)
    if len(trends) >= 2:
        prev = trends[-2]
        comparison = compare_runs(db_path, prev["run_id"], latest["run_id"])
        regression_count = len(comparison["regressions"])
        reg_check = regression_count <= max_regressions
        if not reg_check:
            all_passed = False
        checks.append({
            "name": "max_regressions",
            "passed": reg_check,
            "threshold": f"<= {max_regressions}",
            "actual": str(regression_count),
            "detail": f"{regression_count} regressions since {prev['run_id']} (threshold: {max_regressions})",
        })

    # Build summary
    status = "✅ PASSED" if all_passed else "❌ FAILED"
    summary_lines = [f"Quality Gate {status} [{label_desc}]", f"  Latest run: {latest['run_id']}"]
    for c in checks:
        icon = "✅" if c["passed"] else "❌"
        summary_lines.append(f"  {icon} {c['name']}: {c['detail']}")

    return {
        "passed": all_passed,
        "checks": checks,
        "summary": "\n".join(summary_lines),
        "latest_run": latest,
        "label_desc": label_desc,
    }