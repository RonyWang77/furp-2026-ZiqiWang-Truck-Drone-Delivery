"""State propagation for Truck-Drone EVRPTW-NL solutions.

This module only evaluates a solution. It must not insert stations, remove
customers, open vehicles, or modify truck/drone decisions.
"""

from __future__ import annotations

import copy
import math
from typing import Any

try:
    from .charging import charge_time
except ImportError:  # pragma: no cover
    from charging import charge_time


def simulate_solution(instance: dict, solution: dict[str, Any], charging_policy: str) -> dict[str, Any]:
    if "truck_routes" in solution:
        return _simulate_multi_route_solution(instance, solution, charging_policy)

    original = copy.deepcopy(solution)
    node_map = {node["id"]: node for node in instance["nodes"]}
    customer_ids = {customer["id"] for customer in instance["customers"]}
    station_ids = {station["id"] for station in instance["stations"]}
    depot_id = instance["depot"]["id"]
    truck_route = list(solution.get("truck_route", []))
    drone_tasks = [_normalize_drone_task(dict(task)) for task in solution.get("drone_tasks", [])]
    charging_plan = [dict(plan) for plan in solution.get("charging_plan", [])]

    violations = _initial_violations()
    trace: dict[str, Any] = {"truck": [], "drone_tasks": [], "charging": []}
    metrics = {
        "truck_distance": 0.0,
        "drone_distance": 0.0,
        "total_distance": 0.0,
        "completion_time": 0.0,
        "waiting_time": 0.0,
        "truck_waiting_time": 0.0,
        "drone_waiting_time": 0.0,
        "charging_count": 0,
        "charging_time": 0.0,
    }

    _check_customer_coverage(instance, truck_route, drone_tasks, customer_ids, station_ids, violations)
    if not truck_route or truck_route[0] != depot_id or truck_route[-1] != depot_id:
        violations["truck_route"] += 1.0
    if any(node_id not in node_map for node_id in truck_route):
        violations["truck_route"] += 1.0

    route_positions = _route_positions(truck_route)
    _check_drone_tasks(instance, drone_tasks, route_positions, violations)
    _check_capacity(instance, truck_route, drone_tasks, customer_ids, station_ids, violations)

    pending_by_launch: dict[int, list[tuple[int, dict]]] = {}
    pending_by_recover: dict[int, list[tuple[int, dict]]] = {}
    for task_index, task in enumerate(drone_tasks):
        pending_by_launch.setdefault(int(task["launch"]), []).append((task_index, task))
        pending_by_recover.setdefault(int(task["recover"]), []).append((task_index, task))

    plan_by_visit = _charging_plan_by_visit(charging_plan)
    time = 0.0
    energy = float(instance["truck"]["battery_capacity"])
    truck_leg_count = max(0, len(truck_route) - 1)
    truck_battery_failed_legs: list[str] = []
    launched: dict[tuple[int, int, int], dict] = {}

    for index, node_id in enumerate(truck_route):
        node = node_map.get(node_id)
        if node is None:
            continue
        if index == 0:
            arrival = 0.0
            arrival_energy = energy
            leg_battery_violation = 0.0
        else:
            left_id = truck_route[index - 1]
            left = node_map[left_id]
            leg_distance = distance(left, node)
            metrics["truck_distance"] += leg_distance
            travel_time = leg_distance / max(float(instance["truck"]["speed"]), 1e-9)
            energy -= leg_distance * float(instance["truck"]["consumption_rate"])
            arrival_energy = energy
            leg_battery_violation = max(0.0, -energy)
            if energy < -1e-6:
                violations["truck_battery"] += abs(energy)
                truck_battery_failed_legs.append(f"{left_id}->{node_id}")
            arrival = time + travel_time
            time = arrival

        ready = float(node.get("ready_time", 0.0))
        due = float(node.get("due_time", math.inf))
        waiting = max(0.0, ready - time)
        time += waiting
        time_window_violation = 0.0
        if node_id in customer_ids and time > due + 1e-6:
            time_window_violation = time - due
            violations["time_window"] += time_window_violation
        service_start = time
        time += float(node.get("service_time", 0.0)) if node_id in customer_ids else 0.0

        charge_duration = 0.0
        if node_id in station_ids:
            plan = plan_by_visit.get((truck_route[index - 1] if index > 0 else depot_id, node_id, index))
            if plan is None:
                plan = plan_by_visit.get((truck_route[index - 1] if index > 0 else depot_id, node_id, -1))
            if plan is not None:
                arrival_energy = energy
                target = float(plan["target_energy"])
                if target < energy - 1e-6 or target > float(instance["truck"]["battery_capacity"]) + 1e-6:
                    violations["charging"] += 1.0
                target = min(max(target, energy), float(instance["truck"]["battery_capacity"]))
                charge_duration = charge_time(
                    charging_policy,
                    energy,
                    target,
                    float(instance["truck"]["battery_capacity"]),
                    float(instance["charging"]["linear_recharge_rate"]),
                    list(instance["charging"]["nonlinear_segments"]),
                )
                time += charge_duration
                energy = target
                metrics["charging_count"] += 1
                metrics["charging_time"] += charge_duration
                trace["charging"].append(
                    {
                        "station": node_id,
                        "arrival_energy": arrival_energy,
                        "target_energy": target,
                        "charging_time": charge_duration,
                        "policy": charging_policy,
                    }
                )

        for task_index, task in pending_by_launch.get(node_id, []):
            drone_plans = _plans_for_vehicle(charging_plan, "drone", task_index=task_index)
            task_trace = _simulate_drone_task(instance, task, time, node_map, customer_ids, station_ids, charging_policy, drone_plans, violations)
            launched[_task_key(task)] = task_trace
            trace["drone_tasks"].append(task_trace)
            metrics["drone_distance"] += task_trace["distance"]
            metrics["charging_count"] += task_trace["charging_count"]
            metrics["charging_time"] += task_trace["charging_time"]
            trace["charging"].extend(task_trace["charging_trace"])

        sync_wait = 0.0
        drone_wait = 0.0
        for _, task in pending_by_recover.get(node_id, []):
            task_trace = launched.get(_task_key(task))
            if task_trace is None:
                continue
            if task_trace["arrival_recover"] > time:
                sync_wait += task_trace["arrival_recover"] - time
            else:
                drone_wait += time - task_trace["arrival_recover"]
        if sync_wait:
            time += sync_wait
        metrics["truck_waiting_time"] += waiting + sync_wait
        metrics["drone_waiting_time"] += drone_wait
        metrics["waiting_time"] += waiting + sync_wait + drone_wait

        trace["truck"].append(
            {
                "node": node_id,
                "node_type": _node_type(node_id, depot_id, customer_ids, station_ids),
                "arrival_time": arrival,
                "ready_time": ready,
                "due_time": due,
                "service_start": service_start,
                "departure_time": time,
                "arrival_energy": arrival_energy,
                "departure_energy": energy,
                "energy": max(0.0, energy),
                "time_window_violation": time_window_violation,
                "battery_violation": leg_battery_violation,
                "waiting_time": waiting,
                "sync_wait": sync_wait,
                "drone_wait": drone_wait,
                "charging_time": charge_duration,
            }
        )

    metrics["completion_time"] = time
    metrics["total_distance"] = metrics["truck_distance"] + metrics["drone_distance"]
    diagnostics = _build_diagnostics(instance, trace, violations, truck_leg_count, truck_battery_failed_legs)
    if solution != original:
        raise RuntimeError("route_simulator modified the input solution.")
    feasible = all(value <= 1e-6 for value in violations.values())
    return {
        "feasible": feasible,
        "violations": violations,
        "metrics": metrics,
        "feasibility": diagnostics["feasibility"],
        "diagnostics": diagnostics["diagnostics"],
        "trace": trace,
    }


