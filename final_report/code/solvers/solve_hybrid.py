"""GA+ALNS hybrid solvers for Truck-Drone EVRPTW-NL."""

from __future__ import annotations

import time
from typing import Any

try:
    from .hybrid_tools import (
        compare_hybrid_results,
        hybrid_improvement_percentage,
        paper_cost,
        select_diverse_top_k,
        solution_similarity,
        solution_to_alns_state,
    )
    from .solve_alns import refine_state, solve as solve_alns
    from .solve_ga import expand_ga_candidates_for_hybrid, generate_diverse_ga_candidates_for_hybrid, generate_ga_candidates_for_hybrid, solve as solve_ga
except ImportError:  # pragma: no cover
    from solvers.hybrid_tools import (
        compare_hybrid_results,
        hybrid_improvement_percentage,
        paper_cost,
        select_diverse_top_k,
        solution_similarity,
        solution_to_alns_state,
    )
    from solvers.solve_alns import refine_state, solve as solve_alns
    from solvers.solve_ga import expand_ga_candidates_for_hybrid, generate_diverse_ga_candidates_for_hybrid, generate_ga_candidates_for_hybrid, solve as solve_ga


def solve(instance: dict, charging_policy: str = "NPC", seed: int | None = None, **kwargs: Any) -> dict:
    mode = str(kwargs.get("hybrid_mode") or "refine")
    if mode == "selector":
        return _solve_selector(instance, charging_policy=charging_policy, seed=seed, **kwargs)
    if mode == "preserve":
        return _solve_refine(instance, charging_policy=charging_policy, seed=seed, preserve_vehicle=True, method_name="hybrid_preserve", **kwargs)
    if mode in {"topk", "top_k"}:
        return _solve_topk(instance, charging_policy=charging_policy, seed=seed, **kwargs)
    if mode in {"diverse_topk", "diverse_top_k"}:
        return _solve_topk(instance, charging_policy=charging_policy, seed=seed, diverse_candidates=True, method_name="hybrid_diverse_topk", **kwargs)
    if mode == "periodic":
        return _solve_periodic(instance, charging_policy=charging_policy, seed=seed, **kwargs)
    if mode == "stagnation":
        return _solve_stagnation(instance, charging_policy=charging_policy, seed=seed, **kwargs)
    if mode == "diverse_stagnation":
        return _solve_stagnation(instance, charging_policy=charging_policy, seed=seed, diverse_candidates=True, method_name="hybrid_diverse_stagnation", **kwargs)
    return _solve_refine(instance, charging_policy=charging_policy, seed=seed, **kwargs)


def _solve_selector(instance: dict, charging_policy: str = "NPC", seed: int | None = None, **kwargs: Any) -> dict:
    start = time.perf_counter()
    ga_result = solve_ga(instance, charging_policy=charging_policy, seed=seed, **kwargs)
    alns_result = solve_alns(instance, charging_policy=charging_policy, seed=seed, **kwargs)
    best = compare_hybrid_results(ga_result, alns_result)
    best = dict(best)
    best["method"] = "hybrid_selector"
    best["runtime_seconds"] = time.perf_counter() - start
    best["notes"] = (
        "Hybrid selector baseline: runs GA and independent ALNS separately, "
        "then keeps the better feasible/evaluated solution."
    )
    best["hybrid_details"] = {
        "hybrid_mode": "selector",
        "ga_cost": _display_cost(ga_result),
        "alns_cost": _display_cost(alns_result),
        "selected_source": ga_result["method"] if best["solution"] == ga_result["solution"] else alns_result["method"],
        "alns_improved": False,
        "improvement_percentage": hybrid_improvement_percentage(ga_result, best),
    }
    return best


