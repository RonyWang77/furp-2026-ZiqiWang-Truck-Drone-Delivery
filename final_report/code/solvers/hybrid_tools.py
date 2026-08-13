"""Conversion and comparison helpers for GA+ALNS hybrid methods."""

from __future__ import annotations

from typing import Any

try:
    from .alns.state import ALNSState
    from .alns.solve import _materialize_solution
except ImportError:  # pragma: no cover
    from solvers.alns.state import ALNSState
    from solvers.alns.solve import _materialize_solution


def solution_to_alns_state(solution: dict[str, Any], instance: dict[str, Any]) -> ALNSState:
    """Convert a unified solution into ALNS clean-route state.

    ALNS stores truck routes without charging stations. Charging decisions are
    rebuilt when the state is materialized and evaluated.
    """

    depot = int(instance["depot"]["id"])
    customer_ids = _customer_ids(instance)
    station_ids = _station_ids(instance)
    raw_routes = solution.get("truck_routes") or [solution.get("truck_route", [depot, depot])]
    clean_routes = [_clean_truck_route(route, depot, customer_ids, station_ids) for route in raw_routes]
    clean_routes = _dedupe_routes_global(clean_routes, customer_ids)
    clean_routes = [route for route in clean_routes if len(route) >= 2]

    valid_tasks = _valid_drone_tasks(solution.get("drone_tasks", []), clean_routes, customer_ids, station_ids)
    drone_customer_ids = {
        customer_id
        for task in valid_tasks
        for customer_id in task.get("customers", [])
        if customer_id in customer_ids
    }
    clean_routes = [_remove_route_customers(route, drone_customer_ids) for route in clean_routes]

    served = set()
    for route in clean_routes:
        served.update(node_id for node_id in route if node_id in customer_ids)
    served.update(drone_customer_ids)
    unassigned = sorted(customer_ids - served)

    return ALNSState(
        clean_truck_routes=clean_routes or [[depot, depot]],
        drone_tasks=valid_tasks,
        unassigned_customers=unassigned,
        metadata={"construction": "hybrid_from_ga_solution"},
    )


def alns_state_to_solution(state: ALNSState, instance: dict[str, Any], charging_policy: str) -> dict[str, Any]:
    return _materialize_solution(instance, state, charging_policy)


def compare_hybrid_results(
    ga_result: dict[str, Any],
    refined_result: dict[str, Any],
    comparison_mode: str = "lexicographic_research",
) -> dict[str, Any]:
    if hybrid_rank(refined_result, comparison_mode) < hybrid_rank(ga_result, comparison_mode):
        return refined_result
    return ga_result


def select_diverse_top_k(
    candidates: list[dict[str, Any]],
    k: int = 3,
    similarity_threshold: float = 0.75,
    require_type_coverage: bool = False,
) -> list[dict[str, Any]]:
    """Select high-quality candidates while avoiding near-identical routes."""

    if not candidates:
        return []
    if require_type_coverage:
        typed = _select_by_type_coverage(candidates, k, similarity_threshold)
        if typed:
            return typed
    ordered = sorted(candidates, key=lambda item: item.get("ga_rank", 10**9))
    selected: list[dict[str, Any]] = []
    for candidate in ordered:
        if len(selected) >= max(1, int(k)):
            break
        if not selected:
            selected.append(_with_similarity(candidate, 0.0))
            continue
        max_similarity = max(solution_similarity(candidate["solution"], kept["solution"]) for kept in selected)
        if max_similarity <= float(similarity_threshold):
            selected.append(_with_similarity(candidate, max_similarity))
    if len(selected) < max(1, int(k)):
        for candidate in ordered:
            if len(selected) >= max(1, int(k)):
                break
            if any(candidate is kept or candidate.get("ga_rank") == kept.get("ga_rank") for kept in selected):
                continue
            max_similarity = max(solution_similarity(candidate["solution"], kept["solution"]) for kept in selected)
            selected.append(_with_similarity(candidate, max_similarity))
    return selected


def solution_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_edges = _solution_edges(left)
    right_edges = _solution_edges(right)
    if not left_edges and not right_edges:
        return 1.0
    union = left_edges | right_edges
    if not union:
        return 0.0
    return len(left_edges & right_edges) / len(union)


