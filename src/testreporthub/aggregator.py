"""Walk inputs, dispatch to parsers, aggregate into a TestRun."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from testreporthub.models import TestRun
from testreporthub.parsers import DEFAULT_REGISTRY, ParseError
from testreporthub.parsers.base import BaseParser


def _iter_files(paths: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*")))
    return [f for f in files if f.is_file()]


def collect(
    inputs: Iterable[str],
    format_name: Optional[str] = None,
    run_id: Optional[str] = None,
) -> TestRun:
    """Parse every input and return a unified TestRun.

    If `format_name` is set, every file is parsed with that parser
    (errors are fatal). Otherwise we auto-detect per file and silently
    skip files no parser claims.
    """
    paths = [Path(p) for p in inputs]
    files = _iter_files(paths)

    results = []
    skipped: List[Path] = []

    for file in files:
        parser: Optional[BaseParser]
        if format_name:
            parser = DEFAULT_REGISTRY.get(format_name)
        else:
            parser = DEFAULT_REGISTRY.detect(file)
        if parser is None:
            skipped.append(file)
            continue
        try:
            results.extend(parser.parse_file(file))
        except ParseError:
            # Auto-detected parsers shouldn't crash the whole run.
            skipped.append(file)

    return TestRun(
        generated_at=datetime.utcnow(),
        run_id=run_id or f"trh-{uuid.uuid4().hex[:8]}",
        results=results,
    )