def distance(left: dict, right: dict) -> float:
    return math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"]))


def _simulate_multi_route_solution(instance: dict, solution: dict[str, Any], charging_policy: str) -> dict[str, Any]:
    original = copy.deepcopy(solution)
    node_map = {node["id"]: node for node in instance["nodes"]}
    customer_ids = {customer["id"] for customer in instance["customers"]}
    station_ids = {station["id"] for station in instance["stations"]}
    depot_id = instance["depot"]["id"]
    truck_routes = [list(route) for route in solution.get("truck_routes", [])]
    drone_tasks = [_normalize_drone_task(dict(task)) for task in solution.get("drone_tasks", [])]
    charging_plan = [dict(plan) for plan in solution.get("charging_plan", [])]

    violations = _initial_violations()
    trace: dict[str, Any] = {"truck": [], "drone_tasks": [], "charging": []}
    metrics = {
        "truck_distance": 0.0,
        "drone_distance": 0.0,
        "total_distance": 0.0,
        "completion_time": 0.0,
        "waiting_time": 0.0,
        "truck_waiting_time": 0.0,
        "drone_waiting_time": 0.0,
        "charging_count": 0,
        "charging_time": 0.0,
        "vehicle_count": len(truck_routes),
    }

    served_customers: list[int] = []
    route_positions_by_route: list[dict[int, list[int]]] = []
    for route_index, route in enumerate(truck_routes):
        if not route or route[0] != depot_id or route[-1] != depot_id:
            violations["truck_route"] += 1.0
        if any(node_id not in node_map for node_id in route):
            violations["truck_route"] += 1.0
        route_positions_by_route.append(_route_positions(route))
        served_customers.extend(node for node in route if node in customer_ids)

    tasks_by_route: dict[int, list[dict]] = {}
    for task in drone_tasks:
        route_index = int(task.get("route_index", 0))
        served_customers.extend(_task_customers(task))
        if route_index < 0 or route_index >= len(truck_routes):
            violations["drone_mission"] += 1.0
            continue
        tasks_by_route.setdefault(route_index, []).append(task)

    for route_index, route_tasks in tasks_by_route.items():
        _check_drone_tasks(instance, route_tasks, route_positions_by_route[route_index], violations)

    missing = customer_ids - set(served_customers)
    duplicate = len(served_customers) - len(set(served_customers))
    violations["customer_missing"] += float(len(missing))
    violations["customer_duplicate"] += float(max(0, duplicate))
    violations["customer_coverage"] += violations["customer_missing"] + violations["customer_duplicate"]

    customers = {customer["id"]: customer for customer in instance["customers"]}
    for route_index, route in enumerate(truck_routes):
        route_customer_ids = {node for node in route if node in customer_ids}
        for task in drone_tasks:
            if int(task.get("route_index", 0)) == route_index:
                route_customer_ids.update(_task_customers(task))
        route_demand = sum(float(customers[node_id]["demand"]) for node_id in route_customer_ids if node_id in customers)
        if route_demand > float(instance["truck"]["capacity"]):
            violations["capacity"] += route_demand - float(instance["truck"]["capacity"])

    truck_battery_failed_legs: list[str] = []
    truck_leg_count = sum(max(0, len(route) - 1) for route in truck_routes)
    for route_index, route in enumerate(truck_routes):
        route_result = _simulate_one_route_states(
            instance,
            route,
            route_index,
            [task for task in drone_tasks if int(task.get("route_index", 0)) == route_index],
            [plan for plan in charging_plan if int(plan.get("route_index", 0)) == route_index],
            charging_policy,
            violations,
        )
        for key in [
            "truck_distance",
            "drone_distance",
            "waiting_time",
            "truck_waiting_time",
            "drone_waiting_time",
            "charging_time",
        ]:
            metrics[key] += route_result["metrics"][key]
        metrics["charging_count"] += route_result["metrics"]["charging_count"]
        metrics["completion_time"] = max(metrics["completion_time"], route_result["metrics"]["completion_time"])
        trace["truck"].extend(route_result["trace"]["truck"])
        trace["drone_tasks"].extend(route_result["trace"]["drone_tasks"])
        trace["charging"].extend(route_result["trace"]["charging"])
        truck_battery_failed_legs.extend(route_result["truck_battery_failed_legs"])

    metrics["total_distance"] = metrics["truck_distance"] + metrics["drone_distance"]
    diagnostics = _build_diagnostics(instance, trace, violations, truck_leg_count, truck_battery_failed_legs)
    if solution != original:
        raise RuntimeError("route_simulator modified the input solution.")
    feasible = all(value <= 1e-6 for value in violations.values())
    return {
        "feasible": feasible,
        "violations": violations,
        "metrics": metrics,
        "feasibility": diagnostics["feasibility"],
        "diagnostics": diagnostics["diagnostics"],
        "trace": trace,
    }