def _solve_refine(
    instance: dict,
    charging_policy: str = "NPC",
    seed: int | None = None,
    preserve_vehicle: bool = False,
    method_name: str = "hybrid_refine",
    **kwargs: Any,
) -> dict:
    start = time.perf_counter()
    total_budget = float(kwargs.get("time_budget_seconds") or _default_hybrid_budget(instance))
    ga_budget, alns_budget = _split_time_budget(instance, total_budget)

    ga_kwargs = dict(kwargs)
    ga_kwargs.pop("hybrid_mode", None)
    ga_kwargs["time_budget_seconds"] = ga_budget
    ga_result = solve_ga(instance, charging_policy=charging_policy, seed=seed, **ga_kwargs)

    initial_state = solution_to_alns_state(ga_result["solution"], instance)
    alns_profile = _hybrid_refine_profile(kwargs, preserve_vehicle, default_local=False)
    alns_kwargs = {
        "time_budget_seconds": alns_budget,
        "alns_profile": alns_profile,
        "method_label": alns_profile,
        "preserve_vehicle_count": preserve_vehicle,
        "baseline_vehicle_count": ga_result["vehicle_count"],
    }
    if "max_vehicle_count" in kwargs:
        alns_kwargs["max_vehicle_count"] = kwargs["max_vehicle_count"]
    refined_result = refine_state(instance, initial_state, charging_policy=charging_policy, seed=seed, **alns_kwargs)

    selected = compare_hybrid_results(ga_result, refined_result)
    selected_source = "alns_refine" if selected is refined_result else "ga"
    best = dict(selected)
    best["method"] = method_name
    best["runtime_seconds"] = time.perf_counter() - start
    best["notes"] = (
        "GA+ALNS single-best refinement: GA builds the global truck-drone solution, "
        "then ALNS locally refines routes, drone tasks, charging and petal structure."
    )
    best["hybrid_details"] = {
        "hybrid_mode": "single_best_refine",
        "ga_runtime": ga_result["runtime_seconds"],
        "alns_refine_runtime": refined_result["runtime_seconds"],
        "total_runtime": best["runtime_seconds"],
        "ga_time_budget_seconds": ga_budget,
        "alns_time_budget_seconds": alns_budget,
        "ga_before_cost": _display_cost(ga_result),
        "alns_after_cost": _display_cost(refined_result),
        "ga_vehicle_count": ga_result["vehicle_count"],
        "alns_vehicle_count": refined_result["vehicle_count"],
        "ga_total_distance": ga_result["total_distance"],
        "alns_total_distance": refined_result["total_distance"],
        "ga_truck_distance": ga_result.get("truck_distance", 0.0),
        "alns_truck_distance": refined_result.get("truck_distance", 0.0),
        "ga_drone_distance": ga_result.get("drone_distance", 0.0),
        "alns_drone_distance": refined_result.get("drone_distance", 0.0),
        "ga_charging_time": ga_result.get("charging_time", 0.0),
        "alns_charging_time": refined_result.get("charging_time", 0.0),
        "ga_waiting_time": ga_result.get("waiting_time", 0.0),
        "alns_waiting_time": refined_result.get("waiting_time", 0.0),
        "selected_source": selected_source,
        "alns_improved": selected_source == "alns_refine",
        "improvement_percentage": hybrid_improvement_percentage(ga_result, best),
        "vehicle_preserving_refine": preserve_vehicle,
        "baseline_vehicle_count": ga_result["vehicle_count"],
        "refined_vehicle_count": refined_result["vehicle_count"],
        "distance_improved": refined_result["total_distance"] < ga_result["total_distance"],
        "completion_time_improved": refined_result["completion_time"] < ga_result["completion_time"],
        "charging_time_improved": refined_result.get("charging_time", 0.0) < ga_result.get("charging_time", 0.0),
        "waiting_time_improved": refined_result.get("waiting_time", 0.0) < ga_result.get("waiting_time", 0.0),
        "petal_score_improved": refined_result.get("petal_score", 0.0) < ga_result.get("petal_score", 0.0),
        "accepted_by_hybrid_rule": selected_source == "alns_refine",
        "rejected_reason": _refine_rejected_reason(ga_result, refined_result, selected_source),
        **_hybrid_local_summary(refined_result),
    }
    return best


