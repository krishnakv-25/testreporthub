"""Abstract base for all parsers."""

from __future__ import annotations

from pathlib import Path
from typing import List

from testreporthub.models import TestResult


class ParseError(Exception):
    """Raised when a parser cannot handle a file."""


class BaseParser:
    """Strategy interface. Subclasses implement `parse_file`."""

    name: str = "base"
    extensions: tuple = ()  # e.g. (".xml",)

    def can_parse(self, path: Path) -> bool:
        if self.extensions and path.suffix.lower() in self.extensions:
            return True
        return False

    def parse_file(self, path: Path) -> List[TestResult]:
        raise NotImplementedError