def _simulate_one_route_states(
    instance: dict,
    truck_route: list[int],
    route_index: int,
    drone_tasks: list[dict],
    charging_plan: list[dict],
    charging_policy: str,
    violations: dict[str, float],
) -> dict[str, Any]:
    node_map = {node["id"]: node for node in instance["nodes"]}
    customer_ids = {customer["id"] for customer in instance["customers"]}
    station_ids = {station["id"] for station in instance["stations"]}
    depot_id = instance["depot"]["id"]
    trace: dict[str, Any] = {"truck": [], "drone_tasks": [], "charging": []}
    metrics = {
        "truck_distance": 0.0,
        "drone_distance": 0.0,
        "completion_time": 0.0,
        "waiting_time": 0.0,
        "truck_waiting_time": 0.0,
        "drone_waiting_time": 0.0,
        "charging_count": 0,
        "charging_time": 0.0,
    }
    pending_by_launch: dict[int, list[dict]] = {}
    pending_by_recover: dict[int, list[dict]] = {}
    for task_index, task in enumerate(drone_tasks):
        pending_by_launch.setdefault(int(task["launch"]), []).append((task_index, task))
        pending_by_recover.setdefault(int(task["recover"]), []).append((task_index, task))

    plan_by_visit = _charging_plan_by_visit(_plans_for_vehicle(charging_plan, "truck"))
    time = 0.0
    energy = float(instance["truck"]["battery_capacity"])
    launched: dict[tuple[int, int, int], dict] = {}
    truck_battery_failed_legs: list[str] = []

    for index, node_id in enumerate(truck_route):
        node = node_map.get(node_id)
        if node is None:
            continue
        if index == 0:
            arrival = 0.0
            arrival_energy = energy
            leg_battery_violation = 0.0
        else:
            left_id = truck_route[index - 1]
            left = node_map[left_id]
            leg_distance = distance(left, node)
            metrics["truck_distance"] += leg_distance
            travel_time = leg_distance / max(float(instance["truck"]["speed"]), 1e-9)
            energy -= leg_distance * float(instance["truck"]["consumption_rate"])
            arrival_energy = energy
            leg_battery_violation = max(0.0, -energy)
            if energy < -1e-6:
                violations["truck_battery"] += abs(energy)
                truck_battery_failed_legs.append(f"r{route_index}:{left_id}->{node_id}")
            arrival = time + travel_time
            time = arrival

        ready = float(node.get("ready_time", 0.0))
        due = float(node.get("due_time", math.inf))
        waiting = max(0.0, ready - time)
        time += waiting
        time_window_violation = 0.0
        if node_id in customer_ids and time > due + 1e-6:
            time_window_violation = time - due
            violations["time_window"] += time_window_violation
        service_start = time
        time += float(node.get("service_time", 0.0)) if node_id in customer_ids else 0.0

        charge_duration = 0.0
        if node_id in station_ids:
            plan = plan_by_visit.get((truck_route[index - 1] if index > 0 else depot_id, node_id, index))
            if plan is None:
                plan = plan_by_visit.get((truck_route[index - 1] if index > 0 else depot_id, node_id, -1))
            if plan is not None:
                arrival_energy = energy
                target = float(plan["target_energy"])
                if target < energy - 1e-6 or target > float(instance["truck"]["battery_capacity"]) + 1e-6:
                    violations["charging"] += 1.0
                target = min(max(target, energy), float(instance["truck"]["battery_capacity"]))
                charge_duration = charge_time(
                    charging_policy,
                    energy,
                    target,
                    float(instance["truck"]["battery_capacity"]),
                    float(instance["charging"]["linear_recharge_rate"]),
                    list(instance["charging"]["nonlinear_segments"]),
                )
                time += charge_duration
                energy = target
                metrics["charging_count"] += 1
                metrics["charging_time"] += charge_duration
                trace["charging"].append(
                    {
                        "route_index": route_index,
                        "station": node_id,
                        "arrival_energy": arrival_energy,
                        "target_energy": target,
                        "charging_time": charge_duration,
                        "policy": charging_policy,
                    }
                )

        for task_index, task in pending_by_launch.get(node_id, []):
            drone_plans = _plans_for_vehicle(charging_plan, "drone", task_index=task_index)
            task_trace = _simulate_drone_task(
                instance,
                task,
                time,
                node_map,
                customer_ids,
                station_ids,
                charging_policy,
                drone_plans,
                violations,
            )
            task_trace["route_index"] = route_index
            launched[_task_key(task)] = task_trace
            trace["drone_tasks"].append(task_trace)
            metrics["drone_distance"] += task_trace["distance"]
            metrics["charging_count"] += task_trace["charging_count"]
            metrics["charging_time"] += task_trace["charging_time"]
            trace["charging"].extend(task_trace["charging_trace"])

        sync_wait = 0.0
        drone_wait = 0.0
        for _, task in pending_by_recover.get(node_id, []):
            task_trace = launched.get(_task_key(task))
            if task_trace is None:
                continue
            if task_trace["arrival_recover"] > time:
                sync_wait += task_trace["arrival_recover"] - time
            else:
                drone_wait += time - task_trace["arrival_recover"]
        if sync_wait:
            time += sync_wait
        metrics["truck_waiting_time"] += waiting + sync_wait
        metrics["drone_waiting_time"] += drone_wait
        metrics["waiting_time"] += waiting + sync_wait + drone_wait

        trace["truck"].append(
            {
                "route_index": route_index,
                "node": node_id,
                "node_type": _node_type(node_id, depot_id, customer_ids, station_ids),
                "arrival_time": arrival,
                "ready_time": ready,
                "due_time": due,
                "service_start": service_start,
                "departure_time": time,
                "arrival_energy": arrival_energy,
                "departure_energy": energy,
                "energy": max(0.0, energy),
                "time_window_violation": time_window_violation,
                "battery_violation": leg_battery_violation,
                "waiting_time": waiting,
                "sync_wait": sync_wait,
                "drone_wait": drone_wait,
                "charging_time": charge_duration,
            }
        )

    metrics["completion_time"] = time
    return {"metrics": metrics, "trace": trace, "truck_battery_failed_legs": truck_battery_failed_legs}