def _solve_topk(
    instance: dict,
    charging_policy: str = "NPC",
    seed: int | None = None,
    diverse_candidates: bool = False,
    method_name: str = "hybrid_topk",
    **kwargs: Any,
) -> dict:
    start = time.perf_counter()
    total_budget = float(kwargs.get("time_budget_seconds") or _default_hybrid_budget(instance))
    top_k = int(kwargs.get("hybrid_top_k") or 3)
    similarity_threshold = float(kwargs.get("similarity_threshold") or 0.75)
    ga_budget, alns_total_budget = _split_topk_time_budget(instance, total_budget)

    comparison_mode = str(kwargs.get("comparison_mode") or ("paper_cost_priority" if diverse_candidates else "lexicographic_research"))
    candidate_generator = generate_diverse_ga_candidates_for_hybrid if diverse_candidates else generate_ga_candidates_for_hybrid
    ga_candidates = candidate_generator(
        instance,
        charging_policy=charging_policy,
        seed=seed,
        time_budget_seconds=ga_budget,
        max_candidates=max(top_k * (6 if diverse_candidates else 4), top_k),
    )
    selected_candidates = select_diverse_top_k(
        ga_candidates,
        k=top_k,
        similarity_threshold=similarity_threshold,
        require_type_coverage=diverse_candidates,
    )
    if not selected_candidates:
        return _solve_refine(instance, charging_policy=charging_policy, seed=seed, **kwargs)

    ga_best = ga_candidates[0]["result"]
    best = dict(ga_best)
    best_source = "ga"
    best_candidate_rank = int(ga_candidates[0].get("ga_rank", 1))
    best_similarity = 1.0
    per_candidate_budget = alns_total_budget / max(1, len(selected_candidates))
    candidate_details: list[dict[str, Any]] = []
    improved_candidates = 0
    alns_profile = _hybrid_refine_profile(kwargs, preserve_vehicle=True, default_local=diverse_candidates)

    for idx, candidate in enumerate(selected_candidates, start=1):
        elapsed = time.perf_counter() - start
        remaining_total = total_budget - elapsed
        remaining_candidates = len(selected_candidates) - idx + 1
        if remaining_total <= 0.5:
            break
        candidate_budget = min(per_candidate_budget, max(0.5, remaining_total / max(1, remaining_candidates)))
        candidate_result = candidate["result"]
        candidate_state = solution_to_alns_state(candidate_result["solution"], instance)
        refined = refine_state(
            instance,
            candidate_state,
            charging_policy=charging_policy,
            seed=(seed or int(instance.get("seed", 1987))) + idx,
            time_budget_seconds=candidate_budget,
            max_iterations=_hybrid_refine_iterations(instance, candidate_budget, diverse_candidates),
            alns_profile=alns_profile,
            method_label=alns_profile,
            preserve_vehicle_count=True,
            baseline_vehicle_count=candidate_result["vehicle_count"],
        )
        selected_for_candidate = _select_refined_for_candidate(candidate_result, refined, comparison_mode)
        candidate_improved = selected_for_candidate is refined
        if candidate_improved:
            improved_candidates += 1
        candidate_details.append(
            {
                "candidate_index": idx,
                "ga_rank": int(candidate.get("ga_rank", idx)),
                "candidate_type": str(candidate.get("candidate_type") or candidate_result.get("metadata", {}).get("hybrid_candidate_type", "balanced")),
                "similarity_to_ga_best": solution_similarity(ga_best["solution"], candidate_result["solution"]),
                "similarity_to_selected": float(candidate.get("similarity_to_selected", 0.0)),
                "before_cost": _display_cost(candidate_result),
                "after_cost": _display_cost(refined),
                "paper_cost_before": paper_cost(candidate_result),
                "paper_cost_after": paper_cost(refined),
                "before_vehicle_count": candidate_result["vehicle_count"],
                "after_vehicle_count": refined["vehicle_count"],
                "paper_distance_improved": refined["total_distance"] < candidate_result["total_distance"],
                "paper_cost_improved": paper_cost(refined) < paper_cost(candidate_result),
                "alns_improved": candidate_improved,
                "alns_runtime": refined["runtime_seconds"],
                "rejected_reason": _refine_rejected_reason(candidate_result, refined, "alns_refine" if candidate_improved else "ga_candidate"),
                **_hybrid_local_summary(refined),
            }
        )
        maybe_best = compare_hybrid_results(best, selected_for_candidate, comparison_mode=comparison_mode)
        if maybe_best is selected_for_candidate:
            best = dict(selected_for_candidate)
            best_source = "alns_refine" if candidate_improved else "ga_candidate"
            best_candidate_rank = int(candidate.get("ga_rank", idx))
            best_similarity = solution_similarity(ga_best["solution"], candidate_result["solution"])

    best["method"] = method_name
    best["runtime_seconds"] = time.perf_counter() - start
    best["notes"] = (
        "GA+ALNS Top-K diverse refinement: selects structurally different GA candidates, "
        "runs short ALNS refinement for each, and keeps the best feasible result."
    )
    best["hybrid_details"] = {
        "hybrid_mode": "top_k_diverse_refine",
        "diverse_candidate_generation": diverse_candidates,
        "comparison_mode": comparison_mode,
        "candidate_types": ",".join(sorted({str(row.get("candidate_type", "balanced")) for row in ga_candidates})),
        "selected_candidate_types": ",".join(str(row.get("candidate_type", row.get("result", {}).get("metadata", {}).get("hybrid_candidate_type", "balanced"))) for row in selected_candidates),
        "candidate_count": len(ga_candidates),
        "selected_candidate_count": len(selected_candidates),
        "top_k": top_k,
        "similarity_threshold": similarity_threshold,
        "selected_candidate_rank": best_candidate_rank,
        "selected_candidate_similarity_to_ga_best": best_similarity,
        "ga_runtime": max((row["result"]["runtime_seconds"] for row in ga_candidates), default=0.0),
        "alns_refine_runtime": sum(row["alns_runtime"] for row in candidate_details),
        "total_runtime": best["runtime_seconds"],
        "ga_time_budget_seconds": ga_budget,
        "alns_time_budget_seconds": alns_total_budget,
        "per_candidate_runtime_budget": per_candidate_budget,
        "ga_best_cost": _display_cost(ga_best),
        "ga_before_cost": _display_cost(ga_best),
        "candidate_before_cost": next(
            (row["before_cost"] for row in candidate_details if row["ga_rank"] == best_candidate_rank),
            _display_cost(ga_best),
        ),
        "candidate_after_cost": next(
            (row["after_cost"] for row in candidate_details if row["ga_rank"] == best_candidate_rank),
            _display_cost(best),
        ),
        "paper_cost_before": paper_cost(ga_best),
        "paper_cost_after": paper_cost(best),
        "paper_distance_improved": float(best.get("total_distance", 0.0)) < float(ga_best.get("total_distance", 0.0)),
        "paper_cost_improved": paper_cost(best) < paper_cost(ga_best),
        "accepted_by_paper_rule": best_source in {"alns_refine", "ga_candidate"} and comparison_mode == "paper_cost_priority",
        "rejected_by_cost_rule": comparison_mode == "paper_cost_priority" and best_source == "ga",
        "candidate_vehicle_count_before": next(
            (row["before_vehicle_count"] for row in candidate_details if row["ga_rank"] == best_candidate_rank),
            ga_best["vehicle_count"],
        ),
        "candidate_vehicle_count_after": next(
            (row["after_vehicle_count"] for row in candidate_details if row["ga_rank"] == best_candidate_rank),
            best["vehicle_count"],
        ),
        "alns_improved_candidates": improved_candidates,
        "best_improvement_percentage": hybrid_improvement_percentage(ga_best, best),
        "improvement_percentage": hybrid_improvement_percentage(ga_best, best),
        "selected_source": best_source,
        "alns_improved": best_source == "alns_refine",
        "vehicle_preserving_refine": True,
        "baseline_vehicle_count": ga_best["vehicle_count"],
        "refined_vehicle_count": next(
            (row["after_vehicle_count"] for row in candidate_details if row["ga_rank"] == best_candidate_rank),
            best["vehicle_count"],
        ),
        "distance_improved": float(best.get("total_distance", 0.0)) < float(ga_best.get("total_distance", 0.0)),
        "completion_time_improved": float(best.get("completion_time", 0.0)) < float(ga_best.get("completion_time", 0.0)),
        "charging_time_improved": float(best.get("charging_time", 0.0)) < float(ga_best.get("charging_time", 0.0)),
        "waiting_time_improved": float(best.get("waiting_time", 0.0)) < float(ga_best.get("waiting_time", 0.0)),
        "petal_score_improved": float(best.get("petal_score", 0.0)) < float(ga_best.get("petal_score", 0.0)),
        "accepted_by_hybrid_rule": best_source in {"alns_refine", "ga_candidate"},
        "rejected_reason": "" if best_source in {"alns_refine", "ga_candidate"} else "kept_ga_best",
        "per_candidate_runtime": per_candidate_budget,
        "candidate_details": candidate_details,
        **_sum_hybrid_local_summaries(candidate_details),
    }
    return best


