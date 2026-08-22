"""Validation helpers for optional time-range rows in the desktop UI."""

from __future__ import annotations

from collections.abc import Sequence

from .i18n import Language, text
from .processor import parse_time


def parse_time_rows(
    rows: Sequence[tuple[str, str]],
    *,
    language: Language = "ko",
) -> list[tuple[int, float, float]]:
    """Return populated rows as ``(row_number, start, end)`` tuples.

    A completely blank row is intentionally ignored. A partially populated row
    is rejected so a missing boundary cannot silently widen the processing range.
    """

    intervals: list[tuple[int, float, float]] = []
    for row_number, (start_value, end_value) in enumerate(rows, start=1):
        start_text = start_value.strip()
        end_text = end_value.strip()
        if not start_text and not end_text:
            continue
        if not start_text or not end_text:
            raise ValueError(text(language, "row_both_or_blank", row=row_number))
        try:
            start = parse_time(start_text, language=language)
            end = parse_time(end_text, language=language)
        except ValueError as error:
            raise ValueError(
                text(language, "row_check", row=row_number, error=error)
            ) from error
        if end <= start:
            raise ValueError(text(language, "row_end_after", row=row_number))
        intervals.append((row_number, start, end))

    if not intervals:
        raise ValueError(text(language, "one_range_required"))
    return intervals
