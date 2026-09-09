from pathlib import Path
from testreporthub.aggregator import collect
from testreporthub.reporter import render


def test_render_produces_html(fixtures, tmp_path):
    run = collect([str(fixtures)])
    out = tmp_path / "report.html"
    render(run, out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "TestReportHub" in text
    assert "invalid password" in text
    assert "completes payment" in text
    assert "POST /orders" in text
    assert "status code is 201" in text
    # Self-contained: no external script/css links.
    assert '<link rel="stylesheet"' not in text
    assert '<script src=' not in text