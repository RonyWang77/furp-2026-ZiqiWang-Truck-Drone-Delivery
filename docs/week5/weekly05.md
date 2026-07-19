# Weekly Report: GA+ALNS Development and Future Truck-Drone E-VRPTW-NL Modeling

## 1. Overview

This week, the work focused on two major directions.

First, we systematically improved the GA+ALNS hybrid algorithm for the current E-VRPTW reproduction framework. The goal was not to assume that GA+ALNS must outperform GA or ALNS, but to test whether different forms of hybridization can actually improve solution quality under the same evaluator and feasibility checker.

Second, based on the current E-VRPTW work and the previous discussion of ETRD-NL, we further discussed how to extend the research problem toward a truck-drone collaborative E-VRPTW-NL problem. This future problem will include electric truck routing, drone cooperation, time windows, battery constraints, charging stations, nonlinear charging, full recharge, and partial recharge.

The GA+ALNS development process can be divided into seven stages:

| Stage | Main Purpose |
|---|---|
| Stage0 | Build the basic GA+ALNS post-processing framework |
| Stage1 | Analyze why simple GA+ALNS does not improve GA |
| Stage2 | Add diagnostic logging |
| Stage3 | Strengthen destroy operators |
| Stage4 | Strengthen repair operators |
| Stage5 | Add local search |
| Stage6 | Add Top-K multi-start candidate selection |
| Stage7 | Add deeper hybrid modes: periodic and stagnation-triggered ALNS |

The current numerical results mainly come from a small smoke benchmark:

| Item | Value |
|---|---|
| Dataset | R101 |
| Customers | 10 |
| Instance seed | 1987 |
| Solver seed | 42 |
| Runs per method | 1 |
| Time budget | 10 seconds |
| Hybrid time split | GA 7s + ALNS 3s |

Therefore, the current results should be interpreted as preliminary evidence. They are useful for debugging and early comparison, but they are not yet sufficient for final statistical conclusions.

---

# 2. Stage-by-Stage Algorithm Development

---

## Stage0: Basic GA+ALNS Framework

### 2.0.1 Motivation

The starting point was the observation that Basic GA can generate feasible E-VRPTW routes, but it may lack strong local improvement ability. GA searches globally through customer permutations, crossover, and mutation. However, after a feasible route is produced, GA does not naturally perform detailed local restructuring such as moving customers across routes, merging routes, or repairing time-window conflicts in a targeted way.

ALNS, on the other hand, is naturally designed for large neighborhood search. It can destroy part of a solution and repair it using heuristic insertion rules. Therefore, the first hypothesis was:

> GA can provide a good global solution structure, and ALNS can refine it locally.

The expected benefit was that ALNS would improve the GA best solution after GA finishes.

### 2.0.2 Algorithm Changes

A new independent hybrid module was created:

```text
EVRPTW_Schneider2014/
  algorithms/
    hybrid_ga_alns/
      config.py
      solution_adapter.py
      hybrid_solver.py
      run_experiment.py
      verify_minimal.py
      README.md
```

| File | Modification |
|---|---|
| `config.py` | Added default parameters for GA and ALNS |
| `solution_adapter.py` | Added conversion between GA individual, routes, and ALNS state |
| `hybrid_solver.py` | Added `solve_basic_ga`, `solve_basic_alns`, and `solve` |
| `run_experiment.py` | Added a unified script to compare Basic GA, Basic ALNS, and GA+ALNS |
| `verify_minimal.py` | Added a minimal validation script |

The basic GA+ALNS process was:
GA population initialization
-> GA selection, crossover, mutation
-> GA best individual
-> convert individual to routes
-> convert routes to ALNS state
-> ALNS destroy/repair
-> evaluate ALNS result
-> return better feasible solution