def _initial_violations() -> dict[str, float]:
    return {
        "customer_coverage": 0.0,
        "customer_missing": 0.0,
        "customer_duplicate": 0.0,
        "truck_route": 0.0,
        "drone_mission": 0.0,
        "capacity": 0.0,
        "time_window": 0.0,
        "truck_battery": 0.0,
        "drone_battery": 0.0,
        "charging": 0.0,
        "sync": 0.0,
    }


def _node_type(node_id: int, depot_id: int, customer_ids: set[int], station_ids: set[int]) -> str:
    if node_id == depot_id:
        return "depot"
    if node_id in customer_ids:
        return "customer"
    if node_id in station_ids:
        return "station"
    return "unknown"


def _check_customer_coverage(
    instance: dict,
    truck_route: list[int],
    drone_tasks: list[dict],
    customer_ids: set[int],
    station_ids: set[int],
    violations: dict[str, float],
) -> None:
    depot_id = instance["depot"]["id"]
    truck_customers = [node for node in truck_route if node in customer_ids and node not in station_ids and node != depot_id]
    drone_customers: list[int] = []
    for task in drone_tasks:
        drone_customers.extend(_task_customers(task))
    all_served = truck_customers + drone_customers
    missing = customer_ids - set(all_served)
    duplicate = len(all_served) - len(set(all_served))
    violations["customer_missing"] += float(len(missing))
    violations["customer_duplicate"] += float(max(0, duplicate))
    violations["customer_coverage"] += violations["customer_missing"] + violations["customer_duplicate"]


