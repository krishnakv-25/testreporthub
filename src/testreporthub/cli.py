"""CLI entrypoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from testreporthub import __version__
from testreporthub.aggregator import collect
from testreporthub.db import (
    compare_runs,
    find_flaky_tests,
    get_run_trends,
    list_runs,
    quality_gate_check,
    save_run,
)
from testreporthub.parsers import DEFAULT_REGISTRY
from testreporthub.reporter import render


def _parse_labels(raw: Tuple[str, ...]) -> Dict[str, str]:
    """Parse --label key=value pairs into a dict."""
    labels: Dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise click.BadParameter(f"Label must be key=value, got: {item!r}")
        k, v = item.split("=", 1)
        labels[k.strip()] = v.strip()
    return labels


@click.group()
@click.version_option(__version__, prog_name="testreporthub")
def main() -> None:
    """TestReportHub — one report, every framework."""


# ── collect ──────────────────────────────────────────────────────────────

@main.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", default="report.html", show_default=True,
              type=click.Path(), help="Output file path.")
@click.option("--format", "output_format", default=None,
              type=click.Choice(["html", "json", "ndjson"], case_sensitive=False),
              help="Output format. Defaults to 'html' if .html, else 'json'.")
@click.option("--parser", "parser_format", default=None,
              type=click.Choice(DEFAULT_REGISTRY.names(), case_sensitive=False),
              help="Force a specific input parser.")
@click.option("--run-id", "run_id", default=None, help="Optional run identifier.")
@click.option("--quiet", is_flag=True, help="Suppress summary output.")
@click.option("--fail-on-failed", is_flag=True, help="Exit 1 if any tests failed.")
@click.option("--fail-on-error", is_flag=True, help="Exit 1 if any tests errored.")
def collect_cmd(
    inputs: List[str],
    output_path: str,
    output_format: Optional[str],
    parser_format: Optional[str],
    run_id: Optional[str],
    quiet: bool,
    fail_on_failed: bool,
    fail_on_error: bool,
) -> None:
    """Collect test reports from INPUTS and write a unified report."""
    if not output_format:
        ext = Path(output_path).suffix.lower()
        output_format = "json" if ext == ".json" else "html"

    run = collect(inputs, format_name=parser_format, run_id=run_id)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "html":
        render(run, out_path)
    elif output_format == "json":
        out_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    elif output_format == "ndjson":
        with out_path.open("w", encoding="utf-8") as f:
            for r in run.results:
                f.write(r.model_dump_json() + "\n")

    if not quiet:
        click.echo(f"TestReportHub • run {run.run_id}")
        click.echo(f"  total={run.total}  passed={len(run.passed)}  "
                   f"failed={len(run.failed)}  error={len(run.errored)}  "
                   f"skipped={len(run.skipped)}")
        click.echo(f"  frameworks: {', '.join(run.frameworks) or '—'}")
        click.echo(f"  wrote: {out_path.resolve()}")

    exit_code = 0
    if fail_on_failed and len(run.failed) > 0:
        click.echo("❌ Failing CI: Found failed tests.", err=True)
        exit_code = 1
    elif fail_on_error and len(run.errored) > 0:
        click.echo("❌ Failing CI: Found errored tests.", err=True)
        exit_code = 1

    sys.exit(exit_code)


# ── formats ──────────────────────────────────────────────────────────────

@main.command()
def formats() -> None:
    """List supported input formats."""
    for name in DEFAULT_REGISTRY.names():
        click.echo(f"  {name}")


# ── ingest ───────────────────────────────────────────────────────────────

@main.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--db", "db_path", default="testpulse.db", show_default=True,
              type=click.Path(dir_okay=False), help="Path to the local SQLite database.")
@click.option("--parser", "parser_format", default=None,
              type=click.Choice(DEFAULT_REGISTRY.names(), case_sensitive=False),
              help="Force a specific input parser.")
@click.option("--run-id", "run_id", default=None, help="Optional run identifier.")
@click.option("--label", "raw_labels", multiple=True,
              help="Attach a label (key=value). Repeatable. E.g. --label app=checkout --label env=staging")
def ingest(
    inputs: List[str],
    db_path: str,
    parser_format: Optional[str],
    run_id: Optional[str],
    raw_labels: Tuple[str, ...],
) -> None:
    """Ingest reports and save to the local TestPulse SQLite database."""
    labels = _parse_labels(raw_labels) if raw_labels else None
    run = collect(inputs, format_name=parser_format, run_id=run_id)

    try:
        save_run(Path(db_path), run, labels=labels)
        click.echo(f"✅ Successfully ingested {run.total} results into {db_path}")
        click.echo(f"   Run ID: {run.run_id}")
        if labels:
            lbl_str = ", ".join(f"{k}={v}" for k, v in labels.items())
            click.echo(f"   Labels: {lbl_str}")
    except Exception as e:
        click.echo(f"❌ Database error: {e}", err=True)
        sys.exit(1)


# ── flaky ────────────────────────────────────────────────────────────────

@main.command()
@click.option("--db", "db_path", default="testpulse.db", show_default=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--limit", default=20, show_default=True)
@click.option("--label", "raw_labels", multiple=True,
              help="Filter by label (key=value). Repeatable.")
def flaky(db_path: str, limit: int, raw_labels: Tuple[str, ...]) -> None:
    """Identify flaky tests based on historical runs."""
    path = Path(db_path)
    labels = _parse_labels(raw_labels) if raw_labels else None

    click.echo(f"🔍 Analyzing flaky tests in {db_path}...\n")
    flaky_tests = find_flaky_tests(path, limit=limit, labels=labels)

    if not flaky_tests:
        click.echo("🎉 No flaky tests detected! Your suite is stable.")
        return

    click.echo(f"{'Test Name':<50} | {'Framework':<12} | {'Runs':<6} | {'Pass':<6} | {'Fail':<6} | {'Flake %'}")
    click.echo("-" * 105)

    for t in flaky_tests:
        flake_rate = (t["fail_count"] / t["total_runs"]) * 100
        name = t["full_name"][:47] + "..." if len(t["full_name"]) > 50 else t["full_name"]
        click.echo(
            f"{name:<50} | {t['framework']:<12} | {t['total_runs']:<6} | "
            f"{t['pass_count']:<6} | {t['fail_count']:<6} | {flake_rate:.1f}%"
        )


# ── runs ─────────────────────────────────────────────────────────────────

@main.command()
@click.option("--db", "db_path", default="testpulse.db", show_default=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--limit", default=20, show_default=True)
@click.option("--label", "raw_labels", multiple=True,
              help="Filter by label (key=value). Repeatable.")
def runs(db_path: str, limit: int, raw_labels: Tuple[str, ...]) -> None:
    """List recent run IDs."""
    path = Path(db_path)
    labels = _parse_labels(raw_labels) if raw_labels else None

    for r in list_runs(path, limit=limit, labels=labels):
        ts = r["generated_at"][:19].replace("T", " ")
        lbl_str = ""
        if r.get("labels"):
            lbl_str = "  " + ", ".join(f"{k}={v}" for k, v in r["labels"].items())
        click.echo(
            f"{r['run_id']:<20} {ts}  "
            f"total={r['total']} pass={r['passed']} fail={r['failed']}{lbl_str}"
        )


# ── compare ──────────────────────────────────────────────────────────────

@main.command()
@click.option("--db", "db_path", default="testpulse.db", show_default=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--run-a", required=True, help="Baseline run ID.")
@click.option("--run-b", required=True, help="Current run ID.")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON.")
def compare(db_path: str, run_a: str, run_b: str, as_json: bool) -> None:
    """Compare two runs and surface regressions, fixes, and new failures."""
    path = Path(db_path)
    result = compare_runs(path, run_a, run_b)

    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    click.echo(f"📊 Comparing {run_a} → {run_b}\n")

    def _section(title: str, items: list, color: str) -> None:
        if not items:
            return
        click.echo(click.style(f"\n{title} ({len(items)})", fg=color, bold=True))
        click.echo("-" * 80)
        for item in items:
            if "before" in item:
                test = item["after"]
            else:
                test = item
            click.echo(f"  • {test['full_name']:<60} [{test['framework']}]")

    _section("🔴 REGRESSIONS (passed → failed)", result["regressions"], "red")
    _section("🟡 NEW FAILURES (didn't exist before)", result["new_failures"], "yellow")
    _section("🟢 FIXES (failed → passed)", result["fixes"], "green")
    _section("🔵 NEW PASSES (didn't exist before)", result["new_passes"], "blue")
    _section("⚫ STILL FAILING", result["still_failing"], "white")

    click.echo("\n" + "=" * 80)
    click.echo(
        f"Summary: {len(result['regressions'])} regressions, "
        f"{len(result['fixes'])} fixes, "
        f"{len(result['new_failures'])} new failures, "
        f"{len(result['still_failing'])} still failing"
    )


# ── history ──────────────────────────────────────────────────────────────

@main.command()
@click.option("--db", "db_path", default="testpulse.db", show_default=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--limit", default=20, show_default=True)
@click.option("--label", "raw_labels", multiple=True,
              help="Filter by label (key=value). Repeatable.")
def history(db_path: str, limit: int, raw_labels: Tuple[str, ...]) -> None:
    """Show trends across recent runs."""
    path = Path(db_path)
    labels = _parse_labels(raw_labels) if raw_labels else None
    trends = get_run_trends(path, limit=limit, labels=labels)

    if not trends:
        click.echo("No runs found. Run `trh ingest` first.")
        return

    click.echo(f"📈 Run history (last {len(trends)} runs)\n")
    click.echo(f"{'Run ID':<20} | {'Time':<20} | {'Total':<6} | {'Pass':<6} | {'Fail':<6} | {'Pass %'}")
    click.echo("-" * 90)

    for t in trends:
        ts = t["generated_at"][:19].replace("T", " ")
        click.echo(
            f"{t['run_id']:<20} | {ts:<20} | {t['total']:<6} | "
            f"{t['passed']:<6} | {t['failed']:<6} | {t['pass_rate']:.1f}%"
        )

    totals = [t["total"] for t in trends]
    pass_rates = [t["pass_rate"] for t in trends]
    avg_pass = sum(pass_rates) / len(pass_rates)
    click.echo("\n" + "=" * 90)
    click.echo(
        f"Avg pass rate: {avg_pass:.1f}%  |  "
        f"Runs: {len(trends)}  |  "
        f"Avg tests/run: {sum(totals) / len(totals):.0f}"
    )


# ── quality-gate ─────────────────────────────────────────────────────────

@main.command("quality-gate")
@click.option("--db", "db_path", default="testpulse.db", show_default=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--label", "raw_labels", multiple=True,
              help="Scope the gate to specific labels (key=value). Repeatable.")
@click.option("--min-pass-rate", default=95.0, show_default=True, type=float,
              help="Minimum pass rate (%) for the latest run.")
@click.option("--max-flake-rate", default=5.0, show_default=True, type=float,
              help="Maximum acceptable flaky test rate (%).")
@click.option("--max-regressions", default=0, show_default=True, type=int,
              help="Maximum allowed regressions vs previous run.")
@click.option("--lookback", default=5, show_default=True, type=int,
              help="Number of recent runs to consider.")
@click.option("--fail-on-breach", is_flag=True,
              help="Exit with code 1 if any gate check fails.")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON.")
def quality_gate(
    db_path: str,
    raw_labels: Tuple[str, ...],
    min_pass_rate: float,
    max_flake_rate: float,
    max_regressions: int,
    lookback: int,
    fail_on_breach: bool,
    as_json: bool,
) -> None:
    """Evaluate quality gates for runs matching the given labels."""
    path = Path(db_path)
    labels = _parse_labels(raw_labels) if raw_labels else None

    result = quality_gate_check(
        path,
        labels=labels,
        min_pass_rate=min_pass_rate,
        max_flake_rate=max_flake_rate,
        max_regressions=max_regressions,
        lookback=lookback,
    )

    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        click.echo(result["summary"])

    if fail_on_breach and not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()