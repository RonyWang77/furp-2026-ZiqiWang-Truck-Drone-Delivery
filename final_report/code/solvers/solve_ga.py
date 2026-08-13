"""First-stage GA-style Truck-Drone solver.

This is a lightweight method scaffold: it uses a shuffled customer order as the
GA-style global sequence, then explicitly assigns some eligible customers to
drone tasks and charging decisions. It does not modify any old GA repository.
"""

from __future__ import annotations

import random
import time
from typing import Any

try:
    from ..evaluator import evaluate_solution
    from ..solution_schema import make_result
    from ..spatial_metrics import cluster_bias, cluster_customer_order, sweep_customer_order
    from .common import randomized_customer_ids, solution_cost_tuple, sorted_customer_ids
    from .ga_tools import (
        candidate_individuals,
        crossover_individual,
        default_max_vehicle_count,
        decode_ga_individual,
        default_ga_orders,
        mutate_individual,
        mutated_orders,
    )
except ImportError:  # pragma: no cover
    from evaluator import evaluate_solution
    from solution_schema import make_result
    from spatial_metrics import cluster_bias, cluster_customer_order, sweep_customer_order
    from solvers.common import randomized_customer_ids, solution_cost_tuple, sorted_customer_ids
    from solvers.ga_tools import (
        candidate_individuals,
        crossover_individual,
        default_max_vehicle_count,
        decode_ga_individual,
        default_ga_orders,
        mutate_individual,
        mutated_orders,
    )


def solve(instance: dict, charging_policy: str = "NPC", seed: int | None = None, **kwargs: Any) -> dict:
    start = time.perf_counter()
    seed = int(seed if seed is not None else instance.get("seed", 1987))
    time_budget = float(kwargs.get("time_budget_seconds") or _default_time_budget_seconds(instance))
    evaluated = generate_ga_candidates_for_hybrid(
        instance,
        charging_policy=charging_policy,
        seed=seed,
        time_budget_seconds=time_budget,
    )
    best_result = evaluated[0]["result"]
    best_result["runtime_seconds"] = time.perf_counter() - start
    return best_result