def _route_positions(route: list[int]) -> dict[int, list[int]]:
    positions: dict[int, list[int]] = {}
    for idx, node_id in enumerate(route):
        positions.setdefault(node_id, []).append(idx)
    return positions


def _check_drone_tasks(instance: dict, tasks: list[dict], positions: dict[int, list[int]], violations: dict[str, float]) -> None:
    customers = {customer["id"]: customer for customer in instance["customers"]}
    station_ids = {station["id"] for station in instance["stations"]}
    last_recover_pos = -1
    sorted_tasks = sorted(tasks, key=lambda item: positions.get(int(item.get("launch", -1)), [-1])[0])
    for task in sorted_tasks:
        task = _normalize_drone_task(task)
        launch = int(task.get("launch", -1))
        recover = int(task.get("recover", -1))
        drone_route = _task_route(task)
        if launch not in positions or recover not in positions:
            violations["drone_mission"] += 1.0
            continue
        launch_pos = positions[launch][0]
        recover_pos = positions[recover][-1]
        if launch_pos >= recover_pos or launch_pos < last_recover_pos:
            violations["drone_mission"] += 1.0
        last_recover_pos = recover_pos
        if not drone_route or drone_route[0] != launch or drone_route[-1] != recover:
            violations["drone_mission"] += 1.0
        for node_id in drone_route[1:-1]:
            if node_id in station_ids:
                continue
            if node_id not in customers or not bool(customers[node_id].get("drone_eligible", False)):
                violations["drone_mission"] += 1.0