def hybrid_improvement_percentage(ga_result: dict[str, Any], selected_result: dict[str, Any]) -> float:
    ga_cost = _hybrid_scalar(ga_result)
    selected_cost = _hybrid_scalar(selected_result)
    if ga_cost <= 1e-9 or selected_cost >= ga_cost:
        return 0.0
    return 100.0 * (ga_cost - selected_cost) / ga_cost


def hybrid_rank(result: dict[str, Any], comparison_mode: str = "lexicographic_research") -> tuple[float, ...]:
    if comparison_mode == "paper_cost_priority":
        return _paper_cost_rank(result)
    return _hybrid_rank(result)


def paper_cost(result: dict[str, Any]) -> float:
    return (
        float(result.get("total_distance", 0.0))
        + float(result.get("charging_time", 0.0))
        + 0.25 * float(result.get("waiting_time", 0.0))
        + 0.25 * float(result.get("drone_waiting_time", 0.0))
    )


def _hybrid_rank(result: dict[str, Any]) -> tuple[float, float, float, float, float, float, float]:
    violations = result.get("violations", {})
    total_violation = sum(float(value) for value in violations.values())
    return (
        0.0 if result.get("feasible") else 1.0,
        total_violation,
        float(result.get("vehicle_count", 1)),
        float(result.get("completion_time", 0.0)),
        float(result.get("total_distance", 0.0)) + float(result.get("charging_time", 0.0)),
        float(result.get("waiting_time", 0.0)) + float(result.get("drone_waiting_time", 0.0)),
        float(result.get("petal_score", 0.0)),
    )


def _paper_cost_rank(result: dict[str, Any]) -> tuple[float, float, float, float, float, float, float, float]:
    violations = result.get("violations", {})
    total_violation = sum(float(value) for value in violations.values())
    return (
        0.0 if result.get("feasible") else 1.0,
        total_violation,
        float(result.get("vehicle_count", 1)),
        paper_cost(result),
        float(result.get("total_distance", 0.0)),
        float(result.get("completion_time", 0.0)),
        float(result.get("charging_time", 0.0)) + float(result.get("waiting_time", 0.0)) + float(result.get("drone_waiting_time", 0.0)),
        float(result.get("petal_score", 0.0)),
    )


def _hybrid_scalar(result: dict[str, Any]) -> float:
    violations = result.get("violations", {})
    total_violation = sum(float(value) for value in violations.values())
    return (
        1_000_000.0 * total_violation
        + 50_000.0 * float(result.get("vehicle_count", 1))
        + 1_000.0 * float(result.get("completion_time", 0.0))
        + float(result.get("total_distance", 0.0))
        + 5.0 * float(result.get("charging_time", 0.0))
        + 2.0 * float(result.get("waiting_time", 0.0))
        + 0.5 * float(result.get("petal_score", 0.0))
    )


def _with_similarity(candidate: dict[str, Any], similarity: float) -> dict[str, Any]:
    row = dict(candidate)
    row["similarity_to_selected"] = float(similarity)
    return row


def _select_by_type_coverage(
    candidates: list[dict[str, Any]],
    k: int,
    similarity_threshold: float,
) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda item: item.get("ga_rank", 10**9))
    selected: list[dict[str, Any]] = []
    used_types: set[str] = set()
    for candidate in ordered:
        if len(selected) >= max(1, int(k)):
            break
        candidate_type = str(candidate.get("candidate_type") or candidate.get("result", {}).get("metadata", {}).get("hybrid_candidate_type", "balanced"))
        if candidate_type in used_types:
            continue
        if selected:
            max_similarity = max(solution_similarity(candidate["solution"], kept["solution"]) for kept in selected)
            if max_similarity > float(similarity_threshold):
                continue
        else:
            max_similarity = 0.0
        selected.append(_with_similarity(candidate, max_similarity))
        used_types.add(candidate_type)
    if len(selected) >= max(1, int(k)):
        return selected
    for candidate in ordered:
        if len(selected) >= max(1, int(k)):
            break
        if any(candidate.get("ga_rank") == kept.get("ga_rank") for kept in selected):
            continue
        max_similarity = max(solution_similarity(candidate["solution"], kept["solution"]) for kept in selected) if selected else 0.0
        selected.append(_with_similarity(candidate, max_similarity))
    return selected


