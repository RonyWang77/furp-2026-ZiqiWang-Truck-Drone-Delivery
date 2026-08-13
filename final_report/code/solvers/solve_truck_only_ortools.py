"""Placeholder wrapper for future truck-only OR-Tools baseline."""

from __future__ import annotations


def solve(*_, **__) -> dict:
    raise NotImplementedError(
        "truck_only_ortools is intentionally left as a future baseline wrapper. "
        "The existing EVRPTW_Schneider2014 OR-Tools code was not modified."
    )