def _check_capacity(
    instance: dict,
    truck_route: list[int],
    drone_tasks: list[dict],
    customer_ids: set[int],
    station_ids: set[int],
    violations: dict[str, float],
) -> None:
    customers = {customer["id"]: customer for customer in instance["customers"]}
    served_ids = {node for node in truck_route if node in customer_ids and node not in station_ids}
    for task in drone_tasks:
        served_ids.update(_task_customers(task))
    total_demand = sum(float(customers[node_id]["demand"]) for node_id in served_ids if node_id in customers)
    truck_capacity = float(instance["truck"]["capacity"])
    if total_demand > truck_capacity:
        violations["capacity"] += total_demand - truck_capacity
    drone_capacity = float(instance["drone"]["capacity"])
    for task in drone_tasks:
        route_demand = sum(float(customers[node_id]["demand"]) for node_id in _task_customers(task) if node_id in customers)
        if route_demand > drone_capacity:
            violations["capacity"] += route_demand - drone_capacity


def _charging_plan_by_visit(plans: list[dict]) -> dict[tuple[int, int, int], dict]:
    mapped: dict[tuple[int, int, int], dict] = {}
    for plan in plans:
        position_after = int(plan.get("position_after", -1))
        station = int(plan.get("station", -1))
        visit_index = int(plan.get("visit_index", -1))
        mapped[(position_after, station, visit_index)] = plan
    return mapped


def _plans_for_vehicle(plans: list[dict], vehicle: str, task_index: int | None = None) -> list[dict]:
    filtered: list[dict] = []
    for plan in plans:
        plan_vehicle = str(plan.get("vehicle", "truck"))
        if plan_vehicle != vehicle:
            continue
        if task_index is not None and int(plan.get("task_index", -1)) != task_index:
            continue
        filtered.append(plan)
    return filtered


