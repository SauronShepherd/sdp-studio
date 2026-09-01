"""Small shared primitives used at application boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from .models import Problem

T = TypeVar("T")


def utc_now() -> datetime:
    """Return an aware UTC timestamp from one central clock boundary."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Result[T]:
    """Explicit success/problem result for non-HTTP core operations."""

    value: T | None = None
    problem: Problem | None = None

    @property
    def ok(self) -> bool:
        return self.problem is None

    @classmethod
    def success(cls, value: T) -> Result[T]:
        return cls(value=value)

    @classmethod
    def failure(cls, problem: Problem) -> Result[T]:
        return cls(problem=problem)
