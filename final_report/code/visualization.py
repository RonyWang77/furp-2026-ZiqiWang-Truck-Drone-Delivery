"""Matplotlib visualization for Truck-Drone EVRPTW-NL solutions."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def plot_solution(instance: dict, result: dict[str, Any], save_path: str | Path | None = None, show: bool = False) -> None:
    import matplotlib.pyplot as plt

    solution = result.get("solution", result)
    node_map = {node["id"]: node for node in instance["nodes"]}
    depot = instance["depot"]
    customers = instance["customers"]
    stations = instance["stations"]

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.scatter([depot["x"]], [depot["y"]], marker="s", c="black", s=90, label="Depot")
    ax.text(depot["x"], depot["y"], str(depot["id"]), fontsize=9)

    if customers:
        ax.scatter([c["x"] for c in customers], [c["y"] for c in customers], c="#1f77b4", s=45, label="Customers")
        for customer in customers:
            ax.text(customer["x"], customer["y"], str(customer["id"]), fontsize=8)

    if stations:
        ax.scatter([s["x"] for s in stations], [s["y"] for s in stations], marker="^", c="#2ca02c", s=60, label="Stations")
        for station in stations:
            ax.text(station["x"], station["y"], str(station["id"]), fontsize=8)

    routes = solution.get("truck_routes", [solution.get("truck_route", [])])
    for idx, route in enumerate(routes, start=1):
        if len(route) >= 2:
            xs = [node_map[node_id]["x"] for node_id in route if node_id in node_map]
            ys = [node_map[node_id]["y"] for node_id in route if node_id in node_map]
            ax.plot(xs, ys, "-o", linewidth=2, label=f"Truck route {idx}")

    for idx, task in enumerate(solution.get("drone_tasks", []), start=1):
        drone_route = task.get("drone_route")
        if drone_route is None:
            drone_route = [task["launch"]] + task.get("customers", [task.get("customer")]) + [task["recover"]]
        points = [node_map.get(int(node_id)) for node_id in drone_route]
        if any(point is None for point in points):
            continue
        ax.plot(
            [point["x"] for point in points if point is not None],
            [point["y"] for point in points if point is not None],
            "--",
            c="#ff7f0e",
            linewidth=1.6,
            label="Drone task" if idx == 1 else None,
        )

    ax.set_title(f"{instance['name']} - {result.get('method', 'solution')}")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()

    if save_path is not None:
        output = Path(save_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=180)
    if show:
        plt.show()
    else:
        plt.close(fig)
