"""Constraint-aware GA decoder tools for Truck-Drone EVRPTW-NL."""

from __future__ import annotations

import random
from typing import Any

try:
    from ..evaluator import evaluate_solution
    from ..charging import target_energy
    from ..route_simulator import distance
    from ..spatial_metrics import cluster_bias, cluster_customer_order, sweep_customer_order
    from .common import add_charging_decisions, sorted_customer_ids
except ImportError:  # pragma: no cover
    from evaluator import evaluate_solution
    from charging import target_energy
    from route_simulator import distance
    from spatial_metrics import cluster_bias, cluster_customer_order, sweep_customer_order
    from solvers.common import add_charging_decisions, sorted_customer_ids


MAX_DRONE_CANDIDATES_PER_ROUTE = 6
MAX_DRONE_EXTENSION_ROUNDS = 3
MAX_LAUNCH_RECOVER_PAIRS = 10
MAX_REBALANCE_ATTEMPTS = 18
MAX_GA_INDIVIDUALS = 18


def build_ga_aware_solution(
    instance: dict,
    customer_order: list[int],
    charging_policy: str,
    max_vehicle_count: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Build a solution with TW/Energy/Charging/Drone/Sync-aware GA decisions."""
    individual = make_ga_individual(
        instance,
        customer_order,
        charging_policy,
        max_vehicle_count=max_vehicle_count or default_max_vehicle_count(instance),
        seed=int(seed if seed is not None else instance.get("seed", 1987)),
    )
    return decode_ga_individual(instance, individual)


def make_ga_individual(
    instance: dict,
    customer_order: list[int],
    charging_policy: str,
    max_vehicle_count: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    service_mode: dict[int, str] = {}
    drone_priority: dict[int, float] = {}
    route_split_bias: dict[int, int] = {}
    max_vehicle_count = max(1, int(max_vehicle_count))
    for customer in instance["customers"]:
        customer_id = int(customer["id"])
        drone_priority[customer_id] = rng.random()
        route_split_bias[customer_id] = rng.randrange(max_vehicle_count)
        if _good_drone_seed(instance, customer) and rng.random() < 0.45:
            service_mode[customer_id] = "drone"
        else:
            service_mode[customer_id] = "truck"
    if rng.random() < 0.35:
        route_split_bias.update(cluster_bias(instance, max_vehicle_count))
    return {
        "customer_order": list(customer_order),
        "service_mode": service_mode,
        "drone_priority": drone_priority,
        "charging_policy": charging_policy,
        "max_vehicle_count": max_vehicle_count,
        "route_split_bias": route_split_bias,
        "drone_charging_preference": rng.choice(["allow", "prefer_if_needed", "avoid"]),
    }


def decode_ga_individual(instance: dict, individual: dict[str, Any]) -> dict[str, Any]:
    """Decode order + service mode into a multi-route Truck-Drone solution."""
    best_solution: dict[str, Any] | None = None
    best_evaluation: dict[str, Any] | None = None
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
    max_vehicle_count = max(1, int(individual.get("max_vehicle_count", 1)))
    for vehicle_count in range(1, max_vehicle_count + 1):
        solution = _build_solution_for_vehicle_count(instance, individual, vehicle_count, eval_cache)
        evaluation = _evaluate_cached(instance, solution, individual["charging_policy"], eval_cache)
        if best_evaluation is None or _result_rank(evaluation, vehicle_count) < _result_rank(best_evaluation, len(best_solution["truck_routes"])):
            best_solution = solution
            best_evaluation = evaluation
        if evaluation["feasible"]:
            break
    assert best_solution is not None
    return best_solution


def _build_solution_for_vehicle_count(
    instance: dict,
    individual: dict[str, Any],
    vehicle_count: int,
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    depot_id = int(instance["depot"]["id"])
    charging_policy = individual["charging_policy"]
    service_mode = {int(key): value for key, value in individual.get("service_mode", {}).items()}
    clean_routes = [[depot_id, depot_id] for _ in range(vehicle_count)]
    drone_tasks: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []

    for customer_id in individual["customer_order"]:
        customer_id = int(customer_id)
        clean_routes = _insert_customer_into_best_route(
            instance,
            clean_routes,
            drone_tasks,
            customer_id,
            charging_policy,
            eval_cache,
            individual.get("route_split_bias", {}),
        )

    clean_routes = _rebalance_routes(instance, clean_routes, drone_tasks, charging_policy, eval_cache)

    current_solution = _solution_from_clean_routes(instance, clean_routes, drone_tasks, charging_policy, fallbacks)
    current_evaluation = _evaluate_cached(instance, current_solution, charging_policy, eval_cache)
    current_score = _score_evaluation(current_evaluation)

    drone_order = sorted(
        [int(customer_id) for customer_id in individual["customer_order"] if service_mode.get(int(customer_id), "truck") == "drone"],
        key=lambda customer_id: float(individual.get("drone_priority", {}).get(customer_id, 0.0)),
        reverse=True,
    )
    for customer_id in drone_order:
        route_index = _route_index_containing(clean_routes, int(customer_id))
        if route_index is None:
            continue
        candidate = select_best_drone_task_multi(
            instance,
            clean_routes,
            drone_tasks,
            int(customer_id),
            charging_policy,
            individual=individual,
            eval_cache=eval_cache,
        )
        if candidate is None:
            fallbacks.append({"customer": customer_id, "from": "drone", "to": "truck", "reason": "no_feasible_multi_customer_drone_route"})
            continue
        if _acceptable_drone_candidate(current_evaluation, candidate["evaluation"]) and candidate["score"] < current_score - 1e-6:
            clean_routes = candidate["clean_routes"]
            drone_tasks = candidate["drone_tasks"]
            current_solution = candidate["solution"]
            current_evaluation = candidate["evaluation"]
            current_score = candidate["score"]

    current_solution["metadata"] = {
        "construction": "ga_decoder",
        "ga_decoder": "aware_hierarchical_decoder_v2",
        "ga_stage": "stage_4_8_runtime_pruned_structural_ga",
        "aware_components": ["TW", "Energy", "Charging", "Drone", "Sync"],
        "runtime_controls": {
            "max_drone_candidates_per_route": MAX_DRONE_CANDIDATES_PER_ROUTE,
            "max_drone_extension_rounds": MAX_DRONE_EXTENSION_ROUNDS,
            "max_launch_recover_pairs": MAX_LAUNCH_RECOVER_PAIRS,
            "max_rebalance_attempts": MAX_REBALANCE_ATTEMPTS,
        },
        "max_vehicle_count": individual["max_vehicle_count"],
        "vehicle_count_used": len(current_solution["truck_routes"]),
        "fallbacks": fallbacks,
    }
    return current_solution


def _insert_customer_into_best_route(
    instance: dict,
    clean_routes: list[list[int]],
    drone_tasks: list[dict[str, int]],
    customer_id: int,
    charging_policy: str,
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] | None = None,
    route_split_bias: dict[int, int] | None = None,
) -> list[list[int]]:
    best: dict[str, Any] | None = None
    preferred_route = None
    if route_split_bias:
        preferred_route = int(route_split_bias.get(customer_id, 0)) % max(1, len(clean_routes))
    for route_index, route in enumerate(clean_routes):
        insertion = evaluate_truck_insertion(instance, route, customer_id, charging_policy)
        candidate_routes = [list(candidate) for candidate in clean_routes]
        candidate_routes[route_index] = insertion["clean_route"]
        solution = _solution_from_clean_routes(instance, candidate_routes, drone_tasks, charging_policy, [])
        evaluation = _evaluate_cached(instance, solution, charging_policy, eval_cache)
        bias_penalty = 0.0 if preferred_route is None or route_index == preferred_route else 25.0
        candidate = {"routes": candidate_routes, "score": _score_evaluation(evaluation) + bias_penalty}
        if best is None or candidate["score"] < best["score"]:
            best = candidate
    assert best is not None
    return best["routes"]


def simulate_partial_truck_route(instance: dict, clean_route: list[int], charging_policy: str) -> dict[str, Any]:
    """Evaluate a truck-only candidate route after GA charging decisions."""
    solution = _solution_from_clean_route(instance, clean_route, [], charging_policy)
    return evaluate_solution(instance, solution, charging_policy)


def _rebalance_routes(
    instance: dict,
    clean_routes: list[list[int]],
    drone_tasks: list[dict[str, Any]],
    charging_policy: str,
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] | None,
) -> list[list[int]]:
    """Try a small number of cross-route moves before drone conversion."""
    if len(clean_routes) <= 1:
        return clean_routes
    current_routes = [list(route) for route in clean_routes]
    current_solution = _solution_from_clean_routes(instance, current_routes, drone_tasks, charging_policy, [])
    current_eval = _evaluate_cached(instance, current_solution, charging_policy, eval_cache)
    current_score = _score_evaluation(current_eval)
    customers = {int(customer["id"]): customer for customer in instance["customers"]}
    attempts = 0
    improved = True
    while improved and attempts < MAX_REBALANCE_ATTEMPTS:
        improved = False
        route_order = sorted(range(len(current_routes)), key=lambda idx: len(current_routes[idx]), reverse=True)
        for from_idx in route_order:
            movable = [node for node in current_routes[from_idx][1:-1] if int(node) in customers]
            movable.sort(key=lambda node: (float(customers[int(node)].get("due_time", 0.0)), -float(customers[int(node)].get("demand", 0.0))))
            for customer_id in movable[:3]:
                for to_idx in range(len(current_routes)):
                    if to_idx == from_idx:
                        continue
                    attempts += 1
                    trial_routes = [list(route) for route in current_routes]
                    trial_routes[from_idx] = [node for node in trial_routes[from_idx] if int(node) != int(customer_id)]
                    insertion = evaluate_truck_insertion(instance, trial_routes[to_idx], int(customer_id), charging_policy)
                    trial_routes[to_idx] = insertion["clean_route"]
                    solution = _solution_from_clean_routes(instance, trial_routes, drone_tasks, charging_policy, [])
                    evaluation = _evaluate_cached(instance, solution, charging_policy, eval_cache)
                    score = _score_evaluation(evaluation)
                    if score < current_score - 1e-6:
                        current_routes = trial_routes
                        current_score = score
                        improved = True
                        break
                    if attempts >= MAX_REBALANCE_ATTEMPTS:
                        break
                if improved or attempts >= MAX_REBALANCE_ATTEMPTS:
                    break
            if improved or attempts >= MAX_REBALANCE_ATTEMPTS:
                break
    return current_routes


def evaluate_truck_insertion(
    instance: dict,
    clean_route: list[int],
    customer_id: int,
    charging_policy: str,
) -> dict[str, Any]:
    """Try all truck insertion positions and return the lowest-penalty candidate."""
    best: dict[str, Any] | None = None
    for position in range(1, len(clean_route)):
        candidate_route = list(clean_route)
        candidate_route.insert(position, customer_id)
        evaluation = simulate_partial_truck_route(instance, candidate_route, charging_policy)
        score = _score_evaluation(evaluation)
        candidate = {"clean_route": candidate_route, "evaluation": evaluation, "score": score}
        if best is None or candidate["score"] < best["score"]:
            best = candidate
    assert best is not None
    return best


def evaluate_drone_task(
    instance: dict,
    clean_route: list[int],
    existing_tasks: list[dict[str, int]],
    customer_id: int,
    launch: int,
    recover: int,
    charging_policy: str,
) -> dict[str, Any]:
    """Evaluate one launch-customer-recover drone task candidate."""
    candidate_route = [node for node in clean_route if node != customer_id]
    task = {"launch": int(launch), "customer": int(customer_id), "customers": [int(customer_id)], "recover": int(recover)}
    tasks = list(existing_tasks) + [task]
    solution = _solution_from_clean_route(instance, candidate_route, tasks, charging_policy)
    evaluation = evaluate_solution(instance, solution, charging_policy)
    score = _score_evaluation(evaluation)
    return {
        "clean_route": candidate_route,
        "drone_tasks": tasks,
        "solution": solution,
        "evaluation": evaluation,
        "score": score,
        "task": task,
    }


def select_best_drone_task_multi(
    instance: dict,
    clean_routes: list[list[int]],
    existing_tasks: list[dict[str, Any]],
    customer_id: int,
    charging_policy: str,
    individual: dict[str, Any] | None = None,
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    route_index = _route_index_containing(clean_routes, customer_id)
    if route_index is None:
        return None
    route = clean_routes[route_index]
    customers = {int(customer["id"]): customer for customer in instance["customers"]}
    customer = customers.get(int(customer_id))
    if not customer or not bool(customer.get("drone_eligible", False)):
        return None
    occupied_customers = set(_all_task_customers(existing_tasks))
    if customer_id in occupied_customers:
        return None
    for task in existing_tasks:
        if customer_id in {int(task["launch"]), int(task["recover"])}:
            return None

    route_customer_ids = [int(node) for node in route if int(node) in customers]
    priorities = {int(key): float(value) for key, value in (individual or {}).get("drone_priority", {}).items()}
    candidate_pool = [
        node_id
        for node_id in route_customer_ids
        if node_id not in occupied_customers
        and bool(customers[node_id].get("drone_eligible", False))
        and float(customers[node_id].get("demand", 0.0)) <= float(instance["drone"]["capacity"])
    ]
    if customer_id not in candidate_pool:
        return None
    candidate_pool = _rank_drone_candidate_pool(instance, candidate_pool, customer_id, priorities)
    group = [customer_id]
    best = _best_drone_group_candidate(instance, clean_routes, existing_tasks, route_index, group, charging_policy, eval_cache)
    current_score = best["score"] if best is not None else float("inf")

    improved = True
    rounds = 0
    while improved and rounds < MAX_DRONE_EXTENSION_ROUNDS:
        improved = False
        rounds += 1
        best_extension: dict[str, Any] | None = None
        for next_customer in candidate_pool[:MAX_DRONE_CANDIDATES_PER_ROUTE]:
            if next_customer in group:
                continue
            extended_group = _order_drone_customers(instance, group + [next_customer])
            candidate = _best_drone_group_candidate(
                instance,
                clean_routes,
                existing_tasks,
                route_index,
                extended_group,
                charging_policy,
                eval_cache,
            )
            if candidate is None:
                continue
            if candidate["score"] < current_score - 1e-6 and (best_extension is None or candidate["score"] < best_extension["score"]):
                best_extension = candidate
        if best_extension is not None:
            best = best_extension
            current_score = best_extension["score"]
            group = list(best_extension["task"]["customers"])
            improved = True
    return best


def _best_drone_group_candidate(
    instance: dict,
    clean_routes: list[list[int]],
    existing_tasks: list[dict[str, Any]],
    route_index: int,
    group: list[int],
    charging_policy: str,
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    route = clean_routes[route_index]
    candidate_route = [node for node in route if int(node) not in set(group)]
    if len(candidate_route) < 2:
        return None
    best: dict[str, Any] | None = None
    for launch_pos, launch, recover in _rank_launch_recover_pairs(instance, candidate_route, group):
        ordered_customers = _order_drone_customers(instance, group, start=int(launch), end=int(recover))
        raw_route = [int(launch)] + ordered_customers + [int(recover)]
        drone_route, drone_plans = _add_drone_charging_decisions(instance, raw_route, charging_policy)
        task = {
            "route_index": route_index,
            "launch": int(launch),
            "customers": ordered_customers,
            "customer": ordered_customers[0],
            "drone_route": drone_route,
            "recover": int(recover),
            "charging_plan": drone_plans,
        }
        candidate_tasks = list(existing_tasks) + [task]
        candidate_routes = [list(candidate) for candidate in clean_routes]
        candidate_routes[route_index] = candidate_route
        solution = _solution_from_clean_routes(instance, candidate_routes, candidate_tasks, charging_policy, [])
        evaluation = _evaluate_cached(instance, solution, charging_policy, eval_cache)
        candidate = {
            "clean_routes": candidate_routes,
            "drone_tasks": candidate_tasks,
            "solution": solution,
            "evaluation": evaluation,
            "score": _score_evaluation(evaluation),
            "task": task,
        }
        if best is None or candidate["score"] < best["score"]:
            best = candidate
    return best


def select_best_drone_task(
    instance: dict,
    clean_route: list[int],
    existing_tasks: list[dict[str, int]],
    customer_id: int,
    charging_policy: str,
) -> dict[str, Any] | None:
    """Enumerate launch/recover pairs and return the best drone task candidate."""
    customers = {int(customer["id"]): customer for customer in instance["customers"]}
    customer = customers.get(int(customer_id))
    if not customer or not bool(customer.get("drone_eligible", False)):
        return None
    if customer_id not in clean_route:
        return None
    for task in existing_tasks:
        if customer_id in {int(task["launch"]), int(task["recover"])}:
            return None

    candidate_route = [node for node in clean_route if node != customer_id]
    if len(candidate_route) < 2:
        return None

    best: dict[str, Any] | None = None
    for launch_pos, launch in enumerate(candidate_route[:-1]):
        for recover in candidate_route[launch_pos + 1 :]:
            candidate = evaluate_drone_task(
                instance,
                clean_route,
                existing_tasks,
                customer_id,
                int(launch),
                int(recover),
                charging_policy,
            )
            if best is None or candidate["score"] < best["score"]:
                best = candidate
    return best


def _solution_from_clean_route(
    instance: dict,
    clean_route: list[int],
    drone_tasks: list[dict[str, int]],
    charging_policy: str,
) -> dict[str, Any]:
    solution = {
        "truck_route": list(clean_route),
        "drone_tasks": [dict(task) for task in drone_tasks],
        "charging_plan": [],
        "metadata": {"construction": "ga_decoder_candidate"},
    }
    return add_charging_decisions(instance, solution, charging_policy)


def _solution_from_clean_routes(
    instance: dict,
    clean_routes: list[list[int]],
    drone_tasks: list[dict[str, int]],
    charging_policy: str,
    fallbacks: list[dict[str, Any]],
) -> dict[str, Any]:
    truck_routes: list[list[int]] = []
    charging_plan: list[dict[str, Any]] = []
    for route_index, route in enumerate(clean_routes):
        route_solution = {
            "truck_route": list(route),
            "drone_tasks": [],
            "charging_plan": [],
            "metadata": {"construction": "ga_decoder_route_candidate"},
        }
        charged = add_charging_decisions(instance, route_solution, charging_policy)
        truck_routes.append(charged["truck_route"])
        for plan in charged.get("charging_plan", []):
            plan = dict(plan)
            plan["vehicle"] = "truck"
            plan["route_index"] = route_index
            charging_plan.append(plan)
    cleaned_tasks: list[dict[str, Any]] = []
    for task_index, task in enumerate(drone_tasks):
        cleaned = dict(task)
        task_plans = [dict(plan) for plan in cleaned.pop("charging_plan", [])]
        cleaned_tasks.append(cleaned)
        for plan in task_plans:
            plan["vehicle"] = "drone"
            plan["route_index"] = int(cleaned.get("route_index", 0))
            plan["task_index"] = task_index
            charging_plan.append(plan)
    solution = {
        "truck_routes": truck_routes,
        "truck_route": truck_routes[0] if truck_routes else [],
        "drone_tasks": cleaned_tasks,
        "charging_plan": charging_plan,
        "metadata": {"construction": "ga_decoder_candidate", "fallbacks": list(fallbacks)},
    }
    return solution


def _evaluate_cached(
    instance: dict,
    solution: dict[str, Any],
    charging_policy: str,
    eval_cache: dict[tuple[Any, ...], dict[str, Any]] | None,
) -> dict[str, Any]:
    if eval_cache is None:
        return evaluate_solution(instance, solution, charging_policy)
    key = _solution_cache_key(solution, charging_policy)
    cached = eval_cache.get(key)
    if cached is None:
        cached = evaluate_solution(instance, solution, charging_policy)
        eval_cache[key] = cached
    return cached


def _solution_cache_key(solution: dict[str, Any], charging_policy: str) -> tuple[Any, ...]:
    truck_routes = solution.get("truck_routes")
    if not truck_routes:
        truck_routes = [solution.get("truck_route", [])]
    route_key = tuple(tuple(int(node) for node in route) for route in truck_routes)
    task_key = []
    for task in solution.get("drone_tasks", []):
        task_key.append(
            (
                int(task.get("route_index", 0)),
                tuple(int(node) for node in task.get("drone_route", [])),
                tuple(int(customer) for customer in task.get("customers", [])),
                int(task.get("launch", 0)),
                int(task.get("recover", 0)),
            )
        )
    plan_key = []
    for plan in solution.get("charging_plan", []):
        plan_key.append(
            (
                str(plan.get("vehicle", "truck")),
                int(plan.get("route_index", 0)),
                int(plan.get("task_index", -1)),
                int(plan.get("station", -1)),
                int(plan.get("visit_index", -1)),
                round(float(plan.get("target_energy", 0.0)), 6),
            )
        )
    return charging_policy, route_key, tuple(task_key), tuple(plan_key)


def _rank_drone_candidate_pool(
    instance: dict,
    candidate_pool: list[int],
    seed_customer_id: int,
    priorities: dict[int, float],
) -> list[int]:
    node_map = {int(node["id"]): node for node in instance["nodes"]}
    seed_node = node_map[int(seed_customer_id)]

    def score(node_id: int) -> tuple[float, float, float]:
        node = node_map[int(node_id)]
        spatial = distance(seed_node, node)
        due_time = float(node.get("due_time", 0.0))
        return (-priorities.get(int(node_id), 0.0), spatial, due_time)

    ranked = sorted(candidate_pool, key=score)
    if seed_customer_id in ranked:
        ranked.remove(seed_customer_id)
    return [seed_customer_id] + ranked[: max(0, MAX_DRONE_CANDIDATES_PER_ROUTE - 1)]


def _rank_launch_recover_pairs(instance: dict, candidate_route: list[int], group: list[int]) -> list[tuple[int, int, int]]:
    node_map = {int(node["id"]): node for node in instance["nodes"]}
    pairs: list[tuple[float, int, int, int]] = []
    group_nodes = [node_map[int(customer_id)] for customer_id in group]
    for launch_pos, launch in enumerate(candidate_route[:-1]):
        for recover in candidate_route[launch_pos + 1 :]:
            launch_node = node_map[int(launch)]
            recover_node = node_map[int(recover)]
            cover_distance = sum(min(distance(launch_node, customer), distance(recover_node, customer)) for customer in group_nodes)
            interval_distance = distance(launch_node, recover_node)
            pairs.append((cover_distance + 0.1 * interval_distance, launch_pos, int(launch), int(recover)))
    pairs.sort(key=lambda item: item[0])
    return [(launch_pos, launch, recover) for _, launch_pos, launch, recover in pairs[:MAX_LAUNCH_RECOVER_PAIRS]]


def _score_evaluation(evaluation: dict[str, Any]) -> float:
    violations = evaluation["violations"]
    metrics = evaluation["metrics"]
    total_violation = sum(float(value) for value in violations.values())
    battery_violation = float(violations.get("truck_battery", 0.0)) + float(violations.get("drone_battery", 0.0))
    return (
        1_000_000.0 * total_violation
        + 100_000.0 * float(violations.get("customer_coverage", 0.0))
        + 100_000.0 * float(violations.get("capacity", 0.0))
        + 50_000.0 * battery_violation
        + 20_000.0 * float(violations.get("drone_mission", 0.0))
        + 1_000.0 * float(metrics.get("completion_time", 0.0))
        + float(metrics.get("total_distance", 0.0))
        + float(metrics.get("charging_time", 0.0))
        + float(metrics.get("waiting_time", 0.0))
        + 0.25 * float(metrics.get("petal_score", 0.0))
    )


def _acceptable_drone_candidate(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Never trade structural feasibility for a lower time-window violation."""
    structural_keys = [
        "customer_coverage",
        "customer_missing",
        "customer_duplicate",
        "truck_route",
        "drone_mission",
        "capacity",
        "truck_battery",
        "drone_battery",
        "charging",
        "sync",
    ]
    current_structural = sum(float(current["violations"].get(key, 0.0)) for key in structural_keys)
    candidate_structural = sum(float(candidate["violations"].get(key, 0.0)) for key in structural_keys)
    return candidate_structural <= current_structural + 1e-9


def _result_rank(evaluation: dict[str, Any], vehicle_count: int) -> tuple[float, int, float, float]:
    violations = evaluation["violations"]
    metrics = evaluation["metrics"]
    total_violation = sum(float(value) for value in violations.values())
    return (
        total_violation,
        int(vehicle_count),
        float(metrics.get("completion_time", 0.0)),
        float(metrics.get("total_distance", 0.0)) + float(metrics.get("charging_time", 0.0)) + float(metrics.get("waiting_time", 0.0)),
    )


def _route_index_containing(routes: list[list[int]], customer_id: int) -> int | None:
    for idx, route in enumerate(routes):
        if customer_id in route:
            return idx
    return None


def _all_task_customers(tasks: list[dict[str, Any]]) -> list[int]:
    customers: list[int] = []
    for task in tasks:
        if "customers" in task:
            customers.extend(int(customer_id) for customer_id in task.get("customers", []))
        elif "customer" in task:
            customers.append(int(task["customer"]))
        elif "drone_route" in task:
            route = [int(node_id) for node_id in task.get("drone_route", [])]
            customer_ids = {int(customer["id"]) for customer in []}
            customers.extend(node_id for node_id in route[1:-1] if node_id in customer_ids)
    return customers


def _good_drone_seed(instance: dict, customer: dict) -> bool:
    if not bool(customer.get("drone_eligible", False)):
        return False
    if float(customer.get("demand", 0.0)) > float(instance["drone"]["capacity"]):
        return False
    depot = instance["depot"]
    round_trip = 2.0 * distance(depot, customer)
    if round_trip * float(instance["drone"]["consumption_rate"]) > float(instance["drone"]["battery_capacity"]) * 1.25:
        return False
    ready = float(customer.get("ready_time", 0.0))
    due = float(customer.get("due_time", 0.0))
    return due - ready >= 5.0


def _order_drone_customers(instance: dict, customers: list[int], start: int | None = None, end: int | None = None) -> list[int]:
    node_map = {int(node["id"]): node for node in instance["nodes"]}
    remaining = [int(customer_id) for customer_id in customers]
    if not remaining:
        return []
    current = int(start if start is not None else remaining[0])
    ordered: list[int] = []
    while remaining:
        next_customer = min(
            remaining,
            key=lambda customer_id: (
                distance(node_map[current], node_map[customer_id]),
                float(node_map[customer_id].get("due_time", 0.0)),
            ),
        )
        ordered.append(next_customer)
        remaining.remove(next_customer)
        current = next_customer
    if end is not None and len(ordered) <= 5:
        # A small local cleanup: moving a customer closer to the recover node can
        # reduce synchronization wait without enumerating all permutations.
        ordered.sort(key=lambda customer_id: distance(node_map[customer_id], node_map[int(end)]))
    return ordered


def _add_drone_charging_decisions(instance: dict, drone_route: list[int], charging_policy: str) -> tuple[list[int], list[dict[str, Any]]]:
    if len(drone_route) < 2:
        return list(drone_route), []
    node_map = {int(node["id"]): node for node in instance["nodes"]}
    stations = list(instance["stations"])
    station_ids = {int(station["id"]) for station in stations}
    battery_capacity = float(instance["drone"]["battery_capacity"])
    consumption_rate = float(instance["drone"]["consumption_rate"])
    safety_margin = float(instance["charging"].get("safety_margin", 0.0))
    energy = battery_capacity
    new_route = [int(drone_route[0])]
    plans: list[dict[str, Any]] = []
    for next_node in [int(node_id) for node_id in drone_route[1:]]:
        current = new_route[-1]
        leg_energy = distance(node_map[current], node_map[next_node]) * consumption_rate
        should_charge = energy + 1e-9 < leg_energy
        if should_charge and current not in station_ids:
            station_choice = _best_drone_station(current, next_node, energy, stations, node_map, battery_capacity, consumption_rate)
            if station_choice is not None:
                station_id, arrival_energy, required_after_charge = station_choice
                new_route.append(station_id)
                target = target_energy(charging_policy, arrival_energy, battery_capacity, required_after_charge, safety_margin)
                plans.append(
                    {
                        "station": station_id,
                        "position_after": current,
                        "visit_index": len(new_route) - 1,
                        "arrival_energy": arrival_energy,
                        "target_energy": target,
                        "charging_policy": charging_policy,
                    }
                )
                energy = target
                current = station_id
                leg_energy = distance(node_map[current], node_map[next_node]) * consumption_rate
        energy -= leg_energy
        new_route.append(next_node)
    return new_route, plans


def _best_drone_station(
    current: int,
    next_node: int,
    energy: float,
    stations: list[dict],
    node_map: dict[int, dict],
    battery_capacity: float,
    consumption_rate: float,
) -> tuple[int, float, float] | None:
    feasible: list[tuple[float, int, float, float]] = []
    direct_distance = distance(node_map[current], node_map[next_node])
    for station in stations:
        station_id = int(station["id"])
        to_station = distance(node_map[current], node_map[station_id]) * consumption_rate
        station_to_next = distance(node_map[station_id], node_map[next_node]) * consumption_rate
        if to_station <= energy + 1e-9 and station_to_next <= battery_capacity + 1e-9:
            detour = distance(node_map[current], node_map[station_id]) + distance(node_map[station_id], node_map[next_node]) - direct_distance
            feasible.append((detour, station_id, energy - to_station, station_to_next))
    if not feasible:
        return None
    _, station_id, arrival_energy, required_after_charge = min(feasible, key=lambda item: item[0])
    return station_id, arrival_energy, required_after_charge


def default_max_vehicle_count(instance: dict) -> int:
    customer_count = len(instance.get("customers", []))
    return min(18, max(2, (customer_count + 2) // 3))


def candidate_individuals(instance: dict, orders: list[list[int]], charging_policy: str, seed: int) -> list[dict[str, Any]]:
    individuals: list[dict[str, Any]] = []
    max_vehicle_count = default_max_vehicle_count(instance)
    stable_order = sorted_customer_ids(instance)
    stable = make_ga_individual(instance, stable_order, charging_policy, max_vehicle_count, seed)
    individuals.append(stable)
    individuals.append(mutate_individual(instance, stable, seed + 100))
    for idx, order in enumerate(orders):
        base = make_ga_individual(instance, order, charging_policy, max_vehicle_count, seed + idx)
        individuals.append(base)
        mutated = mutate_individual(instance, base, seed + 100 + idx)
        individuals.append(mutated)
        truck_heavy = _mode_shifted_individual(base, mode="truck")
        drone_heavy = _mode_shifted_individual(base, mode="drone")
        individuals.extend([truck_heavy, drone_heavy])
        if len(individuals) >= MAX_GA_INDIVIDUALS:
            break
    if len(individuals) >= 2:
        individuals.append(crossover_individual(instance, individuals[0], individuals[1], seed + 500))
    return _deduplicate_individuals(individuals)[:MAX_GA_INDIVIDUALS]


def mutate_individual(instance: dict, individual: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    mutated = {
        "customer_order": list(individual["customer_order"]),
        "service_mode": dict(individual["service_mode"]),
        "drone_priority": dict(individual.get("drone_priority", {})),
        "charging_policy": individual["charging_policy"],
        "max_vehicle_count": individual["max_vehicle_count"],
        "route_split_bias": dict(individual.get("route_split_bias", {})),
        "drone_charging_preference": individual.get("drone_charging_preference", "allow"),
    }
    eligible = [int(customer["id"]) for customer in instance["customers"] if bool(customer.get("drone_eligible", False))]
    if eligible:
        for customer_id in rng.sample(eligible, k=min(2, len(eligible))):
            mutated["service_mode"][customer_id] = "truck" if mutated["service_mode"].get(customer_id) == "drone" else "drone"
    if len(mutated["customer_order"]) >= 2:
        i, j = sorted(rng.sample(range(len(mutated["customer_order"])), 2))
        mutated["customer_order"][i], mutated["customer_order"][j] = mutated["customer_order"][j], mutated["customer_order"][i]
    if len(mutated["customer_order"]) >= 3 and rng.random() < 0.45:
        sweep_index = {customer_id: idx for idx, customer_id in enumerate(sweep_customer_order(instance))}
        ordered_positions = sorted(range(len(mutated["customer_order"])), key=lambda pos: sweep_index.get(mutated["customer_order"][pos], pos))
        center = rng.choice(ordered_positions)
        left = max(0, center - 1)
        right = min(len(mutated["customer_order"]) - 1, center + 1)
        mutated["customer_order"][left : right + 1] = sorted(
            mutated["customer_order"][left : right + 1],
            key=lambda customer_id: sweep_index.get(customer_id, 0),
        )
    if len(mutated["customer_order"]) >= 4 and rng.random() < 0.5:
        i, j = sorted(rng.sample(range(len(mutated["customer_order"])), 2))
        mutated["customer_order"][i : j + 1] = reversed(mutated["customer_order"][i : j + 1])
    if mutated["drone_priority"]:
        for customer_id in rng.sample(list(mutated["drone_priority"]), k=min(3, len(mutated["drone_priority"]))):
            mutated["drone_priority"][customer_id] = min(1.0, max(0.0, float(mutated["drone_priority"][customer_id]) + rng.uniform(-0.25, 0.25)))
    if mutated["route_split_bias"]:
        for customer_id in rng.sample(list(mutated["route_split_bias"]), k=min(3, len(mutated["route_split_bias"]))):
            mutated["route_split_bias"][customer_id] = rng.randrange(max(1, int(mutated["max_vehicle_count"])))
    if rng.random() < 0.35:
        clustered = cluster_bias(instance, int(mutated["max_vehicle_count"]))
        for customer_id in rng.sample(list(clustered), k=min(4, len(clustered))):
            mutated["route_split_bias"][customer_id] = clustered[customer_id]
    if rng.random() < 0.35:
        mutated["drone_charging_preference"] = rng.choice(["avoid", "allow", "prefer_if_needed"])
    if rng.random() < 0.25:
        current_max = int(mutated["max_vehicle_count"])
        mutated["max_vehicle_count"] = max(1, min(default_max_vehicle_count(instance), current_max + rng.choice([-1, 1])))
    return mutated


def crossover_individual(instance: dict, left: dict[str, Any], right: dict[str, Any], seed: int) -> dict[str, Any]:
    """Order-preserving crossover that also inherits service and split patterns."""
    rng = random.Random(seed)
    left_order = list(left["customer_order"])
    right_order = list(right["customer_order"])
    if len(left_order) < 2:
        return mutate_individual(instance, left, seed + 1)
    i, j = sorted(rng.sample(range(len(left_order)), 2))
    slice_part = left_order[i : j + 1]
    child_order = slice_part + [customer_id for customer_id in right_order if customer_id not in slice_part]
    service_mode = {}
    drone_priority = {}
    route_split_bias = {}
    max_vehicle_count = max(1, min(default_max_vehicle_count(instance), max(int(left["max_vehicle_count"]), int(right["max_vehicle_count"]))))
    for customer in instance["customers"]:
        customer_id = int(customer["id"])
        source = left if rng.random() < 0.5 else right
        service_mode[customer_id] = source.get("service_mode", {}).get(customer_id, "truck")
        drone_priority[customer_id] = float(source.get("drone_priority", {}).get(customer_id, rng.random()))
        route_split_bias[customer_id] = int(source.get("route_split_bias", {}).get(customer_id, 0)) % max_vehicle_count
    return {
        "customer_order": child_order,
        "service_mode": service_mode,
        "drone_priority": drone_priority,
        "charging_policy": left.get("charging_policy", right.get("charging_policy", "NPC")),
        "max_vehicle_count": max_vehicle_count,
        "route_split_bias": route_split_bias,
        "drone_charging_preference": rng.choice([left.get("drone_charging_preference", "allow"), right.get("drone_charging_preference", "allow")]),
    }


def _mode_shifted_individual(individual: dict[str, Any], mode: str) -> dict[str, Any]:
    shifted = {
        "customer_order": list(individual["customer_order"]),
        "service_mode": dict(individual["service_mode"]),
        "drone_priority": dict(individual.get("drone_priority", {})),
        "charging_policy": individual["charging_policy"],
        "max_vehicle_count": individual["max_vehicle_count"],
        "route_split_bias": dict(individual.get("route_split_bias", {})),
        "drone_charging_preference": individual.get("drone_charging_preference", "allow"),
    }
    eligible_ids = [customer_id for customer_id, priority in sorted(shifted["drone_priority"].items(), key=lambda item: item[1], reverse=True)]
    if mode == "truck":
        for customer_id in eligible_ids:
            shifted["service_mode"][int(customer_id)] = "truck"
    elif mode == "drone":
        for customer_id in eligible_ids[: max(1, len(eligible_ids) // 2)]:
            shifted["service_mode"][int(customer_id)] = "drone"
    return shifted


def _deduplicate_individuals(individuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for individual in individuals:
        key = (
            tuple(int(customer_id) for customer_id in individual["customer_order"]),
            tuple(sorted((int(customer_id), str(mode)) for customer_id, mode in individual.get("service_mode", {}).items())),
            int(individual.get("max_vehicle_count", 1)),
            str(individual.get("drone_charging_preference", "allow")),
        )
        if key not in seen:
            seen.add(key)
            unique.append(individual)
    return unique


def default_ga_orders(instance: dict, randomized_orders: list[list[int]]) -> list[list[int]]:
    """Keep a stable ordered route first, then add randomized GA candidates."""
    customer_rows = list(instance.get("customers", []))
    by_id = sorted_customer_ids(instance)
    by_ready_due = [
        int(customer["id"])
        for customer in sorted(
            customer_rows,
            key=lambda item: (float(item.get("ready_time", 0.0)), float(item.get("due_time", 0.0)), int(item["id"])),
        )
    ]
    by_due_ready = [
        int(customer["id"])
        for customer in sorted(
            customer_rows,
            key=lambda item: (float(item.get("due_time", 0.0)), float(item.get("ready_time", 0.0)), int(item["id"])),
        )
    ]
    sweep_order = sweep_customer_order(instance)
    reverse_sweep_order = sweep_customer_order(instance, reverse=True)
    cluster_order = cluster_customer_order(instance)
    cluster_then_tw_order = cluster_customer_order(instance, then_time_window=True)
    orders = []
    for order in [by_ready_due, by_due_ready, by_id]:
        if order and order not in orders:
            orders.append(order)
    for order in randomized_orders:
        if order not in orders:
            orders.append(order)
    for order in [sweep_order, reverse_sweep_order, cluster_order, cluster_then_tw_order]:
        if order and order not in orders:
            orders.append(order)
    return orders


def mutated_orders(base_orders: list[list[int]], seed: int, max_orders: int = 8) -> list[list[int]]:
    """Generate simple GA mutation candidates from customer orders."""
    rng = random.Random(seed)
    orders = [list(order) for order in base_orders]
    for order in base_orders:
        if len(order) < 2:
            continue
        swapped = list(order)
        i, j = sorted(rng.sample(range(len(swapped)), 2))
        swapped[i], swapped[j] = swapped[j], swapped[i]
        if swapped not in orders:
            orders.append(swapped)

        reversed_segment = list(order)
        i, j = sorted(rng.sample(range(len(reversed_segment)), 2))
        reversed_segment[i : j + 1] = reversed(reversed_segment[i : j + 1])
        if reversed_segment not in orders:
            orders.append(reversed_segment)

        if len(orders) >= max_orders:
            break
    return orders[:max_orders]
