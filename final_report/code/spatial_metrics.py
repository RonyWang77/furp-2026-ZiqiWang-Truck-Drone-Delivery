"""Spatial quality metrics for petal-shaped Truck-Drone routes."""

from __future__ import annotations

import math
from typing import Any


PETAL_WEIGHTS = {
    "route_compactness": 1.0,
    "sector_coherence": 0.5,
    "crossing_count": 50.0,
    "route_overlap_penalty": 10.0,
}


def analyze_spatial_quality(instance: dict, solution: dict[str, Any]) -> dict[str, float]:
    node_map = {int(node["id"]): node for node in instance["nodes"]}
    customer_ids = {int(customer["id"]) for customer in instance["customers"]}
    station_ids = {int(station["id"]) for station in instance["stations"]}
    depot_id = int(instance["depot"]["id"])
    routes = solution.get("truck_routes") or [solution.get("truck_route", [])]
    clean_routes = [
        [int(node_id) for node_id in route if int(node_id) in node_map and int(node_id) not in station_ids]
        for route in routes
    ]
    service_routes = [list(route) for route in clean_routes]
    for task in solution.get("drone_tasks", []):
        route_index = int(task.get("route_index", 0))
        if 0 <= route_index < len(service_routes):
            task_customers = [int(cid) for cid in task.get("customers", []) if int(cid) in customer_ids]
            if not task_customers and task.get("drone_route"):
                task_customers = [int(node_id) for node_id in task["drone_route"][1:-1] if int(node_id) in customer_ids]
            service_routes[route_index].extend(task_customers)

    compactness_values = [_route_compactness(route, node_map, customer_ids) for route in service_routes]
    sector_values = [_route_sector_span(route, node_map, customer_ids, depot_id) for route in service_routes]
    radial_values = [_route_radial_consistency(route, node_map, customer_ids, depot_id) for route in service_routes]
    crossing_count = _crossing_count(clean_routes, node_map)
    overlap_penalty = _route_overlap_penalty(service_routes, node_map, customer_ids, depot_id)

    route_compactness = _avg(compactness_values)
    sector_coherence = _avg(sector_values)
    depot_radial_consistency = _avg(radial_values)
    petal_score = (
        PETAL_WEIGHTS["route_compactness"] * route_compactness
        + PETAL_WEIGHTS["sector_coherence"] * sector_coherence
        + PETAL_WEIGHTS["crossing_count"] * crossing_count
        + PETAL_WEIGHTS["route_overlap_penalty"] * overlap_penalty
        + 5.0 * depot_radial_consistency
    )
    return {
        "route_compactness": float(route_compactness),
        "sector_coherence": float(sector_coherence),
        "crossing_count": float(crossing_count),
        "depot_radial_consistency": float(depot_radial_consistency),
        "route_overlap_penalty": float(overlap_penalty),
        "petal_score": float(petal_score),
    }


def sweep_customer_order(instance: dict, reverse: bool = False) -> list[int]:
    depot = instance["depot"]
    return [
        int(customer["id"])
        for customer in sorted(
            instance["customers"],
            key=lambda customer: (
                -_angle(depot, customer) if reverse else _angle(depot, customer),
                _dist(depot, customer),
                float(customer.get("due_time", math.inf)),
            ),
        )
    ]


def cluster_customer_order(instance: dict, cluster_count: int | None = None, then_time_window: bool = False) -> list[int]:
    clusters = angle_clusters(instance, cluster_count)
    ordered: list[int] = []
    customers = {int(customer["id"]): customer for customer in instance["customers"]}
    depot = instance["depot"]
    for _, customer_ids in sorted(clusters.items()):
        rows = [customers[cid] for cid in customer_ids]
        if then_time_window:
            rows.sort(key=lambda row: (float(row.get("due_time", math.inf)), float(row.get("ready_time", 0.0)), int(row["id"])))
        else:
            rows.sort(key=lambda row: (_angle(depot, row), _dist(depot, row), int(row["id"])))
        ordered.extend(int(row["id"]) for row in rows)
    return ordered


def angle_clusters(instance: dict, cluster_count: int | None = None) -> dict[int, list[int]]:
    customers = list(instance["customers"])
    if not customers:
        return {}
    k = int(cluster_count or max(1, min(12, math.ceil(len(customers) / 5))))
    depot = instance["depot"]
    rows = sorted(customers, key=lambda row: (_angle(depot, row), _dist(depot, row)))
    clusters: dict[int, list[int]] = {idx: [] for idx in range(k)}
    for pos, customer in enumerate(rows):
        clusters[min(k - 1, int(pos * k / len(rows)))].append(int(customer["id"]))
    return clusters


def cluster_bias(instance: dict, max_vehicle_count: int) -> dict[int, int]:
    clusters = angle_clusters(instance, max_vehicle_count)
    bias: dict[int, int] = {}
    for cluster_idx, customer_ids in clusters.items():
        for customer_id in customer_ids:
            bias[int(customer_id)] = int(cluster_idx) % max(1, int(max_vehicle_count))
    return bias


