"""Normalized data model.

This is the single source of truth every parser writes to and every
consumer (HTML report, future TestPulse intel) reads from.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    XFAILED = "xfailed"


class Attachment(BaseModel):
    name: str
    kind: str  # "screenshot" | "log" | "video" | "trace" | "other"
    content_type: str = "application/octet-stream"
    # Inline base64 for self-contained HTML, or a relative path.
    data: Optional[str] = None
    path: Optional[str] = None


class TestResult(BaseModel):
    """A single normalized test result."""

    id: str = Field(description="Stable unique id (hash of full_name + framework).")
    name: str
    full_name: str
    suite: str = ""
    framework: str = Field(description="Source framework: junit|cypress|playwright|newman")
    status: TestStatus
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    message: Optional[str] = None
    trace: Optional[str] = None
    error_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[Attachment] = Field(default_factory=list)

    @field_validator("duration_ms")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        return max(0.0, float(v))

    @classmethod
    def make_id(cls, full_name: str, framework: str) -> str:
        h = hashlib.sha1(f"{framework}:{full_name}".encode("utf-8")).hexdigest()[:12]
        return f"trh-{h}"


class TestRun(BaseModel):
    """A collection of results produced by one invocation of `trh collect`."""

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    run_id: str = ""
    results: List[TestResult] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    def by_status(self, status: TestStatus) -> List[TestResult]:
        return [r for r in self.results if r.status == status]

    @property
    def passed(self) -> List[TestResult]:
        return self.by_status(TestStatus.PASSED)

    @property
    def failed(self) -> List[TestResult]:
        return self.by_status(TestStatus.FAILED)

    @property
    def errored(self) -> List[TestResult]:
        return self.by_status(TestStatus.ERROR)

    @property
    def skipped(self) -> List[TestResult]:
        return self.by_status(TestStatus.SKIPPED)

    @property
    def xfailed(self) -> List[TestResult]:
        return self.by_status(TestStatus.XFAILED)

    @property
    def duration_ms(self) -> float:
        return sum(r.duration_ms for r in self.results)

    @property
    def frameworks(self) -> List[str]:
        return sorted({r.framework for r in self.results})

    @property
    def suites(self) -> List[str]:
        return sorted({r.suite for r in self.results if r.suite})