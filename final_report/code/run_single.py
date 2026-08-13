"""Run one Truck-Drone EVRPTW-NL method on one generated instance."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .config import ROOT, apply_overrides, load_config, resolve_path
    from .instance_builder import build_instance, load_generated_instance, save_instance
    from .visualization import plot_solution
    from .solvers.solve_alns import solve as solve_alns
    from .solvers.solve_ga import solve as solve_ga
    from .solvers.solve_hybrid import solve as solve_hybrid
    from .solvers.solve_truck_only_ortools import solve as solve_truck_ortools
    from .solvers.solve_truck_only_pyvrp import solve as solve_truck_pyvrp
except ImportError:  # pragma: no cover
    from config import ROOT, apply_overrides, load_config, resolve_path
    from instance_builder import build_instance, load_generated_instance, save_instance
    from visualization import plot_solution
    from solvers.solve_alns import solve as solve_alns
    from solvers.solve_ga import solve as solve_ga
    from solvers.solve_hybrid import solve as solve_hybrid
    from solvers.solve_truck_only_ortools import solve as solve_truck_ortools
    from solvers.solve_truck_only_pyvrp import solve as solve_truck_pyvrp


SOLVERS = {
    "ga": solve_ga,
    "ga_td": solve_ga,
    "ga_td_petal": solve_ga,
    "alns": solve_alns,
    "alns_td": solve_alns,
    "alns_td_petal": solve_alns,
    "alns_core": solve_alns,
    "alns_vehicle": solve_alns,
    "alns_petal": solve_alns,
    "alns_drone": solve_alns,
    "alns_charging": solve_alns,
    "alns_full": solve_alns,
    "hybrid": solve_hybrid,
    "hybrid_selector": solve_hybrid,
    "hybrid_refine": solve_hybrid,
    "hybrid_topk": solve_hybrid,
    "hybrid_preserve": solve_hybrid,
    "hybrid_periodic": solve_hybrid,
    "hybrid_stagnation": solve_hybrid,
    "hybrid_diverse_topk": solve_hybrid,
    "hybrid_diverse_stagnation": solve_hybrid,
    "truck_ortools": solve_truck_ortools,
    "truck_pyvrp": solve_truck_pyvrp,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/debug_small.yaml")
    parser.add_argument("--instance", default=None)
    parser.add_argument("--customers", type=int, default=None)
    parser.add_argument("--method", choices=sorted(SOLVERS), default="ga")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--charging-policy", choices=["LFC", "LPC", "NFC", "NPC"], default=None)
    parser.add_argument("--instance-file", default=None)
    parser.add_argument("--save-plot", action="store_true")
    parser.add_argument("--show-plot", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--alns-profile", choices=["alns_core", "alns_vehicle", "alns_petal", "alns_drone", "alns_charging", "alns_full"], default=None)
    args = parser.parse_args()

    config = apply_overrides(load_config(args.config), args)
    charging_policy = config.get("charging_policies", ["NPC"])[0]

    if args.instance_file:
        instance = load_generated_instance(args.instance_file)
    else:
        source_instance = config["instances"][0]
        customer_count = int(config["customer_counts"][0])
        instance = build_instance(config, source_instance, customer_count)
        save_instance(instance, resolve_path(config.get("output_instance_dir", "generated_instances")))

    solver_kwargs = _solver_kwargs(config, args.method, int(instance["customer_count"]))
    if args.alns_profile:
        solver_kwargs["alns_profile"] = args.alns_profile
    result = SOLVERS[args.method](instance, charging_policy=charging_policy, seed=config.get("seed", 1987), **solver_kwargs)
    print_result(result, diagnose=args.diagnose)

    if args.save_plot or args.show_plot:
        figure_path = ROOT / "figures" / f"{result['instance']}_{result['method']}_{charging_policy}.png"
        plot_solution(instance, result, save_path=figure_path if args.save_plot else None, show=args.show_plot)
        if args.save_plot:
            print(f"figure: {figure_path}")


def print_result(result: dict, diagnose: bool = False) -> None:
    solution = result["solution"]
    print(f"instance: {result['instance']}")
    print(f"method: {result['method']}")
    print(f"charging_policy: {result['charging_policy']}")
    print("truck_routes:")
    for idx, route in enumerate(solution.get("truck_routes", [solution.get("truck_route", [])]), start=1):
        print(f"  Vehicle {idx}: {route_to_text(route)}")
    print("drone_tasks:")
    if solution.get("drone_tasks"):
        for idx, task in enumerate(solution["drone_tasks"], start=1):
            route = task.get("drone_route")
            if route is None:
                route = [task["launch"]] + task.get("customers", [task.get("customer")]) + [task["recover"]]
            print(f"  Task {idx}: route {task.get('route_index', 0)} | {route_to_text(route)}")
    else:
        print("  none")
    print("charging_plan:")
    if solution.get("charging_plan"):
        for plan in solution["charging_plan"]:
            print(
                "  "
                f"route {plan.get('route_index', 0)} after {plan['position_after']} charge at {plan['station']} "
                f"to {plan['target_energy']:.2f} ({plan['charging_policy']})"
            )
    else:
        print("  none")
    print(f"feasible: {result['feasible']}")
    print(f"vehicle_count: {result['vehicle_count']}")
    print(f"total_distance: {result['total_distance']:.3f}")
    print(f"completion_time: {result['completion_time']:.3f}")
    print(f"waiting_time: {result['waiting_time']:.3f}")
    print(f"charging_count: {result['charging_count']}")
    print(f"charging_time: {result['charging_time']:.3f}")
    print(f"petal_score: {result.get('petal_score', 0.0):.3f}")
    print(f"crossing_count: {result.get('crossing_count', 0.0):.0f}")
    print(f"route_compactness: {result.get('route_compactness', 0.0):.3f}")
    print(f"sector_coherence: {result.get('sector_coherence', 0.0):.3f}")
    print(f"runtime_seconds: {result['runtime_seconds']:.3f}")
    if result.get("hybrid_details"):
        print("hybrid_details:")
        for key, value in result["hybrid_details"].items():
            if key in {"candidate_details", "periodic_details", "stagnation_details"} and isinstance(value, list):
                print(f"  {key}: {len(value)} candidates")
                continue
            if isinstance(value, float):
                print(f"  {key}: {value:.6g}")
            else:
                print(f"  {key}: {value}")
    print("feasibility_rates:")
    for key, value in result.get("feasibility", {}).items():
        if key == "total_violation":
            print(f"  {key}: {value:.6g}")
        else:
            print(f"  {key}: {value:.2f}%")
    print("violations:")
    for key, value in result["violations"].items():
        print(f"  {key}: {value:.6g}")
    if diagnose:
        print_diagnostics(result)


def route_to_text(route: list[int]) -> str:
    return " ---> ".join(str(node) for node in route)


def _solver_kwargs(config: dict, method: str, customer_count: int) -> dict:
    kwargs: dict = {}
    budget = _method_time_budget(config, method, customer_count)
    if budget is not None:
        kwargs["time_budget_seconds"] = budget
    method_key = str(method).lower()
    if method_key == "hybrid_selector":
        kwargs["hybrid_mode"] = "selector"
    elif method_key == "hybrid_topk":
        kwargs["hybrid_mode"] = "topk"
    elif method_key == "hybrid_preserve":
        kwargs["hybrid_mode"] = "preserve"
    elif method_key == "hybrid_periodic":
        kwargs["hybrid_mode"] = "periodic"
    elif method_key == "hybrid_stagnation":
        kwargs["hybrid_mode"] = "stagnation"
    elif method_key == "hybrid_diverse_topk":
        kwargs["hybrid_mode"] = "diverse_topk"
        kwargs["comparison_mode"] = "paper_cost_priority"
    elif method_key == "hybrid_diverse_stagnation":
        kwargs["hybrid_mode"] = "diverse_stagnation"
        kwargs["comparison_mode"] = "paper_cost_priority"
    elif method_key in {"hybrid", "hybrid_refine"}:
        kwargs["hybrid_mode"] = "refine"
    if method_key in {"alns_core", "alns_vehicle", "alns_petal", "alns_drone", "alns_charging", "alns_full"}:
        kwargs["alns_profile"] = method_key
        kwargs["method_label"] = method_key
    elif "alns_profile" in config and "alns" in method_key:
        kwargs["alns_profile"] = config["alns_profile"]
        kwargs["method_label"] = f"alns_{config['alns_profile']}"
    return kwargs


def _method_time_budget(config: dict, method: str, customer_count: int) -> float | None:
    method_key = str(method).lower()
    if "time_budget_seconds" in config:
        return float(config["time_budget_seconds"])
    if "alns_time_budget_seconds" in config and "alns" in method_key:
        return float(config["alns_time_budget_seconds"])
    if "ga_time_budget_seconds" in config and "ga" in method_key:
        return float(config["ga_time_budget_seconds"])
    if "petal_time_budget_seconds" in config and ("petal" in method_key or customer_count >= 25):
        return float(config["petal_time_budget_seconds"])
    return None


def print_diagnostics(result: dict) -> None:
    print("diagnostics:")
    diagnostics = result.get("diagnostics", {})
    print(f"  time_window_failed_nodes: {', '.join(diagnostics.get('time_window_failed_nodes', [])) or 'none'}")
    print(f"  truck_battery_failed_legs: {', '.join(diagnostics.get('truck_battery_failed_legs', [])) or 'none'}")
    print(f"  drone_failed_tasks: {', '.join(diagnostics.get('drone_failed_tasks', [])) or 'none'}")

    trace = result.get("trace", {})
    print("truck_node_trace:")
    print("  route node type arrival ready due start depart arr_energy dep_energy wait charge sync tw_violation")
    for row in trace.get("truck", []):
        print(
            "  "
            f"{row.get('route_index', 0)} {row['node']} {row['node_type']} "
            f"{row['arrival_time']:.2f} {row['ready_time']:.2f} {row['due_time']:.2f} "
            f"{row['service_start']:.2f} {row['departure_time']:.2f} "
            f"{row['arrival_energy']:.2f} {row['departure_energy']:.2f} "
            f"{row['waiting_time']:.2f} {row['charging_time']:.2f} {row['sync_wait']:.2f} "
            f"{row['time_window_violation']:.2f}"
        )

    print("drone_task_trace:")
    if not trace.get("drone_tasks"):
        print("  none")
    for row in trace.get("drone_tasks", []):
        drone_route = row.get("drone_route", [row.get("launch"), row.get("customer"), row.get("recover")])
        print(
            "  "
            f"route={row.get('route_index', 0)} | {route_to_text(drone_route)} | "
            f"launch={row['launch_time']:.2f}, arrival_customer={row['arrival_customer']:.2f}, "
            f"service_start={row['service_start']:.2f}, due={row['due_time']:.2f}, "
            f"arrival_recover={row['arrival_recover']:.2f}, energy={row['energy_used']:.2f}, "
            f"charge={row.get('charging_time', 0.0):.2f}, "
            f"tw_violation={row['time_window_violation']:.2f}, battery_violation={row['battery_violation']:.2f}"
        )


if __name__ == "__main__":
    main()