def generate_ga_candidates_for_hybrid(
    instance: dict,
    charging_policy: str = "NPC",
    seed: int | None = None,
    time_budget_seconds: float | None = None,
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """Evaluate GA candidates and return a ranked pool for hybrid refinement.

    The normal GA solver still returns only its best result. This helper is
    intentionally separate so Hybrid can inspect several evaluated candidates.
    """

    start = time.perf_counter()
    seed = int(seed if seed is not None else instance.get("seed", 1987))
    time_budget = float(time_budget_seconds or _default_time_budget_seconds(instance))
    base_candidates = default_ga_orders(instance, [randomized_customer_ids(instance, seed), randomized_customer_ids(instance, seed + 1)])
    order_candidates = mutated_orders(base_candidates, seed + 100, max_orders=8)
    candidates = candidate_individuals(instance, order_candidates, charging_policy, seed)
    evaluated: list[dict[str, Any]] = []
    evaluated_candidates = 0
    for individual in candidates:
        if evaluated and time.perf_counter() - start >= time_budget:
            break
        solution = decode_ga_individual(instance, individual)
        evaluation = evaluate_solution(instance, solution, charging_policy)
        evaluated_candidates += 1
        result = make_result(
            instance,
            "ga_td",
            charging_policy,
            solution,
            time.perf_counter() - start,
            evaluation,
            notes="GA aware decoder with runtime pruning, cache, specialized mutation, route rebalance, and route-preserving crossover.",
        ).to_dict()
        result["metadata"] = dict(result.get("metadata", {}))
        result["metadata"]["ga_time_budget_seconds"] = time_budget
        result["metadata"]["ga_candidates_total"] = len(candidates)
        result["metadata"]["ga_candidates_evaluated"] = evaluated_candidates
        evaluated.append(
            {
                "individual": individual,
                "result": result,
                "solution": solution,
                "cost_tuple": solution_cost_tuple(result),
                "runtime_seconds": result["runtime_seconds"],
            }
        )
        if max_candidates is not None and evaluated_candidates >= max(1, int(max_candidates)):
            break
    assert evaluated
    evaluated.sort(key=lambda item: item["cost_tuple"])
    for rank, item in enumerate(evaluated, start=1):
        item["ga_rank"] = rank
        item["result"]["metadata"]["ga_candidate_rank"] = rank
    if max_candidates is not None:
        return evaluated[: max(1, int(max_candidates))]
    return evaluated


DIVERSE_CANDIDATE_TYPES = [
    "balanced",
    "distance_oriented",
    "vehicle_oriented",
    "time_window_oriented",
    "drone_aggressive",
    "drone_conservative",
    "charging_oriented",
    "petal_oriented",
]


def generate_diverse_ga_candidates_for_hybrid(
    instance: dict,
    charging_policy: str = "NPC",
    seed: int | None = None,
    time_budget_seconds: float | None = None,
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """Generate explicitly different GA candidates for final Hybrid runs.

    This is a Hybrid-only helper. The normal GA baseline still calls
    ``generate_ga_candidates_for_hybrid()`` and returns its best result.
    """

    start = time.perf_counter()
    seed = int(seed if seed is not None else instance.get("seed", 1987))
    time_budget = float(time_budget_seconds or _default_time_budget_seconds(instance))
    target_count = max(1, int(max_candidates or 32))
    base_budget = max(1.0, time_budget * 0.35)
    base_candidates = generate_ga_candidates_for_hybrid(
        instance,
        charging_policy=charging_policy,
        seed=seed,
        time_budget_seconds=base_budget,
        max_candidates=max(4, min(8, target_count // 3 if target_count >= 12 else target_count)),
    )
    evaluated: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for candidate in base_candidates:
        row = _tag_candidate(candidate, "balanced")
        key = _individual_key(row["individual"]) if row.get("individual") else _solution_key(row["solution"])
        if key not in seen:
            seen.add(key)
            evaluated.append(row)

    sources = [candidate["individual"] for candidate in base_candidates if candidate.get("individual")]
    if not sources:
        return _rank_diverse_candidates(evaluated)

    typed_sources = _seed_type_individuals(instance, sources, charging_policy, seed)
    for candidate_type, individual in typed_sources:
        if len(evaluated) >= target_count:
            break
        if evaluated and time.perf_counter() - start >= time_budget:
            break
        key = _individual_key(individual)
        if key in seen:
            continue
        seen.add(key)
        result = _evaluate_hybrid_individual(
            instance,
            individual,
            charging_policy,
            candidate_type,
            time.perf_counter() - start,
            time_budget,
        )
        evaluated.append(
            {
                "individual": individual,
                "result": result,
                "solution": result["solution"],
                "cost_tuple": solution_cost_tuple(result),
                "runtime_seconds": result["runtime_seconds"],
                "candidate_type": candidate_type,
            }
        )
    return _rank_diverse_candidates(evaluated)[:target_count]


def expand_ga_candidates_for_hybrid(
    instance: dict,
    base_candidates: list[dict[str, Any]],
    charging_policy: str = "NPC",
    seed: int | None = None,
    max_new_candidates: int = 6,
) -> list[dict[str, Any]]:
    """Create extra Hybrid candidates from existing GA-style individuals.

    This helper is intentionally separate from ``solve()`` so the GA baseline
    remains unchanged. It gives Hybrid a small candidate-pool evolution step
    without rewriting the current GA scaffold into a full generation loop.
    """

    start = time.perf_counter()
    seed = int(seed if seed is not None else instance.get("seed", 1987))
    generated: list[dict[str, Any]] = []
    individuals: list[dict[str, Any]] = []
    source_individuals = [candidate.get("individual") for candidate in base_candidates if candidate.get("individual")]
    for idx, individual in enumerate(source_individuals[: max(1, max_new_candidates)]):
        individuals.append(mutate_individual(instance, individual, seed + 1000 + idx))
    for idx in range(min(len(source_individuals) - 1, max_new_candidates)):
        individuals.append(crossover_individual(instance, source_individuals[idx], source_individuals[idx + 1], seed + 2000 + idx))
    seen = {
        _individual_key(candidate["individual"])
        for candidate in base_candidates
        if candidate.get("individual")
    }
    for individual in individuals:
        if len(generated) >= max(1, int(max_new_candidates)):
            break
        key = _individual_key(individual)
        if key in seen:
            continue
        seen.add(key)
        solution = decode_ga_individual(instance, individual)
        evaluation = evaluate_solution(instance, solution, charging_policy)
        result = make_result(
            instance,
            "ga_td",
            charging_policy,
            solution,
            time.perf_counter() - start,
            evaluation,
            notes="GA hybrid candidate expansion by mutation/crossover; baseline GA solve() unchanged.",
        ).to_dict()
        generated.append(
            {
                "individual": individual,
                "result": result,
                "solution": solution,
                "cost_tuple": solution_cost_tuple(result),
                "runtime_seconds": result["runtime_seconds"],
            }
        )
    generated.sort(key=lambda item: item["cost_tuple"])
    return generated


def _seed_type_individuals(
    instance: dict,
    sources: list[dict[str, Any]],
    charging_policy: str,
    seed: int,
) -> list[tuple[str, dict[str, Any]]]:
    typed: list[tuple[str, dict[str, Any]]] = []
    base_orders = {
        "distance_oriented": sorted_customer_ids(instance),
        "vehicle_oriented": cluster_customer_order(instance, then_time_window=True),
        "time_window_oriented": [
            int(customer["id"])
            for customer in sorted(
                instance.get("customers", []),
                key=lambda item: (float(item.get("due_time", 0.0)), float(item.get("ready_time", 0.0)), int(item["id"])),
            )
        ],
        "petal_oriented": sweep_customer_order(instance),
    }
    max_vehicle_count = default_max_vehicle_count(instance)
    for idx, candidate_type in enumerate(DIVERSE_CANDIDATE_TYPES):
        source = sources[idx % len(sources)]
        individual = _specialize_individual(instance, source, candidate_type, seed + idx * 97)
        if candidate_type in base_orders and base_orders[candidate_type]:
            individual["customer_order"] = list(base_orders[candidate_type])
        if candidate_type == "vehicle_oriented":
            individual["max_vehicle_count"] = max(1, min(max_vehicle_count, max(2, (len(instance.get("customers", [])) + 4) // 5)))
            individual["route_split_bias"] = cluster_bias(instance, max(1, int(individual["max_vehicle_count"])))
        typed.append((candidate_type, individual))

        mutated = mutate_individual(instance, individual, seed + idx * 97 + 1)
        typed.append((candidate_type, mutated))
    return typed


def _specialize_individual(instance: dict, source: dict[str, Any], candidate_type: str, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    individual = {
        "customer_order": list(source["customer_order"]),
        "service_mode": dict(source["service_mode"]),
        "drone_priority": dict(source.get("drone_priority", {})),
        "charging_policy": source.get("charging_policy", "NPC"),
        "max_vehicle_count": int(source.get("max_vehicle_count", default_max_vehicle_count(instance))),
        "route_split_bias": dict(source.get("route_split_bias", {})),
        "drone_charging_preference": source.get("drone_charging_preference", "allow"),
    }
    customers = list(instance.get("customers", []))
    eligible = [int(customer["id"]) for customer in customers if bool(customer.get("drone_eligible", False))]
    if candidate_type == "distance_oriented":
        individual["service_mode"] = {int(customer["id"]): "truck" for customer in customers}
        individual["drone_charging_preference"] = "avoid"
    elif candidate_type == "vehicle_oriented":
        individual["max_vehicle_count"] = max(1, int(individual["max_vehicle_count"]) - 1)
        individual["service_mode"] = {int(customer["id"]): "drone" if int(customer["id"]) in eligible[: max(1, len(eligible) // 3)] else "truck" for customer in customers}
    elif candidate_type == "time_window_oriented":
        individual["service_mode"] = {
            int(customer["id"]): "truck" if float(customer.get("due_time", 0.0)) - float(customer.get("ready_time", 0.0)) < 20.0 else individual["service_mode"].get(int(customer["id"]), "truck")
            for customer in customers
        }
    elif candidate_type == "drone_aggressive":
        for customer in customers:
            cid = int(customer["id"])
            if cid in eligible and rng.random() < 0.75:
                individual["service_mode"][cid] = "drone"
                individual["drone_priority"][cid] = 1.0 - 0.01 * rng.random()
        individual["drone_charging_preference"] = "prefer_if_needed"
    elif candidate_type == "drone_conservative":
        for customer in customers:
            cid = int(customer["id"])
            individual["service_mode"][cid] = "truck"
            if cid in eligible and _loose_drone_candidate(customer):
                individual["service_mode"][cid] = "drone"
                individual["drone_priority"][cid] = 0.8
        individual["drone_charging_preference"] = "avoid"
    elif candidate_type == "charging_oriented":
        individual["drone_charging_preference"] = "prefer_if_needed"
        individual["charging_policy"] = source.get("charging_policy", "NPC")
        for cid in eligible:
            individual["drone_priority"][cid] = max(float(individual["drone_priority"].get(cid, 0.0)), 0.6)
    elif candidate_type == "petal_oriented":
        individual["route_split_bias"] = cluster_bias(instance, max(1, int(individual["max_vehicle_count"])))
        for cid in eligible:
            individual["drone_priority"][cid] = max(float(individual["drone_priority"].get(cid, 0.0)), 0.55)
    return individual


def _loose_drone_candidate(customer: dict[str, Any]) -> bool:
    ready = float(customer.get("ready_time", 0.0))
    due = float(customer.get("due_time", 0.0))
    return due - ready >= 30.0 and float(customer.get("demand", 0.0)) <= 30.0


def _evaluate_hybrid_individual(
    instance: dict,
    individual: dict[str, Any],
    charging_policy: str,
    candidate_type: str,
    runtime_seconds: float,
    time_budget: float,
) -> dict[str, Any]:
    solution = decode_ga_individual(instance, individual)
    evaluation = evaluate_solution(instance, solution, charging_policy)
    result = make_result(
        instance,
        "ga_td",
        charging_policy,
        solution,
        runtime_seconds,
        evaluation,
        notes=f"Hybrid diverse GA candidate: {candidate_type}.",
    ).to_dict()
    result["metadata"] = dict(result.get("metadata", {}))
    result["metadata"]["ga_time_budget_seconds"] = time_budget
    result["metadata"]["hybrid_candidate_type"] = candidate_type
    return result


def _tag_candidate(candidate: dict[str, Any], candidate_type: str) -> dict[str, Any]:
    tagged = dict(candidate)
    tagged["candidate_type"] = candidate_type
    tagged["result"] = dict(candidate["result"])
    tagged["result"]["metadata"] = dict(tagged["result"].get("metadata", {}))
    tagged["result"]["metadata"]["hybrid_candidate_type"] = candidate_type
    return tagged


def _rank_diverse_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [dict(candidate) for candidate in candidates]
    candidates.sort(key=lambda item: item.get("cost_tuple") or solution_cost_tuple(item["result"]))
    for rank, candidate in enumerate(candidates, start=1):
        candidate["ga_rank"] = rank
        candidate["result"]["metadata"] = dict(candidate["result"].get("metadata", {}))
        candidate["result"]["metadata"]["ga_candidate_rank"] = rank
        candidate["result"]["metadata"]["hybrid_candidate_type"] = candidate.get("candidate_type", "balanced")
    if candidates:
        best_solution = candidates[0]["solution"]
        for candidate in candidates:
            candidate["similarity_to_ga_best"] = _simple_solution_similarity(best_solution, candidate["solution"])
    return candidates


def _solution_key(solution: dict[str, Any]) -> tuple[Any, ...]:
    routes = solution.get("truck_routes") or [solution.get("truck_route", [])]
    tasks = solution.get("drone_tasks", [])
    return (
        tuple(tuple(int(node) for node in route) for route in routes),
        tuple(tuple(int(node) for node in task.get("drone_route", [])) for task in tasks),
    )


def _simple_solution_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_edges = _simple_edges(left)
    right_edges = _simple_edges(right)
    if not left_edges and not right_edges:
        return 1.0
    union = left_edges | right_edges
    return len(left_edges & right_edges) / len(union) if union else 0.0


def _simple_edges(solution: dict[str, Any]) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for route in solution.get("truck_routes") or [solution.get("truck_route", [])]:
        route = [int(node) for node in route]
        edges.update((left, right) for left, right in zip(route, route[1:]))
    for task in solution.get("drone_tasks", []):
        route = [int(node) for node in task.get("drone_route", [])]
        edges.update((left, right) for left, right in zip(route, route[1:]))
    return edges


def _individual_key(individual: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(int(customer_id) for customer_id in individual.get("customer_order", [])),
        tuple(sorted((int(customer_id), str(mode)) for customer_id, mode in individual.get("service_mode", {}).items())),
        int(individual.get("max_vehicle_count", 1)),
        str(individual.get("drone_charging_preference", "allow")),
    )


def _default_time_budget_seconds(instance: dict) -> float:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        return 15.0
    if customer_count <= 10:
        return 45.0
    if customer_count <= 25:
        return 120.0
    if customer_count <= 50:
        return 240.0
    return 360.0
