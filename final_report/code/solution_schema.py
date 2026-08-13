"""Shared solution/result structures for Truck-Drone EVRPTW-NL."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SolutionResult:
    instance: str
    method: str
    charging_policy: str
    solution: dict[str, Any]
    feasible: bool
    vehicle_count: int
    truck_distance: float
    drone_distance: float
    total_distance: float
    completion_time: float
    waiting_time: float
    truck_waiting_time: float
    drone_waiting_time: float
    charging_count: int
    charging_time: float
    petal_score: float
    crossing_count: float
    route_compactness: float
    sector_coherence: float
    depot_radial_consistency: float
    runtime_seconds: float
    violations: dict[str, float] = field(default_factory=dict)
    feasibility: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_result(
    instance: dict,
    method: str,
    charging_policy: str,
    solution: dict[str, Any],
    runtime_seconds: float,
    evaluation: dict[str, Any],
    notes: str = "",
) -> SolutionResult:
    metrics = evaluation["metrics"]
    return SolutionResult(
        instance=instance["name"],
        method=method,
        charging_policy=charging_policy,
        solution=solution,
        feasible=bool(evaluation["feasible"]),
        vehicle_count=int(metrics.get("vehicle_count", 1)),
        truck_distance=float(metrics["truck_distance"]),
        drone_distance=float(metrics["drone_distance"]),
        total_distance=float(metrics["total_distance"]),
        completion_time=float(metrics["completion_time"]),
        waiting_time=float(metrics["waiting_time"]),
        truck_waiting_time=float(metrics["truck_waiting_time"]),
        drone_waiting_time=float(metrics["drone_waiting_time"]),
        charging_count=int(metrics["charging_count"]),
        charging_time=float(metrics["charging_time"]),
        petal_score=float(metrics.get("petal_score", 0.0)),
        crossing_count=float(metrics.get("crossing_count", 0.0)),
        route_compactness=float(metrics.get("route_compactness", 0.0)),
        sector_coherence=float(metrics.get("sector_coherence", 0.0)),
        depot_radial_consistency=float(metrics.get("depot_radial_consistency", 0.0)),
        runtime_seconds=float(runtime_seconds),
        violations=dict(evaluation["violations"]),
        feasibility=dict(evaluation.get("feasibility", {})),
        diagnostics=dict(evaluation.get("diagnostics", {})),
        trace=dict(evaluation.get("trace", {})),
        notes=notes,
    )
