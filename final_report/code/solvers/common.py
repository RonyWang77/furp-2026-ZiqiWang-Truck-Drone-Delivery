"""Shared construction helpers for first-stage Truck-Drone solvers."""

from __future__ import annotations

import math
import random
from typing import Any

try:
    from ..charging import target_energy
    from ..route_simulator import distance
except ImportError:  # pragma: no cover
    from charging import target_energy
    from route_simulator import distance


def sorted_customer_ids(instance: dict) -> list[int]:
    return [int(customer["id"]) for customer in sorted(instance["customers"], key=lambda item: int(item["id"]))]


def nearest_neighbor_customer_ids(instance: dict, seed: int | None = None) -> list[int]:
    rng = random.Random(seed)
    remaining = sorted_customer_ids(instance)
    node_map = {node["id"]: node for node in instance["nodes"]}
    current = int(instance["depot"]["id"])
    order: list[int] = []
    while remaining:
        best_distance = min(distance(node_map[current], node_map[cid]) for cid in remaining)
        ties = [cid for cid in remaining if abs(distance(node_map[current], node_map[cid]) - best_distance) <= 1e-9]
        chosen = rng.choice(ties)
        order.append(chosen)
        remaining.remove(chosen)
        current = chosen
    return order


def randomized_customer_ids(instance: dict, seed: int | None = None) -> list[int]:
    ids = sorted_customer_ids(instance)
    random.Random(seed).shuffle(ids)
    return ids


def build_truck_drone_solution(
    instance: dict,
    customer_order: list[int],
    charging_policy: str,
    drone_stride: int,
) -> dict[str, Any]:
    drone_customers = _choose_drone_customers(instance, customer_order, max(2, drone_stride))
    truck_route = [int(instance["depot"]["id"])] + [cid for cid in customer_order if cid not in drone_customers] + [
        int(instance["depot"]["id"])
    ]
    drone_tasks = _build_drone_tasks(truck_route, customer_order, drone_customers)
    solution = {
        "truck_route": truck_route,
        "drone_tasks": drone_tasks,
        "charging_plan": [],
        "metadata": {"construction": "direct_solver_decision"},
    }
    return add_charging_decisions(instance, solution, charging_policy)


def add_charging_decisions(instance: dict, solution: dict[str, Any], charging_policy: str) -> dict[str, Any]:
    route = list(solution["truck_route"])
    if len(route) < 2:
        return solution
    node_map = {node["id"]: node for node in instance["nodes"]}
    stations = list(instance["stations"])
    battery_capacity = float(instance["truck"]["battery_capacity"])
    consumption_rate = float(instance["truck"]["consumption_rate"])
    safety_margin = float(instance["charging"].get("safety_margin", 0.0))
    energy = battery_capacity
    new_route = [route[0]]
    plans: list[dict[str, Any]] = []

    for next_node in route[1:]:
        current = new_route[-1]
        leg_energy = _energy_required(node_map[current], node_map[next_node], consumption_rate)
        escape_energy = _minimum_escape_energy(next_node, instance, node_map, consumption_rate)
        should_charge_before_next = energy + 1e-9 < leg_energy or energy - leg_energy < escape_energy + safety_margin
        if should_charge_before_next and int(current) not in {int(station["id"]) for station in stations}:
            station_choice = _best_station(
                current,
                next_node,
                energy,
                stations,
                node_map,
                battery_capacity,
                consumption_rate,
                extra_required_after_next=escape_energy + safety_margin,
            )
            if station_choice is not None:
                station_id, arrival_energy, required_after_charge = station_choice
                new_route.append(station_id)
                target = target_energy(
                    charging_policy,
                    arrival_energy,
                    battery_capacity,
                    required_after_charge,
                    safety_margin,
                )
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
                leg_energy = _energy_required(node_map[current], node_map[next_node], consumption_rate)
        energy -= leg_energy
        new_route.append(next_node)

    updated = dict(solution)
    updated["truck_route"] = new_route
    updated["charging_plan"] = plans
    return updated


def solution_cost_tuple(result: dict[str, Any]) -> tuple[int, float, float]:
    return (
        0 if result["feasible"] else 1,
        int(result.get("vehicle_count", 1)),
        float(result.get("total_distance", math.inf)) + float(result.get("charging_time", 0.0)),
    )


def _choose_drone_customers(instance: dict, order: list[int], stride: int) -> set[int]:
    customers = {int(customer["id"]): customer for customer in instance["customers"]}
    chosen: set[int] = set()
    for idx, customer_id in enumerate(order):
        if idx == 0 or idx == len(order) - 1:
            continue
        customer = customers[customer_id]
        if bool(customer.get("drone_eligible", False)) and idx % stride == stride - 1:
            chosen.add(customer_id)
    return chosen


def _build_drone_tasks(truck_route: list[int], customer_order: list[int], drone_customers: set[int]) -> list[dict[str, int]]:
    tasks: list[dict[str, int]] = []
    for customer_id in customer_order:
        if customer_id not in drone_customers:
            continue
        original_pos = customer_order.index(customer_id)
        launch = _nearest_truck_node_before(customer_order, truck_route, original_pos)
        recover = _nearest_truck_node_after(customer_order, truck_route, original_pos)
        if launch != recover:
            tasks.append({"launch": launch, "customer": customer_id, "recover": recover})
    return tasks


def _nearest_truck_node_before(order: list[int], truck_route: list[int], pos: int) -> int:
    truck_set = set(truck_route)
    for idx in range(pos - 1, -1, -1):
        if order[idx] in truck_set:
            return order[idx]
    return truck_route[0]


def _nearest_truck_node_after(order: list[int], truck_route: list[int], pos: int) -> int:
    truck_set = set(truck_route)
    for idx in range(pos + 1, len(order)):
        if order[idx] in truck_set:
            return order[idx]
    return truck_route[-1]


def _best_station(
    current: int,
    next_node: int,
    energy: float,
    stations: list[dict],
    node_map: dict[int, dict],
    battery_capacity: float,
    consumption_rate: float,
    extra_required_after_next: float = 0.0,
) -> tuple[int, float, float] | None:
    feasible: list[tuple[float, int, float, float]] = []
    direct_distance = distance(node_map[current], node_map[next_node])
    for station in stations:
        station_id = int(station["id"])
        to_station = _energy_required(node_map[current], node_map[station_id], consumption_rate)
        station_to_next = _energy_required(node_map[station_id], node_map[next_node], consumption_rate)
        required_after_charge = station_to_next + extra_required_after_next
        if to_station <= energy + 1e-9 and required_after_charge <= battery_capacity + 1e-9:
            detour = distance(node_map[current], node_map[station_id]) + distance(node_map[station_id], node_map[next_node]) - direct_distance
            feasible.append((detour, station_id, energy - to_station, required_after_charge))
    if not feasible:
        return None
    _, station_id, arrival_energy, required_after_charge = min(feasible, key=lambda item: item[0])
    return station_id, arrival_energy, required_after_charge


def _energy_required(left: dict, right: dict, consumption_rate: float) -> float:
    return distance(left, right) * consumption_rate


def _minimum_escape_energy(node_id: int, instance: dict, node_map: dict[int, dict], consumption_rate: float) -> float:
    escape_nodes = [instance["depot"]] + list(instance["stations"])
    return min(_energy_required(node_map[node_id], node, consumption_rate) for node in escape_nodes)