def _solve_periodic(instance: dict, charging_policy: str = "NPC", seed: int | None = None, **kwargs: Any) -> dict:
    start = time.perf_counter()
    total_budget = float(kwargs.get("time_budget_seconds") or _default_hybrid_budget(instance))
    evolution_budget, periodic_budget, final_refine_budget = _split_periodic_time_budget(instance, total_budget)
    max_batches = int(kwargs.get("max_batches") or _default_periodic_batches(instance))
    interval_batches = int(kwargs.get("interval_batches") or 2)
    top_k_elites = int(kwargs.get("top_k_elites") or 2)
    similarity_threshold = float(kwargs.get("similarity_threshold") or 0.75)
    base_seed = int(seed if seed is not None else instance.get("seed", 1987))

    candidates = generate_ga_candidates_for_hybrid(
        instance,
        charging_policy=charging_policy,
        seed=base_seed,
        time_budget_seconds=max(1.0, evolution_budget / max(1, max_batches)),
        max_candidates=_initial_periodic_candidate_limit(instance),
    )
    candidates = _rank_candidates(candidates)
    periodic_trigger_count = 0
    periodic_selected_elites = 0
    periodic_injected_count = 0
    periodic_rejected_count = 0
    periodic_best_before = _display_cost(candidates[0]["result"])
    population_diversity_before = _population_diversity(candidates)
    periodic_details: list[dict[str, Any]] = []

    for batch in range(2, max_batches + 1):
        if time.perf_counter() - start >= total_budget * 0.75:
            break
        expanded = expand_ga_candidates_for_hybrid(
            instance,
            candidates,
            charging_policy=charging_policy,
            seed=base_seed + batch * 100,
            max_new_candidates=_periodic_expansion_count(instance),
        )
        candidates = _rank_candidates(candidates + expanded)[:18]
        if batch % max(1, interval_batches) != 0:
            continue
        periodic_trigger_count += 1
        elites = select_diverse_top_k(candidates, k=top_k_elites, similarity_threshold=similarity_threshold)
        periodic_selected_elites += len(elites)
        per_elite_budget = _periodic_alns_runtime(instance)
        remaining_periodic_budget = max(0.0, periodic_budget - sum(row.get("runtime", 0.0) for row in periodic_details))
        if remaining_periodic_budget <= 0:
            break
        per_elite_budget = min(per_elite_budget, remaining_periodic_budget / max(1, len(elites)))
        for elite_index, elite in enumerate(elites, start=1):
            elite_result = elite["result"]
            refined = refine_state(
                instance,
                solution_to_alns_state(elite_result["solution"], instance),
                charging_policy=charging_policy,
                seed=base_seed + batch * 1000 + elite_index,
                time_budget_seconds=per_elite_budget,
                alns_profile="alns_hybrid_preserve",
                method_label="alns_hybrid_preserve",
                preserve_vehicle_count=True,
                baseline_vehicle_count=elite_result["vehicle_count"],
            )
            selected = compare_hybrid_results(elite_result, refined)
            injected = selected is refined
            if injected:
                periodic_injected_count += 1
                candidates.append(
                    {
                        "individual": None,
                        "result": selected,
                        "solution": selected["solution"],
                        "cost_tuple": (),
                        "runtime_seconds": selected["runtime_seconds"],
                    }
                )
            else:
                periodic_rejected_count += 1
            periodic_details.append(
                {
                    "batch": batch,
                    "elite_rank": int(elite.get("ga_rank", elite_index)),
                    "before_cost": _display_cost(elite_result),
                    "after_cost": _display_cost(refined),
                    "before_vehicle_count": elite_result["vehicle_count"],
                    "after_vehicle_count": refined["vehicle_count"],
                    "injected": injected,
                    "rejected_reason": _refine_rejected_reason(elite_result, refined, "alns_refine" if injected else "ga"),
                    "runtime": refined["runtime_seconds"],
                }
            )
        candidates = _rank_candidates(candidates)[:18]

    candidates = _rank_candidates(candidates)
    population_diversity_after = _population_diversity(candidates)
    final_selected = select_diverse_top_k(candidates, k=3, similarity_threshold=similarity_threshold)
    best = dict(candidates[0]["result"])
    final_details: list[dict[str, Any]] = []
    remaining_total_budget = max(0.0, total_budget - (time.perf_counter() - start))
    effective_final_budget = min(final_refine_budget, remaining_total_budget)
    if effective_final_budget <= 1.0:
        final_selected = []
    per_candidate_budget = effective_final_budget / max(1, len(final_selected))
    for idx, candidate in enumerate(final_selected, start=1):
        candidate_result = candidate["result"]
        refined = refine_state(
            instance,
            solution_to_alns_state(candidate_result["solution"], instance),
            charging_policy=charging_policy,
            seed=base_seed + 5000 + idx,
            time_budget_seconds=per_candidate_budget,
            alns_profile="alns_hybrid_preserve",
            method_label="alns_hybrid_preserve",
            preserve_vehicle_count=True,
            baseline_vehicle_count=candidate_result["vehicle_count"],
        )
        selected = compare_hybrid_results(candidate_result, refined)
        best = dict(compare_hybrid_results(best, selected))
        final_details.append(
            {
                "candidate_rank": int(candidate.get("ga_rank", idx)),
                "before_cost": _display_cost(candidate_result),
                "after_cost": _display_cost(refined),
                "injected": selected is refined,
                "runtime": refined["runtime_seconds"],
            }
        )

    best["method"] = "hybrid_periodic"
    best["runtime_seconds"] = time.perf_counter() - start
    best["notes"] = (
        "GA+ALNS periodic elite improvement: evolves a GA candidate pool, "
        "periodically refines diverse elites with vehicle-preserving ALNS, then performs final Top-K refinement."
    )
    best["hybrid_details"] = {
        "hybrid_mode": "periodic_elite_improvement",
        "periodic_trigger_count": periodic_trigger_count,
        "periodic_selected_elites": periodic_selected_elites,
        "periodic_injected_count": periodic_injected_count,
        "periodic_rejected_count": periodic_rejected_count,
        "periodic_best_before": periodic_best_before,
        "periodic_best_after": _display_cost(best),
        "population_diversity_before": population_diversity_before,
        "population_diversity_after": population_diversity_after,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(final_selected),
        "ga_time_budget_seconds": evolution_budget,
        "periodic_alns_time_budget_seconds": periodic_budget,
        "alns_time_budget_seconds": final_refine_budget,
        "total_runtime": best["runtime_seconds"],
        "improvement_percentage": hybrid_improvement_percentage(candidates[0]["result"], best),
        "selected_source": "hybrid_periodic",
        "vehicle_preserving_refine": True,
        "periodic_details": periodic_details,
        "candidate_details": final_details,
    }
    return best