def _simulate_drone_task(
    instance: dict,
    task: dict,
    launch_departure_time: float,
    node_map: dict[int, dict],
    customer_ids: set[int],
    station_ids: set[int],
    charging_policy: str,
    charging_plan: list[dict],
    violations: dict[str, float],
) -> dict[str, Any]:
    task = _normalize_drone_task(task)
    launch = int(task["launch"])
    recover = int(task["recover"])
    drone_route = _task_route(task)
    if any(node_id not in node_map for node_id in drone_route):
        violations["drone_mission"] += 1.0
        return {
            "task": task,
            "launch": launch,
            "customer": _task_customers(task)[0] if _task_customers(task) else -1,
            "customers": _task_customers(task),
            "drone_route": drone_route,
            "recover": recover,
            "distance": 0.0,
            "arrival_recover": launch_departure_time,
            "time_window_violation": 0.0,
            "battery_violation": 0.0,
            "charging_count": 0,
            "charging_time": 0.0,
            "charging_trace": [],
        }

    drone = instance["drone"]
    customers = _task_customers(task)
    plan_by_visit = _charging_plan_by_visit(charging_plan)
    energy = float(drone["battery_capacity"])
    battery_violation = 0.0
    drone_distance = 0.0
    energy_used = 0.0
    charging_count = 0
    charging_time = 0.0
    charging_trace: list[dict[str, Any]] = []
    launch_time = launch_departure_time + float(drone["launch_time"])
    time = launch_time
    time_window_violation = 0.0
    customer_trace: list[dict[str, Any]] = []
    for index, node_id in enumerate(drone_route[1:], start=1):
        left_id = drone_route[index - 1]
        leg_distance = distance(node_map[left_id], node_map[node_id])
        drone_distance += leg_distance
        leg_energy = leg_distance * float(drone["consumption_rate"])
        energy -= leg_energy
        energy_used += leg_energy
        if energy < -1e-6:
            battery_violation += abs(energy)
            violations["drone_battery"] += abs(energy)
        arrival = time + leg_distance / max(float(drone["speed"]), 1e-9)
        time = arrival
        node = node_map[node_id]
        if node_id in customer_ids:
            service_start = max(time, float(node.get("ready_time", 0.0)))
            if service_start > float(node.get("due_time", math.inf)) + 1e-6:
                violation = service_start - float(node["due_time"])
                time_window_violation += violation
                violations["time_window"] += violation
            time = service_start + float(node.get("service_time", 0.0))
            customer_trace.append(
                {
                    "customer": node_id,
                    "arrival_customer": arrival,
                    "service_start": service_start,
                    "due_time": float(node.get("due_time", math.inf)),
                }
            )
        elif node_id in station_ids:
            plan = plan_by_visit.get((left_id, node_id, index))
            if plan is None:
                plan = plan_by_visit.get((left_id, node_id, -1))
            if plan is not None:
                arrival_energy = energy
                target = float(plan["target_energy"])
                if target < energy - 1e-6 or target > float(drone["battery_capacity"]) + 1e-6:
                    violations["charging"] += 1.0
                target = min(max(target, energy), float(drone["battery_capacity"]))
                duration = charge_time(
                    charging_policy,
                    energy,
                    target,
                    float(drone["battery_capacity"]),
                    float(instance["charging"]["linear_recharge_rate"]),
                    list(instance["charging"]["nonlinear_segments"]),
                )
                time += duration
                energy = target
                charging_count += 1
                charging_time += duration
                charging_trace.append(
                    {
                        "vehicle": "drone",
                        "station": node_id,
                        "arrival_energy": arrival_energy,
                        "target_energy": target,
                        "charging_time": duration,
                        "policy": charging_policy,
                    }
                )
    arrival_recover = time + float(drone["recover_time"])
    first_customer = customer_trace[0] if customer_trace else {}
    return {
        "launch": launch,
        "customer": customers[0] if customers else -1,
        "customers": customers,
        "drone_route": drone_route,
        "recover": recover,
        "launch_time": launch_time,
        "arrival_customer": float(first_customer.get("arrival_customer", launch_time)),
        "service_start": float(first_customer.get("service_start", launch_time)),
        "due_time": float(first_customer.get("due_time", math.inf)),
        "arrival_recover": arrival_recover,
        "distance": drone_distance,
        "energy_used": energy_used,
        "time_window_violation": time_window_violation,
        "battery_violation": battery_violation,
        "charging_count": charging_count,
        "charging_time": charging_time,
        "charging_trace": charging_trace,
        "customer_trace": customer_trace,
    }


def _normalize_drone_task(task: dict) -> dict:
    normalized = dict(task)
    launch = int(normalized.get("launch", -1))
    recover = int(normalized.get("recover", -1))
    if "drone_route" in normalized:
        normalized["drone_route"] = [int(node_id) for node_id in normalized["drone_route"]]
    else:
        customers = _task_customers(normalized)
        normalized["drone_route"] = [launch] + customers + [recover]
    if "customers" not in normalized:
        normalized["customers"] = [node_id for node_id in normalized["drone_route"][1:-1]]
    if "customer" not in normalized and normalized["customers"]:
        normalized["customer"] = int(normalized["customers"][0])
    return normalized


def _task_customers(task: dict) -> list[int]:
    if "customers" in task:
        return [int(node_id) for node_id in task.get("customers", [])]
    if "customer" in task:
        return [int(task.get("customer", -1))]
    route = [int(node_id) for node_id in task.get("drone_route", [])]
    return [node_id for node_id in route[1:-1]]


def _task_route(task: dict) -> list[int]:
    normalized = _normalize_drone_task(task)
    return [int(node_id) for node_id in normalized["drone_route"]]


def _task_key(task: dict) -> tuple[int, tuple[int, ...], int]:
    normalized = _normalize_drone_task(task)
    return int(normalized["launch"]), tuple(_task_route(normalized)[1:-1]), int(normalized["recover"])


def _build_diagnostics(
    instance: dict,
    trace: dict[str, Any],
    violations: dict[str, float],
    truck_leg_count: int,
    truck_battery_failed_legs: list[str],
) -> dict[str, Any]:
    customer_count = max(1, len(instance["customers"]))
    total_demand = max(1.0, sum(float(customer["demand"]) for customer in instance["customers"]))

    truck_tw_failed = [
        str(row["node"])
        for row in trace["truck"]
        if row["node_type"] == "customer" and float(row["time_window_violation"]) > 1e-6
    ]
    drone_tw_failed = [
        str(customer_id)
        for row in trace["drone_tasks"]
        for customer_id in row.get("customers", [row.get("customer", -1)])
        if float(row.get("time_window_violation", 0.0)) > 1e-6
    ]
    failed_customers = set(truck_tw_failed + drone_tw_failed)

    customer_coverage_rate = _rate_from_violation(violations["customer_coverage"], customer_count)
    time_window_feasibility_rate = 100.0 * (customer_count - len(failed_customers)) / customer_count
    truck_battery_feasibility_rate = 100.0 if truck_leg_count == 0 else 100.0 * (
        truck_leg_count - len(truck_battery_failed_legs)
    ) / truck_leg_count
    drone_task_count = len(trace["drone_tasks"])
    drone_failed_tasks = [
        "->".join(str(node_id) for node_id in row.get("drone_route", [row.get("launch"), row.get("customer"), row.get("recover")]))
        for row in trace["drone_tasks"]
        if float(row.get("battery_violation", 0.0)) > 1e-6 or float(row.get("time_window_violation", 0.0)) > 1e-6
    ]
    drone_battery_failed_count = sum(1 for row in trace["drone_tasks"] if float(row.get("battery_violation", 0.0)) > 1e-6)
    drone_battery_feasibility_rate = 100.0 if drone_task_count == 0 else 100.0 * (
        drone_task_count - drone_battery_failed_count
    ) / drone_task_count
    capacity_feasibility_rate = _rate_from_violation(violations["capacity"], total_demand)
    sync_feasibility_rate = 100.0 if violations["sync"] <= 1e-6 else 0.0

    feasibility = {
        "customer_coverage_rate": _clamp_rate(customer_coverage_rate),
        "time_window_feasibility_rate": _clamp_rate(time_window_feasibility_rate),
        "truck_battery_feasibility_rate": _clamp_rate(truck_battery_feasibility_rate),
        "drone_battery_feasibility_rate": _clamp_rate(drone_battery_feasibility_rate),
        "capacity_feasibility_rate": _clamp_rate(capacity_feasibility_rate),
        "sync_feasibility_rate": _clamp_rate(sync_feasibility_rate),
    }
    feasibility["feasibility_rate"] = _clamp_rate(sum(feasibility.values()) / len(feasibility))
    feasibility["total_violation"] = sum(float(value) for value in violations.values())

    diagnostics = {
        "time_window_failed_nodes": sorted(failed_customers, key=lambda value: int(value)),
        "truck_time_window_failed_nodes": truck_tw_failed,
        "drone_time_window_failed_nodes": drone_tw_failed,
        "truck_battery_failed_legs": truck_battery_failed_legs,
        "drone_failed_tasks": drone_failed_tasks,
    }
    return {"feasibility": feasibility, "diagnostics": diagnostics}


def _rate_from_violation(violation: float, denominator: float) -> float:
    return 100.0 * max(0.0, 1.0 - float(violation) / max(float(denominator), 1e-9))


def _clamp_rate(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
