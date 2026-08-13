"""Placeholder wrapper for future truck-only PyVRP baseline."""

from __future__ import annotations


def solve(*_, **__) -> dict:
    raise NotImplementedError(
        "truck_only_pyvrp is intentionally left as a future baseline wrapper. "
        "The existing EVRPTW_Schneider2014 PyVRP code was not modified."
    )

