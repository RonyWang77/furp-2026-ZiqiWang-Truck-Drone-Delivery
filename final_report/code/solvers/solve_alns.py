"""ALNS entry point.

The real implementation lives in ``solvers.alns``. This wrapper keeps the
existing public import path stable for run_single/run_experiments.
"""

from __future__ import annotations

from typing import Any

try:
    from .alns import solve as _solve_independent_alns
    from .alns.solve import refine_state
except ImportError:  # pragma: no cover
    from solvers.alns import solve as _solve_independent_alns
    from solvers.alns.solve import refine_state


def solve(instance: dict, charging_policy: str = "NPC", seed: int | None = None, **_: Any) -> dict:
    return _solve_independent_alns(instance, charging_policy=charging_policy, seed=seed, **_)