def _solve_stagnation(
    instance: dict,
    charging_policy: str = "NPC",
    seed: int | None = None,
    diverse_candidates: bool = False,
    method_name: str = "hybrid_stagnation",
    **kwargs: Any,
) -> dict:
    start = time.perf_counter()
    total_budget = float(kwargs.get("time_budget_seconds") or _default_hybrid_budget(instance))
    evolution_budget, stagnation_budget, final_refine_budget = _split_stagnation_time_budget(instance, total_budget)
    max_batches = int(kwargs.get("max_batches") or _default_periodic_batches(instance))
    stagnation_limit = int(kwargs.get("stagnation_limit") or 2)
    top_k_elites = int(kwargs.get("top_k_elites") or 2)
    immigrant_ratio = float(kwargs.get("immigrant_ratio") or 0.15)
    similarity_threshold = float(kwargs.get("similarity_threshold") or 0.75)
    diversity_threshold = float(kwargs.get("diversity_threshold") or 0.25)
    alns_profile = str(kwargs.get("alns_refine_profile") or kwargs.get("hybrid_alns_profile") or "alns_hybrid_local")
    comparison_mode = str(kwargs.get("comparison_mode") or ("paper_cost_priority" if diverse_candidates else "lexicographic_research"))
    base_seed = int(seed if seed is not None else instance.get("seed", 1987))

    candidate_generator = generate_diverse_ga_candidates_for_hybrid if diverse_candidates else generate_ga_candidates_for_hybrid
    candidates = candidate_generator(
        instance,
        charging_policy=charging_policy,
        seed=base_seed,
        time_budget_seconds=max(1.0, evolution_budget / max(1, max_batches)),
        max_candidates=_initial_periodic_candidate_limit(instance),
    )
    candidates = _rank_candidates(candidates)
    initial_best_result = dict(candidates[0]["result"])
    best_rank = _result_rank(candidates[0]["result"])
    stagnation_best_before = _display_cost(candidates[0]["result"])
    population_diversity_before = _population_diversity(candidates)
    no_improvement_batches = 0
    stagnation_trigger_count = 0
    stagnation_selected_elites = 0
    stagnation_injected_count = 0
    stagnation_rejected_count = 0
    stagnation_immigrant_count = 0
    alns_called_due_to_no_improvement = 0
    alns_called_due_to_low_diversity = 0
    stagnation_batches: list[int] = []
    stagnation_details: list[dict[str, Any]] = []

    for batch in range(2, max_batches + 1):
        if time.perf_counter() - start >= total_budget * 0.75:
            break
        expanded = expand_ga_candidates_for_hybrid(
            instance,
            candidates,
            charging_policy=charging_policy,
            seed=base_seed + batch * 100,
            max_new_candidates=_periodic_expansion_count(instance),
        )
        candidates = _rank_candidates(candidates + expanded)[:18]
        current_rank = _result_rank(candidates[0]["result"])
        if current_rank < best_rank:
            best_rank = current_rank
            no_improvement_batches = 0
        else:
            no_improvement_batches += 1

        diversity = _population_diversity(candidates)
        trigger_no_improvement = has_stagnated(no_improvement_batches, stagnation_limit)
        trigger_low_diversity = diversity < diversity_threshold
        if not (trigger_no_improvement or trigger_low_diversity):
            continue

        stagnation_trigger_count += 1
        stagnation_batches.append(batch)
        if trigger_no_improvement:
            alns_called_due_to_no_improvement += 1
        if trigger_low_diversity:
            alns_called_due_to_low_diversity += 1

        elites = select_diverse_top_k(candidates, k=top_k_elites, similarity_threshold=similarity_threshold)
        stagnation_selected_elites += len(elites)
        spent_stagnation_budget = sum(row.get("runtime", 0.0) for row in stagnation_details)
        remaining_stagnation_budget = max(0.0, stagnation_budget - spent_stagnation_budget)
        if remaining_stagnation_budget <= 0:
            break
        per_elite_budget = min(_periodic_alns_runtime(instance), remaining_stagnation_budget / max(1, len(elites)))
        injected_this_trigger = 0

        for elite_index, elite in enumerate(elites, start=1):
            elite_result = elite["result"]
            refined = refine_state(
                instance,
                solution_to_alns_state(elite_result["solution"], instance),
                charging_policy=charging_policy,
                seed=base_seed + batch * 1000 + elite_index,
                time_budget_seconds=per_elite_budget,
                alns_profile=alns_profile,
                method_label=alns_profile,
                preserve_vehicle_count=True,
                baseline_vehicle_count=elite_result["vehicle_count"],
            )
            selected = _select_refined_for_candidate(elite_result, refined, comparison_mode)
            injected = selected is refined
            if injected:
                stagnation_injected_count += 1
                injected_this_trigger += 1
                candidates.append(
                    {
                        "individual": None,
                        "result": selected,
                        "solution": selected["solution"],
                        "cost_tuple": (),
                        "runtime_seconds": selected["runtime_seconds"],
                    }
                )
            else:
                stagnation_rejected_count += 1
            stagnation_details.append(
                {
                    "batch": batch,
                    "elite_rank": int(elite.get("ga_rank", elite_index)),
                    "trigger_reason": _trigger_reason(trigger_no_improvement, trigger_low_diversity),
                    "before_cost": _display_cost(elite_result),
                    "after_cost": _display_cost(refined),
                    "paper_cost_before": paper_cost(elite_result),
                    "paper_cost_after": paper_cost(refined),
                    "paper_distance_improved": refined["total_distance"] < elite_result["total_distance"],
                    "paper_cost_improved": paper_cost(refined) < paper_cost(elite_result),
                    "before_vehicle_count": elite_result["vehicle_count"],
                    "after_vehicle_count": refined["vehicle_count"],
                    "injected": injected,
                    "rejected_reason": _refine_rejected_reason(elite_result, refined, "alns_refine" if injected else "ga"),
                    "runtime": refined["runtime_seconds"],
                    **_hybrid_local_summary(refined),
                }
            )

        if injected_this_trigger == 0:
            immigrant_count = max(1, int(round(len(candidates) * immigrant_ratio)))
            immigrants = expand_ga_candidates_for_hybrid(
                instance,
                candidates,
                charging_policy=charging_policy,
                seed=base_seed + batch * 10000,
                max_new_candidates=immigrant_count,
            )
            stagnation_immigrant_count += len(immigrants)
            candidates.extend(immigrants)
        else:
            no_improvement_batches = 0

        candidates = _rank_candidates(candidates)[:18]

    candidates = _rank_candidates(candidates)
    population_diversity_after = _population_diversity(candidates)
    final_selected = select_diverse_top_k(
        candidates,
        k=3,
        similarity_threshold=similarity_threshold,
        require_type_coverage=diverse_candidates,
    )
    best = dict(candidates[0]["result"])
    final_details: list[dict[str, Any]] = []
    remaining_total_budget = max(0.0, total_budget - (time.perf_counter() - start))
    effective_final_budget = min(final_refine_budget + max(0.0, stagnation_budget - sum(row.get("runtime", 0.0) for row in stagnation_details)), remaining_total_budget)
    if effective_final_budget <= 1.0:
        final_selected = []
    per_candidate_budget = effective_final_budget / max(1, len(final_selected))
    for idx, candidate in enumerate(final_selected, start=1):
        candidate_result = candidate["result"]
        refined = refine_state(
            instance,
            solution_to_alns_state(candidate_result["solution"], instance),
            charging_policy=charging_policy,
            seed=base_seed + 7000 + idx,
            time_budget_seconds=per_candidate_budget,
            alns_profile=alns_profile,
            method_label=alns_profile,
            preserve_vehicle_count=True,
            baseline_vehicle_count=candidate_result["vehicle_count"],
        )
        selected = _select_refined_for_candidate(candidate_result, refined, comparison_mode)
        best = dict(compare_hybrid_results(best, selected, comparison_mode=comparison_mode))
        final_details.append(
            {
                "candidate_rank": int(candidate.get("ga_rank", idx)),
                "candidate_type": str(candidate.get("candidate_type") or candidate_result.get("metadata", {}).get("hybrid_candidate_type", "balanced")),
                "before_cost": _display_cost(candidate_result),
                "after_cost": _display_cost(refined),
                "paper_cost_before": paper_cost(candidate_result),
                "paper_cost_after": paper_cost(refined),
                "injected": selected is refined,
                "runtime": refined["runtime_seconds"],
                **_hybrid_local_summary(refined),
            }
        )

    best["method"] = method_name
    best["runtime_seconds"] = time.perf_counter() - start
    best["notes"] = (
        "GA+ALNS stagnation-triggered refinement: evolves a GA candidate pool, "
        "calls vehicle-preserving ALNS only when improvement stalls or diversity becomes low, "
        "and injects random immigrants when refinement fails."
    )
    best["hybrid_details"] = {
        "hybrid_mode": "stagnation_triggered_refinement",
        "diverse_candidate_generation": diverse_candidates,
        "comparison_mode": comparison_mode,
        "candidate_types": ",".join(sorted({str(row.get("candidate_type", "balanced")) for row in candidates})),
        "selected_candidate_types": ",".join(str(row.get("candidate_type", row.get("result", {}).get("metadata", {}).get("hybrid_candidate_type", "balanced"))) for row in final_selected),
        "stagnation_trigger_count": stagnation_trigger_count,
        "stagnation_selected_elites": stagnation_selected_elites,
        "stagnation_injected_count": stagnation_injected_count,
        "stagnation_rejected_count": stagnation_rejected_count,
        "stagnation_immigrant_count": stagnation_immigrant_count,
        "stagnation_best_before": stagnation_best_before,
        "stagnation_best_after": _display_cost(best),
        "stagnation_batches": ",".join(str(value) for value in stagnation_batches),
        "population_diversity_before": population_diversity_before,
        "population_diversity_after": population_diversity_after,
        "alns_called_due_to_no_improvement": alns_called_due_to_no_improvement,
        "alns_called_due_to_low_diversity": alns_called_due_to_low_diversity,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(final_selected),
        "ga_time_budget_seconds": evolution_budget,
        "stagnation_alns_time_budget_seconds": stagnation_budget,
        "alns_time_budget_seconds": final_refine_budget,
        "total_runtime": best["runtime_seconds"],
        "improvement_percentage": hybrid_improvement_percentage(initial_best_result, best),
        "paper_cost_before": paper_cost(initial_best_result),
        "paper_cost_after": paper_cost(best),
        "paper_distance_improved": float(best.get("total_distance", 0.0)) < float(initial_best_result.get("total_distance", 0.0)),
        "paper_cost_improved": paper_cost(best) < paper_cost(initial_best_result),
        "accepted_by_paper_rule": comparison_mode == "paper_cost_priority" and paper_cost(best) < paper_cost(initial_best_result),
        "rejected_by_cost_rule": comparison_mode == "paper_cost_priority" and paper_cost(best) >= paper_cost(initial_best_result),
        "selected_source": "hybrid_stagnation",
        "vehicle_preserving_refine": True,
        "hybrid_refine_profile": alns_profile,
        "stagnation_details": stagnation_details,
        "candidate_details": final_details,
        **_sum_hybrid_local_summaries(stagnation_details + final_details),
    }
    return best


