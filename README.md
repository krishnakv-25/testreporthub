# TestReportHub

**One command. One report. Every framework.**

TestReportHub ingests test execution reports from different frameworks...
(JUnit XML, Cypress, Playwright, Newman/Postman), normalizes them into a
single data model, and emits a self-contained, searchable HTML quality report.

## Install

```bash
pip install testreporthub
```

Or from source:

```bash
git clone https://github.com/your-org/testreporthub.git
cd testreporthub
pip install -e .
```

## Quick start

```bash
# Ingest anything — JUnit XML, Cypress, Playwright, Newman
trh collect ./results/ -o report.html

# Auto-detect formats (default)
trh collect ./cypress/results ./playwright/results ./junit.xml

# Force a specific format
trh collect ./legacy.xml --format junit

# Open the report
open report.html
```

## 🚀 CI/CD Integration

TestReportHub is designed to run in your CI pipeline. It provides machine-readable outputs and strict exit codes.

### Fail the build on failures
```bash
# Exits with code 1 if any test failed or errored
trh collect ./results/ -o report.json --fail-on-failed --fail-on-error
```

## Supported formats

| Format | Source | Flag |
| --- | --- | --- |
| JUnit XML | pytest, Java, Go, Rust, etc. | `--format junit` |
| Cypress JSON | Mocha-based reporter | `--format cypress` |
| Playwright JSON | `--reporter=json` | `--format playwright` |
| Newman JSON | Postman collections | `--format newman` |

## Normalized model

Every test is normalized to:

```
id, name, full_name, suite, framework, status, duration_ms,
started_at, message, trace, error_type, tags, metadata, attachments
```

Statuses: `passed`, `failed`, `skipped`, `error`, `xfailed`.

## Why this matters

Teams usually have test results scattered across UI, API, regression,
and legacy automation. TestReportHub gives you:

* one command to collect results
* one normalized test-result model
* one unified report
* one place to understand failures

It's also the foundation for **TestPulse** — flaky-test detection and
failure intelligence — but the MVP stays small on purpose.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT