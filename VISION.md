# TestReportHub Vision

TestReportHub is the data ingestion layer for **TestPulse**, a test-failure intelligence platform.

## Two-Tier Architecture

### Tier 1: TestReportHub (Local CLI)
**Target user:** Individual engineer  
**Scope:** One repo, one run  
**Storage:** Stateless HTML/JSON, optional local SQLite  
**Value:** "Show me this run, unified across frameworks"

Commands:
- `trh collect` — generate unified report
- `trh ingest` — persist to local SQLite with labels
- `trh flaky` — find flaky tests
- `trh compare` — diff two runs
- `trh history` — trend analysis
- `trh quality-gate` — enforce quality thresholds

### Tier 2: TestPulse (Hosted SaaS)
**Target user:** QA leads, engineering managers  
**Scope:** Entire org, all time  
**Storage:** Hosted database  
**Value:** "Show me the health of checkout-service across all environments"

Features (future):
- Multi-tenant web dashboard
- Team-based access control
- Slack/Jira integrations
- ML-based flake prediction
- Failure clustering and root-cause hints
- SLO tracking per app/env

## The Bridge: Labels

The `--label` flag on `trh ingest` is the bridge between tiers. Labels like `org=acme,app=checkout,env=staging` map directly to the hierarchy in TestPulse.

Local CLI users get hierarchical filtering for free. When they're ready for the SaaS, their data model is already compatible.

## Design Principles

1. **Zero-config by default.** `pip install testreporthub` should be the only setup.
2. **Self-contained outputs.** HTML reports have no external dependencies.
3. **Labels over schema.** Don't hardcode org/app/env — use flexible key-value labels.
4. **CLI-first, UI-later.** The SaaS is a UI on top of the same data model.
5. **Fail fast in CI.** Quality gates should block deployments when quality drops.

## Roadmap

### v1.0 (Current)
- [x] Parsers: JUnit, Cypress, Playwright, Newman
- [x] HTML report with search/filter
- [x] JSON/NDJSON output
- [x] CI exit codes
- [x] SQLite backend with labels
- [x] Intelligence: flaky, compare, history, quality-gate
- [x] GitHub Action
- [x] PyPI release

### v1.1 (Next)
- [ ] Streaming parsers for 100MB+ files
- [ ] Attachment bundling (screenshots/videos in report)
- [ ] Secret redaction (`--redact`)
- [ ] HTML trend charts in report
- [ ] More parsers: Jest, Mocha, Robot, Cucumber

### v2.0 (TestPulse Preview)
- [ ] Hosted SaaS launch
- [ ] Web dashboard with hierarchy navigation
- [ ] Slack notifications on quality gate breaches
- [ ] Jira/GitHub issue creation from failures
- [ ] Team-based access control

## What TestReportHub is NOT

- Not a test runner
- Not a test framework
- Not a replacement for Allure/ReportPortal (it complements them)
- Not a SaaS (yet — that's TestPulse)