HYBRID_LOCAL_FIELDS = [
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
]


def _hybrid_refine_profile(kwargs: dict[str, Any], preserve_vehicle: bool, default_local: bool = False) -> str:
    explicit_profile = kwargs.get("alns_refine_profile") or kwargs.get("hybrid_alns_profile")
    if explicit_profile:
        return str(explicit_profile)
    if bool(kwargs.get("hybrid_local_refine", default_local)):
        return "alns_hybrid_local"
    if preserve_vehicle:
        return "alns_hybrid_preserve"
    return "alns_hybrid_refine"


def _hybrid_refine_iterations(instance: dict, candidate_budget: float, diverse_candidates: bool = False) -> int:
    customer_count = len(instance.get("customers", []))
    if diverse_candidates:
        base = 4 if customer_count <= 10 else 6 if customer_count <= 25 else 8
    else:
        base = 8 if customer_count <= 10 else 12 if customer_count <= 25 else 16
    return max(1, min(base, int(max(1.0, candidate_budget) * 2)))


def _hybrid_local_summary(result: dict[str, Any]) -> dict[str, int]:
    diagnostics = result.get("alns_diagnostics", {})
    return {field: int(diagnostics.get(field, 0) or 0) for field in HYBRID_LOCAL_FIELDS}


def _sum_hybrid_local_summaries(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals = {field: 0 for field in HYBRID_LOCAL_FIELDS}
    for row in rows:
        for field in HYBRID_LOCAL_FIELDS:
            totals[field] += int(row.get(field, 0) or 0)
    return totals


def _display_cost(result: dict[str, Any]) -> float:
    return float(result.get("total_distance", 0.0)) + float(result.get("charging_time", 0.0))


def _select_refined_for_candidate(candidate_result: dict[str, Any], refined_result: dict[str, Any], comparison_mode: str) -> dict[str, Any]:
    """Apply the final Hybrid acceptance rule for one GA candidate."""
    if candidate_result.get("feasible") and int(refined_result.get("vehicle_count", 1)) > int(candidate_result.get("vehicle_count", 1)):
        return candidate_result
    if comparison_mode == "paper_cost_priority" and candidate_result.get("feasible"):
        if not refined_result.get("feasible"):
            return candidate_result
        if int(refined_result.get("vehicle_count", 1)) > int(candidate_result.get("vehicle_count", 1)):
            return candidate_result
        cost_improved = paper_cost(refined_result) < paper_cost(candidate_result) - 1e-9
        distance_improved = float(refined_result.get("total_distance", 0.0)) < float(candidate_result.get("total_distance", 0.0)) - 1e-9
        if cost_improved or distance_improved:
            return compare_hybrid_results(candidate_result, refined_result, comparison_mode=comparison_mode)
        return candidate_result
    return compare_hybrid_results(candidate_result, refined_result, comparison_mode=comparison_mode)


def _result_rank(result: dict[str, Any]) -> tuple[float, float, float, float, float, float, float]:
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


def _rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(candidates, key=lambda candidate: _result_rank(candidate["result"]))
    for rank, candidate in enumerate(ranked, start=1):
        candidate["ga_rank"] = rank
        if candidate["result"].get("metadata") is None:
            candidate["result"]["metadata"] = {}
        candidate["result"]["metadata"]["hybrid_candidate_rank"] = rank
    return ranked


def _population_diversity(candidates: list[dict[str, Any]]) -> float:
    selected = candidates[: min(8, len(candidates))]
    if len(selected) < 2:
        return 0.0
    similarities = []
    for i, left in enumerate(selected):
        for right in selected[i + 1 :]:
            similarities.append(solution_similarity(left["solution"], right["solution"]))
    if not similarities:
        return 0.0
    return 1.0 - sum(similarities) / len(similarities)


def _refine_rejected_reason(before: dict[str, Any], after: dict[str, Any], selected_source: str) -> str:
    if selected_source == "alns_refine":
        return ""
    if int(after.get("vehicle_count", 1)) > int(before.get("vehicle_count", 1)):
        return "vehicle_count_increased"
    if before.get("feasible") and not after.get("feasible"):
        return "refined_infeasible"
    if _result_rank(after) >= _result_rank(before):
        return "lexicographic_not_improved"
    return "not_selected"


def has_stagnated(no_improvement_batches: int, stagnation_limit: int) -> bool:
    return no_improvement_batches >= max(1, stagnation_limit)


def _trigger_reason(trigger_no_improvement: bool, trigger_low_diversity: bool) -> str:
    if trigger_no_improvement and trigger_low_diversity:
        return "no_improvement_and_low_diversity"
    if trigger_no_improvement:
        return "no_improvement"
    if trigger_low_diversity:
        return "low_diversity"
    return ""


def _default_hybrid_budget(instance: dict) -> float:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        return 10.0
    if customer_count <= 10:
        return 30.0
    if customer_count <= 25:
        return 120.0
    if customer_count <= 50:
        return 240.0
    return 300.0


def _split_time_budget(instance: dict, total_budget: float) -> tuple[float, float]:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        preferred = (7.0, 3.0)
    elif customer_count <= 10:
        preferred = (22.0, 8.0)
    elif customer_count <= 25:
        preferred = (90.0, 30.0)
    elif customer_count <= 50:
        preferred = (190.0, 50.0)
    else:
        preferred = (240.0, 60.0)
    preferred_total = sum(preferred)
    if total_budget <= 0:
        return preferred
    scale = total_budget / preferred_total
    return max(1.0, preferred[0] * scale), max(1.0, preferred[1] * scale)


def _split_topk_time_budget(instance: dict, total_budget: float) -> tuple[float, float]:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        preferred = (6.0, 4.0)
    elif customer_count <= 10:
        preferred = (18.0, 12.0)
    elif customer_count <= 25:
        preferred = (75.0, 45.0)
    elif customer_count <= 50:
        preferred = (160.0, 80.0)
    else:
        preferred = (210.0, 90.0)
    preferred_total = sum(preferred)
    if total_budget <= 0:
        return preferred
    scale = total_budget / preferred_total
    return max(1.0, preferred[0] * scale), max(1.0, preferred[1] * scale)


def _split_periodic_time_budget(instance: dict, total_budget: float) -> tuple[float, float, float]:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        preferred = (6.0, 2.0, 2.0)
    elif customer_count <= 10:
        preferred = (18.0, 6.0, 6.0)
    elif customer_count <= 25:
        preferred = (70.0, 25.0, 25.0)
    elif customer_count <= 50:
        preferred = (150.0, 45.0, 45.0)
    else:
        preferred = (190.0, 55.0, 55.0)
    preferred_total = sum(preferred)
    if total_budget <= 0:
        return preferred
    scale = total_budget / preferred_total
    return max(1.0, preferred[0] * scale), max(1.0, preferred[1] * scale), max(1.0, preferred[2] * scale)


def _split_stagnation_time_budget(instance: dict, total_budget: float) -> tuple[float, float, float]:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        preferred = (6.0, 2.0, 2.0)
    elif customer_count <= 10:
        preferred = (18.0, 6.0, 6.0)
    elif customer_count <= 25:
        preferred = (75.0, 25.0, 20.0)
    elif customer_count <= 50:
        preferred = (150.0, 50.0, 40.0)
    else:
        preferred = (190.0, 60.0, 50.0)
    preferred_total = sum(preferred)
    if total_budget <= 0:
        return preferred
    scale = total_budget / preferred_total
    return max(1.0, preferred[0] * scale), max(1.0, preferred[1] * scale), max(1.0, preferred[2] * scale)


def _default_periodic_batches(instance: dict) -> int:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        return 2
    if customer_count <= 10:
        return 3
    if customer_count <= 25:
        return 4
    return 5


def _initial_periodic_candidate_limit(instance: dict) -> int:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 10:
        return 12
    if customer_count <= 25:
        return 8
    return 6


def _periodic_expansion_count(instance: dict) -> int:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 10:
        return 4
    if customer_count <= 25:
        return 2
    return 1


def _periodic_alns_runtime(instance: dict) -> float:
    customer_count = len(instance.get("customers", []))
    if customer_count <= 5:
        return 1.0
    if customer_count <= 10:
        return 3.0
    if customer_count <= 25:
        return 8.0
    return 15.0