def route_crossing_customers(instance: dict, solution: dict[str, Any]) -> list[int]:
    node_map = {int(node["id"]): node for node in instance["nodes"]}
    customer_ids = {int(customer["id"]) for customer in instance["customers"]}
    routes = solution.get("truck_routes") or [solution.get("truck_route", [])]
    clean_routes = [[int(node_id) for node_id in route if int(node_id) in node_map] for route in routes]
    involved: set[int] = set()
    segments = []
    for route_index, route in enumerate(clean_routes):
        for pos in range(len(route) - 1):
            a, b = route[pos], route[pos + 1]
            if a == b:
                continue
            segments.append((route_index, a, b))
    for idx, left in enumerate(segments):
        for right in segments[idx + 1 :]:
            if left[0] == right[0] and ({left[1], left[2]} & {right[1], right[2]}):
                continue
            if _share_endpoint(left, right):
                continue
            if _segments_intersect(node_map[left[1]], node_map[left[2]], node_map[right[1]], node_map[right[2]]):
                involved.update(node for node in [left[1], left[2], right[1], right[2]] if node in customer_ids)
    return sorted(involved)


def _route_compactness(route: list[int], node_map: dict[int, dict], customer_ids: set[int]) -> float:
    points = [node_map[node_id] for node_id in route if node_id in customer_ids]
    if len(points) <= 1:
        return 0.0
    cx = sum(float(point["x"]) for point in points) / len(points)
    cy = sum(float(point["y"]) for point in points) / len(points)
    return sum(math.hypot(float(point["x"]) - cx, float(point["y"]) - cy) for point in points) / len(points)


def _route_sector_span(route: list[int], node_map: dict[int, dict], customer_ids: set[int], depot_id: int) -> float:
    angles = [_angle(node_map[depot_id], node_map[node_id]) for node_id in route if node_id in customer_ids]
    if len(angles) <= 1:
        return 0.0
    angles.sort()
    gaps = [angles[idx + 1] - angles[idx] for idx in range(len(angles) - 1)]
    gaps.append((angles[0] + 2.0 * math.pi) - angles[-1])
    return 2.0 * math.pi - max(gaps)


def _route_radial_consistency(route: list[int], node_map: dict[int, dict], customer_ids: set[int], depot_id: int) -> float:
    distances = [_dist(node_map[depot_id], node_map[node_id]) for node_id in route if node_id in customer_ids]
    if len(distances) <= 2:
        return 0.0
    peak = max(range(len(distances)), key=lambda idx: distances[idx])
    violation = 0.0
    for idx in range(peak):
        violation += max(0.0, distances[idx] - distances[idx + 1])
    for idx in range(peak, len(distances) - 1):
        violation += max(0.0, distances[idx + 1] - distances[idx])
    return violation / max(1, len(distances) - 1)


def _crossing_count(routes: list[list[int]], node_map: dict[int, dict]) -> int:
    segments = []
    for route_index, route in enumerate(routes):
        for pos in range(len(route) - 1):
            a, b = route[pos], route[pos + 1]
            if a in node_map and b in node_map and a != b:
                segments.append((route_index, a, b))
    count = 0
    for idx, left in enumerate(segments):
        for right in segments[idx + 1 :]:
            if _share_endpoint(left, right):
                continue
            if _segments_intersect(node_map[left[1]], node_map[left[2]], node_map[right[1]], node_map[right[2]]):
                count += 1
    return count


def _route_overlap_penalty(routes: list[list[int]], node_map: dict[int, dict], customer_ids: set[int], depot_id: int) -> float:
    route_infos = []
    for route in routes:
        customers = [node_id for node_id in route if node_id in customer_ids]
        if not customers:
            continue
        angles = [_angle(node_map[depot_id], node_map[node_id]) for node_id in customers]
        centroid_x = sum(float(node_map[node_id]["x"]) for node_id in customers) / len(customers)
        centroid_y = sum(float(node_map[node_id]["y"]) for node_id in customers) / len(customers)
        route_infos.append((min(angles), max(angles), centroid_x, centroid_y))
    penalty = 0.0
    for idx, left in enumerate(route_infos):
        for right in route_infos[idx + 1 :]:
            angle_overlap = max(0.0, min(left[1], right[1]) - max(left[0], right[0]))
            centroid_distance = math.hypot(left[2] - right[2], left[3] - right[3])
            if angle_overlap > 0.2:
                penalty += angle_overlap / max(1.0, centroid_distance)
    return penalty


def _segments_intersect(a: dict, b: dict, c: dict, d: dict) -> bool:
    p1 = (float(a["x"]), float(a["y"]))
    p2 = (float(b["x"]), float(b["y"]))
    p3 = (float(c["x"]), float(c["y"]))
    p4 = (float(d["x"]), float(d["y"]))
    return _ccw(p1, p3, p4) != _ccw(p2, p3, p4) and _ccw(p1, p2, p3) != _ccw(p1, p2, p4)


def _ccw(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _share_endpoint(left: tuple[int, int, int], right: tuple[int, int, int]) -> bool:
    return bool({left[1], left[2]} & {right[1], right[2]})


def _angle(depot: dict, node: dict) -> float:
    angle = math.atan2(float(node["y"]) - float(depot["y"]), float(node["x"]) - float(depot["x"]))
    return angle if angle >= 0.0 else angle + 2.0 * math.pi


def _dist(left: dict, right: dict) -> float:
    return math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"]))


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