def _solution_edges(solution: dict[str, Any]) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for route in solution.get("truck_routes") or [solution.get("truck_route", [])]:
        clean_route = [int(node_id) for node_id in route]
        for left, right in zip(clean_route, clean_route[1:]):
            edges.add((int(left), int(right)))
    for task in solution.get("drone_tasks", []):
        route = task.get("drone_route")
        if route is None:
            route = [task.get("launch")] + task.get("customers", [task.get("customer")]) + [task.get("recover")]
        clean_route = [int(node_id) for node_id in route if node_id is not None]
        for left, right in zip(clean_route, clean_route[1:]):
            edges.add((int(left), int(right)))
    return edges


def _clean_truck_route(route: list[int], depot: int, customer_ids: set[int], station_ids: set[int]) -> list[int]:
    clean = []
    for raw_node in route:
        node_id = int(raw_node)
        if node_id == depot or node_id in customer_ids:
            clean.append(node_id)
        elif node_id in station_ids:
            continue
    if not clean or clean[0] != depot:
        clean.insert(0, depot)
    if clean[-1] != depot:
        clean.append(depot)
    return _dedupe_route_customers(clean, depot)


def _dedupe_route_customers(route: list[int], depot: int) -> list[int]:
    seen = set()
    clean = [depot]
    for node_id in route[1:-1]:
        node_id = int(node_id)
        if node_id == depot or node_id in seen:
            continue
        clean.append(node_id)
        seen.add(node_id)
    clean.append(depot)
    return clean


def _dedupe_routes_global(routes: list[list[int]], customer_ids: set[int]) -> list[list[int]]:
    seen = set()
    clean_routes: list[list[int]] = []
    for route in routes:
        if len(route) < 2:
            continue
        cleaned = [route[0]]
        for node_id in route[1:-1]:
            if node_id in customer_ids:
                if node_id in seen:
                    continue
                seen.add(node_id)
            cleaned.append(node_id)
        cleaned.append(route[-1])
        clean_routes.append(cleaned)
    return clean_routes


def _remove_route_customers(route: list[int], remove_ids: set[int]) -> list[int]:
    if not remove_ids:
        return list(route)
    return [route[0]] + [node_id for node_id in route[1:-1] if node_id not in remove_ids] + [route[-1]]


def _valid_drone_tasks(
    tasks: list[dict[str, Any]],
    clean_routes: list[list[int]],
    customer_ids: set[int],
    station_ids: set[int],
) -> list[dict[str, Any]]:
    valid = []
    used_customers: set[int] = set()
    for task in tasks:
        route_index = int(task.get("route_index", 0))
        if route_index < 0 or route_index >= len(clean_routes):
            continue
        route = clean_routes[route_index]
        launch = int(task.get("launch", route[0]))
        recover = int(task.get("recover", route[-1]))
        if launch not in route or recover not in route:
            continue
        if route.index(launch) >= route.index(recover):
            continue
        drone_route = [int(node_id) for node_id in task.get("drone_route", [])]
        if not drone_route:
            raw_customers = task.get("customers", [task.get("customer")])
            drone_route = [launch] + [int(cid) for cid in raw_customers if cid is not None] + [recover]
        if not drone_route or drone_route[0] != launch or drone_route[-1] != recover:
            continue
        allowed_middle = customer_ids | station_ids
        if any(node_id not in allowed_middle for node_id in drone_route[1:-1]):
            continue
        customers: list[int] = []
        cleaned_middle: list[int] = []
        for node_id in drone_route[1:-1]:
            if node_id in station_ids:
                cleaned_middle.append(node_id)
            elif node_id in customer_ids and node_id not in used_customers:
                cleaned_middle.append(node_id)
                customers.append(node_id)
        if not customers:
            continue
        used_customers.update(customers)
        valid.append(
            {
                "route_index": route_index,
                "launch": launch,
                "recover": recover,
                "drone_route": [launch] + cleaned_middle + [recover],
                "customers": customers,
            }
        )
    return valid


def _customer_ids(instance: dict[str, Any]) -> set[int]:
    return {int(customer["id"]) for customer in instance.get("customers", [])}


def _station_ids(instance: dict[str, Any]) -> set[int]:
    return {int(station["id"]) for station in instance.get("stations", [])}
