"""Parser registry + auto-detection."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Type

from testreporthub.parsers.base import BaseParser, ParseError
from testreporthub.parsers.cypress_json import CypressJSONParser
from testreporthub.parsers.junit_xml import JUnitXMLParser
from testreporthub.parsers.newman_json import NewmanJSONParser
from testreporthub.parsers.playwright_json import PlaywrightJSONParser


class ParserRegistry:
    def __init__(self) -> None:
        self._by_name: Dict[str, BaseParser] = {}
        for cls in self._default_parsers():
            self.register(cls())

    @staticmethod
    def _default_parsers() -> List[Type[BaseParser]]:
        return [JUnitXMLParser, CypressJSONParser, PlaywrightJSONParser, NewmanJSONParser]

    def register(self, parser: BaseParser) -> None:
        self._by_name[parser.name] = parser

    def names(self) -> List[str]:
        return sorted(self._by_name)

    def get(self, name: str) -> BaseParser:
        if name not in self._by_name:
            raise ParseError(
                f"Unknown format '{name}'. Known: {', '.join(self.names())}"
            )
        return self._by_name[name]

    def detect(self, path: Path) -> Optional[BaseParser]:
        """Return the first parser that claims this file, or None."""
        if not path.is_file():
            return None
        for parser in self._by_name.values():
            try:
                if parser.can_parse(path):
                    return parser
            except Exception:
                continue
        return None


DEFAULT_REGISTRY = ParserRegistry()