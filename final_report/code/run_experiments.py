"""Batch experiments for first-stage Truck-Drone EVRPTW-NL methods."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
from datetime import datetime
from pathlib import Path

try:
    from .config import ROOT, load_config, resolve_path
    from .instance_builder import build_instance, save_instance
    from .run_single import SOLVERS, route_to_text
    from .visualization import plot_solution
except ImportError:  # pragma: no cover
    from config import ROOT, load_config, resolve_path
    from instance_builder import build_instance, save_instance
    from run_single import SOLVERS, route_to_text
    from visualization import plot_solution


SUMMARY_FIELDS = [
    "instance",
    "source_instance",
    "customer_count",
    "seed",
    "method",
    "charging_policy",
    "truck_route",
    "truck_routes",
    "drone_tasks",
    "feasible",
    "vehicle_count",
    "truck_distance",
    "drone_distance",
    "total_distance",
    "completion_time",
    "waiting_time",
    "truck_waiting_time",
    "drone_waiting_time",
    "charging_count",
    "charging_time",
    "petal_score",
    "crossing_count",
    "route_compactness",
    "sector_coherence",
    "depot_radial_consistency",
    "runtime_seconds",
    "feasibility_rate",
    "customer_coverage_rate",
    "time_window_feasibility_rate",
    "truck_battery_feasibility_rate",
    "drone_battery_feasibility_rate",
    "capacity_feasibility_rate",
    "sync_feasibility_rate",
    "total_violation",
    "ga_before_cost",
    "alns_after_cost",
    "improvement_percentage",
    "selected_source",
    "ga_runtime",
    "alns_refine_runtime",
    "candidate_count",
    "selected_candidate_count",
    "selected_candidate_rank",
    "selected_candidate_similarity_to_ga_best",
    "comparison_mode",
    "candidate_types",
    "selected_candidate_types",
    "ga_best_cost",
    "candidate_before_cost",
    "candidate_after_cost",
    "candidate_vehicle_count_before",
    "candidate_vehicle_count_after",
    "alns_improved_candidates",
    "best_improvement_percentage",
    "per_candidate_runtime",
    "vehicle_preserving_refine",
    "baseline_vehicle_count",
    "refined_vehicle_count",
    "distance_improved",
    "completion_time_improved",
    "charging_time_improved",
    "waiting_time_improved",
    "petal_score_improved",
    "accepted_by_hybrid_rule",
    "rejected_reason",
    "paper_cost_before",
    "paper_cost_after",
    "paper_distance_improved",
    "paper_cost_improved",
    "accepted_by_paper_rule",
    "rejected_by_cost_rule",
    "periodic_trigger_count",
    "periodic_selected_elites",
    "periodic_injected_count",
    "periodic_rejected_count",
    "periodic_best_before",
    "periodic_best_after",
    "stagnation_trigger_count",
    "stagnation_selected_elites",
    "stagnation_injected_count",
    "stagnation_rejected_count",
    "stagnation_immigrant_count",
    "stagnation_best_before",
    "stagnation_best_after",
    "stagnation_batches",
    "alns_called_due_to_no_improvement",
    "alns_called_due_to_low_diversity",
    "population_diversity_before",
    "population_diversity_after",
    "hybrid_local_operator_calls",
    "hybrid_local_operator_successes",
    "same_vehicle_relocate_successes",
    "same_vehicle_swap_successes",
    "no_new_vehicle_relocate_successes",
    "drone_reassign_successes",
    "launch_recover_adjust_successes",
    "charging_polish_successes",
    "waiting_reduction_successes",
    "petal_polish_successes",
    "accepted_same_vehicle_improvements",
    "rejected_by_vehicle_increase",
    "time_window_failed_nodes",
    "truck_battery_failed_legs",
    "drone_failed_tasks",
    "customer_coverage_violation",
    "time_window_violation",
    "truck_battery_violation",
    "drone_battery_violation",
    "capacity_violation",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/debug_small.yaml")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose solver diagnostics and print one compact line per run.")
    parser.add_argument("--resume", action="store_true", help="Skip runs already present in summary.csv and append new results.")
    parser.add_argument("--max-runs", type=int, default=None, help="Run at most this many new method-instance-policy combinations.")
    args = parser.parse_args()

    config = load_config(args.config)
    results_dir = resolve_path(config.get("results_dir", "results"))
    results_dir.mkdir(parents=True, exist_ok=True)
    raw_path = results_dir / "raw_results.jsonl"
    summary_path = results_dir / "summary.csv"
    petal_path = results_dir / "petal_comparison_summary.csv"
    rows: list[dict] = _read_existing_rows(summary_path) if args.resume else []
    completed = {_run_key_from_row(row) for row in rows}
    executed_runs = 0

    seeds = config.get("seeds")
    if not isinstance(seeds, list):
        seeds = [config.get("seed", 1987)]

    raw_mode = "a" if args.resume else "w"
    with raw_path.open(raw_mode, encoding="utf-8") as raw_file:
        for seed in seeds:
            seed_config = dict(config)
            seed_config["seed"] = int(seed)
            for source_instance in config.get("instances", []):
                for customer_count in config.get("customer_counts", []):
                    instance = build_instance(seed_config, source_instance, int(customer_count))
                    save_instance(instance, resolve_path(config.get("output_instance_dir", "generated_instances")))
                    for policy in config.get("charging_policies", ["NPC"]):
                        for method in config.get("methods", ["ga", "alns", "hybrid"]):
                            run_key = _run_key(source_instance, int(customer_count), int(seed), str(method), str(policy))
                            if args.resume and run_key in completed:
                                if not args.quiet:
                                    print(f"skip existing: {source_instance}-{customer_count} seed={seed} {method} {policy}")
                                continue
                            if args.max_runs is not None and executed_runs >= args.max_runs:
                                _write_summary(summary_path, rows)
                                _write_petal_summary(petal_path, rows)
                                print(f"stopped after max-runs={args.max_runs}")
                                print(f"raw_results: {raw_path}")
                                print(f"summary: {summary_path}")
                                print(f"petal_summary: {petal_path}")
                                return
                            if args.quiet:
                                with contextlib.redirect_stdout(io.StringIO()):
                                    result = SOLVERS[method](
                                        instance,
                                        charging_policy=policy,
                                        seed=int(seed),
                                        **_solver_kwargs(config, method, int(customer_count)),
                                    )
                            else:
                                result = SOLVERS[method](
                                    instance,
                                    charging_policy=policy,
                                    seed=int(seed),
                                    **_solver_kwargs(config, method, int(customer_count)),
                                )
                            raw_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                            raw_file.flush()
                            row = _summary_row(instance, result)
                            rows.append(row)
                            completed.add(run_key)
                            executed_runs += 1
                            _write_summary(summary_path, rows)
                            _write_petal_summary(petal_path, rows)
                            print(
                                f"{result['instance']} | {result['method']} | {policy} | "
                                f"feasible={result['feasible']} | vehicles={result['vehicle_count']} | "
                                f"distance={result['total_distance']:.2f} | runtime={result['runtime_seconds']:.2f}s"
                            )
                            if args.plot:
                                fig_path = ROOT / "figures" / f"{result['instance']}_{result['method']}_{policy}.png"
                                plot_solution(instance, result, save_path=fig_path, show=False)

    summary_path = _write_summary(summary_path, rows)
    _write_petal_summary(petal_path, rows)

    print(f"raw_results: {raw_path}")
    print(f"summary: {summary_path}")
    print(f"petal_summary: {petal_path}")


def _summary_row(instance: dict, result: dict) -> dict:
    violations = result.get("violations", {})
    feasibility = result.get("feasibility", {})
    diagnostics = result.get("diagnostics", {})
    hybrid_details = result.get("hybrid_details", {})
    solution = result["solution"]
    return {
        "instance": result["instance"],
        "source_instance": instance["source_instance"],
        "customer_count": instance["customer_count"],
        "seed": instance.get("seed", ""),
        "method": result["method"],
        "charging_policy": result["charging_policy"],
        "truck_route": route_to_text(solution.get("truck_route", [])),
        "truck_routes": _truck_routes_to_text(solution.get("truck_routes", [solution.get("truck_route", [])])),
        "drone_tasks": _drone_tasks_to_text(solution.get("drone_tasks", [])),
        "feasible": result["feasible"],
        "vehicle_count": result["vehicle_count"],
        "truck_distance": round(result["truck_distance"], 6),
        "drone_distance": round(result["drone_distance"], 6),
        "total_distance": round(result["total_distance"], 6),
        "completion_time": round(result["completion_time"], 6),
        "waiting_time": round(result["waiting_time"], 6),
        "truck_waiting_time": round(result["truck_waiting_time"], 6),
        "drone_waiting_time": round(result["drone_waiting_time"], 6),
        "charging_count": result["charging_count"],
        "charging_time": round(result["charging_time"], 6),
        "petal_score": round(result.get("petal_score", 0.0), 6),
        "crossing_count": round(result.get("crossing_count", 0.0), 6),
        "route_compactness": round(result.get("route_compactness", 0.0), 6),
        "sector_coherence": round(result.get("sector_coherence", 0.0), 6),
        "depot_radial_consistency": round(result.get("depot_radial_consistency", 0.0), 6),
        "runtime_seconds": round(result["runtime_seconds"], 6),
        "feasibility_rate": round(feasibility.get("feasibility_rate", 0.0), 6),
        "customer_coverage_rate": round(feasibility.get("customer_coverage_rate", 0.0), 6),
        "time_window_feasibility_rate": round(feasibility.get("time_window_feasibility_rate", 0.0), 6),
        "truck_battery_feasibility_rate": round(feasibility.get("truck_battery_feasibility_rate", 0.0), 6),
        "drone_battery_feasibility_rate": round(feasibility.get("drone_battery_feasibility_rate", 0.0), 6),
        "capacity_feasibility_rate": round(feasibility.get("capacity_feasibility_rate", 0.0), 6),
        "sync_feasibility_rate": round(feasibility.get("sync_feasibility_rate", 0.0), 6),
        "total_violation": round(feasibility.get("total_violation", 0.0), 6),
        "ga_before_cost": _round_optional(hybrid_details.get("ga_before_cost", hybrid_details.get("ga_cost", ""))),
        "alns_after_cost": _round_optional(hybrid_details.get("alns_after_cost", hybrid_details.get("alns_cost", ""))),
        "improvement_percentage": _round_optional(hybrid_details.get("improvement_percentage", "")),
        "selected_source": hybrid_details.get("selected_source", ""),
        "ga_runtime": _round_optional(hybrid_details.get("ga_runtime", "")),
        "alns_refine_runtime": _round_optional(hybrid_details.get("alns_refine_runtime", "")),
        "candidate_count": _round_optional(hybrid_details.get("candidate_count", "")),
        "selected_candidate_count": _round_optional(hybrid_details.get("selected_candidate_count", "")),
        "selected_candidate_rank": _round_optional(hybrid_details.get("selected_candidate_rank", "")),
        "selected_candidate_similarity_to_ga_best": _round_optional(hybrid_details.get("selected_candidate_similarity_to_ga_best", "")),
        "comparison_mode": hybrid_details.get("comparison_mode", ""),
        "candidate_types": hybrid_details.get("candidate_types", ""),
        "selected_candidate_types": hybrid_details.get("selected_candidate_types", ""),
        "ga_best_cost": _round_optional(hybrid_details.get("ga_best_cost", "")),
        "candidate_before_cost": _round_optional(hybrid_details.get("candidate_before_cost", "")),
        "candidate_after_cost": _round_optional(hybrid_details.get("candidate_after_cost", "")),
        "candidate_vehicle_count_before": _round_optional(hybrid_details.get("candidate_vehicle_count_before", "")),
        "candidate_vehicle_count_after": _round_optional(hybrid_details.get("candidate_vehicle_count_after", "")),
        "alns_improved_candidates": _round_optional(hybrid_details.get("alns_improved_candidates", "")),
        "best_improvement_percentage": _round_optional(hybrid_details.get("best_improvement_percentage", "")),
        "per_candidate_runtime": _round_optional(hybrid_details.get("per_candidate_runtime", "")),
        "vehicle_preserving_refine": hybrid_details.get("vehicle_preserving_refine", ""),
        "baseline_vehicle_count": _round_optional(hybrid_details.get("baseline_vehicle_count", "")),
        "refined_vehicle_count": _round_optional(hybrid_details.get("refined_vehicle_count", "")),
        "distance_improved": hybrid_details.get("distance_improved", ""),
        "completion_time_improved": hybrid_details.get("completion_time_improved", ""),
        "charging_time_improved": hybrid_details.get("charging_time_improved", ""),
        "waiting_time_improved": hybrid_details.get("waiting_time_improved", ""),
        "petal_score_improved": hybrid_details.get("petal_score_improved", ""),
        "accepted_by_hybrid_rule": hybrid_details.get("accepted_by_hybrid_rule", ""),
        "rejected_reason": hybrid_details.get("rejected_reason", ""),
        "paper_cost_before": _round_optional(hybrid_details.get("paper_cost_before", "")),
        "paper_cost_after": _round_optional(hybrid_details.get("paper_cost_after", "")),
        "paper_distance_improved": hybrid_details.get("paper_distance_improved", ""),
        "paper_cost_improved": hybrid_details.get("paper_cost_improved", ""),
        "accepted_by_paper_rule": hybrid_details.get("accepted_by_paper_rule", ""),
        "rejected_by_cost_rule": hybrid_details.get("rejected_by_cost_rule", ""),
        "periodic_trigger_count": _round_optional(hybrid_details.get("periodic_trigger_count", "")),
        "periodic_selected_elites": _round_optional(hybrid_details.get("periodic_selected_elites", "")),
        "periodic_injected_count": _round_optional(hybrid_details.get("periodic_injected_count", "")),
        "periodic_rejected_count": _round_optional(hybrid_details.get("periodic_rejected_count", "")),
        "periodic_best_before": _round_optional(hybrid_details.get("periodic_best_before", "")),
        "periodic_best_after": _round_optional(hybrid_details.get("periodic_best_after", "")),
        "stagnation_trigger_count": _round_optional(hybrid_details.get("stagnation_trigger_count", "")),
        "stagnation_selected_elites": _round_optional(hybrid_details.get("stagnation_selected_elites", "")),
        "stagnation_injected_count": _round_optional(hybrid_details.get("stagnation_injected_count", "")),
        "stagnation_rejected_count": _round_optional(hybrid_details.get("stagnation_rejected_count", "")),
        "stagnation_immigrant_count": _round_optional(hybrid_details.get("stagnation_immigrant_count", "")),
        "stagnation_best_before": _round_optional(hybrid_details.get("stagnation_best_before", "")),
        "stagnation_best_after": _round_optional(hybrid_details.get("stagnation_best_after", "")),
        "stagnation_batches": hybrid_details.get("stagnation_batches", ""),
        "alns_called_due_to_no_improvement": _round_optional(hybrid_details.get("alns_called_due_to_no_improvement", "")),
        "alns_called_due_to_low_diversity": _round_optional(hybrid_details.get("alns_called_due_to_low_diversity", "")),
        "population_diversity_before": _round_optional(hybrid_details.get("population_diversity_before", "")),
        "population_diversity_after": _round_optional(hybrid_details.get("population_diversity_after", "")),
        "hybrid_local_operator_calls": _round_optional(hybrid_details.get("hybrid_local_operator_calls", "")),
        "hybrid_local_operator_successes": _round_optional(hybrid_details.get("hybrid_local_operator_successes", "")),
        "same_vehicle_relocate_successes": _round_optional(hybrid_details.get("same_vehicle_relocate_successes", "")),
        "same_vehicle_swap_successes": _round_optional(hybrid_details.get("same_vehicle_swap_successes", "")),
        "no_new_vehicle_relocate_successes": _round_optional(hybrid_details.get("no_new_vehicle_relocate_successes", "")),
        "drone_reassign_successes": _round_optional(hybrid_details.get("drone_reassign_successes", "")),
        "launch_recover_adjust_successes": _round_optional(hybrid_details.get("launch_recover_adjust_successes", "")),
        "charging_polish_successes": _round_optional(hybrid_details.get("charging_polish_successes", "")),
        "waiting_reduction_successes": _round_optional(hybrid_details.get("waiting_reduction_successes", "")),
        "petal_polish_successes": _round_optional(hybrid_details.get("petal_polish_successes", "")),
        "accepted_same_vehicle_improvements": _round_optional(hybrid_details.get("accepted_same_vehicle_improvements", "")),
        "rejected_by_vehicle_increase": _round_optional(hybrid_details.get("rejected_by_vehicle_increase", "")),
        "time_window_failed_nodes": "; ".join(diagnostics.get("time_window_failed_nodes", [])),
        "truck_battery_failed_legs": "; ".join(diagnostics.get("truck_battery_failed_legs", [])),
        "drone_failed_tasks": "; ".join(diagnostics.get("drone_failed_tasks", [])),
        "customer_coverage_violation": round(violations.get("customer_coverage", 0.0), 6),
        "time_window_violation": round(violations.get("time_window", 0.0), 6),
        "truck_battery_violation": round(violations.get("truck_battery", 0.0), 6),
        "drone_battery_violation": round(violations.get("drone_battery", 0.0), 6),
        "capacity_violation": round(violations.get("capacity", 0.0), 6),
    }


def _drone_tasks_to_text(tasks: list[dict]) -> str:
    formatted: list[str] = []
    for task in tasks:
        route = task.get("drone_route")
        if route is None:
            route = [task["launch"]] + task.get("customers", [task.get("customer")]) + [task["recover"]]
        formatted.append(f"r{task.get('route_index', 0)}:{route_to_text(route)}")
    return "; ".join(formatted)


def _truck_routes_to_text(routes: list[list[int]]) -> str:
    return " | ".join(f"v{idx}:{route_to_text(route)}" for idx, route in enumerate(routes, start=1))


def _round_optional(value: object) -> object:
    if value == "":
        return ""
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return value


def _write_summary(summary_path: Path, rows: list[dict]) -> Path:
    try:
        return _write_csv(summary_path, rows)
    except PermissionError:
        fallback = summary_path.with_name(f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        return _write_csv(fallback, rows)


def _write_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as file_object:
        writer = csv.DictWriter(file_object, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file_object:
        return list(csv.DictReader(file_object))


def _run_key(source_instance: str, customer_count: int, seed: int, method: str, charging_policy: str) -> tuple[str, int, int, str, str]:
    return (str(source_instance), int(customer_count), int(seed), str(method), str(charging_policy))


def _run_key_from_row(row: dict) -> tuple[str, int, int, str, str]:
    return _run_key(
        str(row.get("source_instance", "")),
        int(float(row.get("customer_count", 0) or 0)),
        int(float(row.get("seed", 0) or 0)),
        str(row.get("method", "")),
        str(row.get("charging_policy", "")),
    )


def _write_petal_summary(path: Path, rows: list[dict]) -> Path:
    fields = [
        "instance",
        "source_instance",
        "customer_count",
        "method",
        "charging_policy",
        "feasible",
        "vehicle_count",
        "total_distance",
        "truck_distance",
        "drone_distance",
        "charging_time",
        "waiting_time",
        "petal_score",
        "crossing_count",
        "route_compactness",
        "sector_coherence",
        "runtime_seconds",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file_object:
        writer = csv.DictWriter(file_object, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return path


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


if __name__ == "__main__":
    main()
