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

The basic GA+ALNS process was:<br>
GA population initialization<br>
-> GA selection, crossover, mutation<br>
-> GA best individual<br>
-> convert individual to routes<br>
-> convert routes to ALNS state<br>
-> ALNS destroy/repair<br>
-> evaluate ALNS result<br>
-> return better feasible solution<br>


### 2.0.3 Results
| Method | Best Cost | Average Cost | Vehicles | Travel Distance | Charging Count | Feasible Rate | Runtime | Std Cost | Improvement |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Basic GA | 884.611 | 884.611 | 7 | 430.621 | 0 | 100% | 0.217s | 0.000 | - |
| Basic ALNS | 884.611 | 884.611 | 7 | 430.621 | 0 | 100% | 10.024s | 0.000 | 0.000% |
| GA+ALNS Stage0 | 884.611 | 884.611 | 7 | 430.621 | 0 | 100% | 3.265s | 0.000 | 0.000% |

### 2.0.4 Discussion
The simplest GA+ALNS structure did not improve the GA solution. This means that simply connecting GA and ALNS is not enough. The ALNS post-processing stage received the GA best solution, but it failed to find a better feasible route.<br>
Possible explanations:<br>
The GA solution was already locally optimal under the current ALNS neighborhood.<br>
The ALNS destroy operators were too weak.<br>
The ALNS repair operators reconstructed a solution similar to the original GA solution.<br>
The objective function may have made small structural improvements invisible.<br>
ALNS was only applied to one best solution, so the search starting point lacked diversity.<br>

### 2.1-2.2 Stage1&2: Bottleneck Analysis & Diagnostic Logging
After Stage0, the hybrid method produced no improvement. Therefore, the next step was not to blindly increase iterations, but to analyze the bottleneck.

Possible bottlenecks included:<br>
Initial solution already locally optimal<br>
Destroy too weak<br>
Repair too conservative<br>
No route merge<br>
ALNS budget too small<br>
GA and ALNS behavior too similar<br>
Objective function hides real improvement<br>

| Component | Purpose |
|---|---|
| GA individual | Check representation |
| GA repair | Check route generation behavior |
| ALNS state | Check route/unassigned structure |
| Destroy operators | Check removal logic |
| Repair operators | Check insertion logic |
| GA+ALNS adapters | Check information loss during conversion |

### 2.3-2.4 Stage3: Enhanced Destroy Operators & Stage4: Enhanced Repair Operators
The previous stages showed that basic destroy operators were too weak. If destroy only removes random customers or simple route segments, ALNS may repeatedly repair back to similar routes.<br>
Stage3 aimed to create more meaningful destruction patterns.<br>

Destroy alone cannot improve solutions if repair is too conservative. Previous results suggested that routes were often reconstructed into similar structures. Stage4 aimed to make repair more intelligent.

### 2.3.1 Algorithm Changes:
| Operator | Purpose |
|---|---|
| `worst_cost_removal` | Remove customers with high marginal cost |
| `related_removal` | Remove spatially/time-related customers |
| `time_window_critical_removal` | Remove customers causing tight time-window pressure |
| `energy_critical_removal` | Remove customers causing energy pressure |
| `route_removal` | Remove one route to encourage vehicle reduction |
| `cluster_removal` | Remove geographic cluster |

### 2.3.2 Results and Comparision
| Method | Best Cost | Avg Cost | Vehicle Count | Travel Distance | Charging Count | Feasible Rate | Runtime | Std Cost | Improvement |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GA+ALNS strengthened | 881.900 | 881.900 | 7 | 473.646 | 0 | 100% | 5.542s | 0.000 | 0.306% |

| Metric | Stage2 | Stage3 Evidence | Change |
|---|---:|---:|---:|
| Cost | 884.611 | 881.900 | Improved |
| Vehicles | 7 | 7 | No change |
| Distance | 430.621 | 473.646 | Worse |
| Runtime | 3.265s | 5.542s | Increased |
| Feasible Rate | 100% | 100% | Same |

| Metric | Previous simple post-processing | Strengthened repair evidence |
|---|---:|---:|
| Improvement rate | 0.000 | Positive for several repair operators |
| Best cost | 884.611 | 881.900 |
| Vehicle count | 7 | 7 |

### 2.3.3 Discussion
The most effective destroy operator was time_window_critical_removal. This is important because E-VRPTW is heavily constrained by time windows. Destroying time-critical customers gives repair more opportunity to reduce waiting time and improve schedule feasibility.<br>
route_removal did not work in this run. It was expected to help reduce vehicles, but the final vehicle count remained 7. This suggests that removing a whole route is not enough; repair must also be strong enough to insert those customers into other routes.<br>

Repair was likely more important than destroy in producing the final improvement. In particular, regret-style repair and greedy min-cost insertion showed measurable success.<br>
However, vehicle_reduction_insertion did not reduce the final vehicle count. This suggests that vehicle reduction requires not only insertion but also stronger route merge or route compression logic.<br>
energy_aware_insertion had no effect in the current instance, probably because this smoke instance did not require charging. It may become more important in larger or more energy-constrained instances.<br>

### 2.5-2.7 Adding Local Search and Top-K Multi-start to get Deep Hybrid GA+ALNS
Destroy and repair can reconstruct routes, but they may still miss small route-level improvements. Stage5 added local search to improve route geometry and route assignment after ALNS repair.<br>
Single-best post-processing may fail because the GA best solution is not the best starting point for ALNS. A slightly worse but structurally different GA individual may be easier for ALNS to improve.<br>
Stage6 introduced Top-K diverse candidate selection.<br>
Post-processing may be too late: once GA has converged, ALNS receives only final solutions and cannot influence the population. Stage7 introduced deeper fusion modes.

### 2.5.1 Results
| Metric | Single-best | Top-K | Change |
|---|---:|---:|---:|
| Cost | 884.611 | 884.611 | 0 |
| Vehicles | 7 | 7 | 0 |
| Runtime | 3.265s | 3.559s | +0.294s |
| Feasible Rate | 100% | 100% | 0 |
The idea of Top-K is algorithmically reasonable, but the current result does not prove its effectiveness. The likely reason is that selected candidates were not structurally different enough, or ALNS still lacked strong enough operators to exploit the diversity.

### 3. Overall Comparision
| Method | Best Cost | Avg Cost | Vehicles | Runtime | Feasible Rate |
|---|---:|---:|---:|---:|---:|
| GA | 884.611 | 884.611 | 7 | 0.217s | 100% |
| ALNS | 884.611 | 884.611 | 7 | 10.024s | 100% |
| GA+ALNS Stage0 | 884.611 | 884.611 | 7 | 3.265s | 100% |
| GA+ALNS Stage1 | 884.611 | 884.611 | 7 | 3.265s | 100% |
| GA+ALNS Stage2 | 884.611 | 884.611 | 7 | 3.265s | 100% |
| GA+ALNS Stage3 | 881.900 | 881.900 | 7 | 5.542s | 100% |
| GA+ALNS Stage4 | 881.900 | 881.900 | 7 | 5.542s | 100% |
| GA+ALNS Stage5 | 881.900 | 881.900 | 7 | 5.542s | 100% |
| GA+ALNS Stage6 | 884.611 | 884.611 | 7 | 3.559s | 100% |
| GA+ALNS Stage7 Periodic | 884.611 | 884.611 | 7 | 0.202s | 100% |
| GA+ALNS Stage7 Stagnation | 884.611 | 884.611 | 7 | 0.231s | 100% |

| Rank | Change | Contribution |
|---:|---|---|
| 1 | Repair operators | Most direct evidence of improvement |
| 2 | Time-window critical destroy | Highest destroy success rate |
| 3 | Regret repair | Highest repair success rate among key operators |
| 4 | Diagnostics | Crucial for explaining failures |
| 5 | Strengthened ALNS combined version | Only version with visible cost improvement |
| 6 | Top-K multi-start | Useful framework, but no current improvement |
| 7 | Periodic/Stagnation hybrid | Useful framework, but no current improvement |
| 8 | Route merge | Conceptually important, but weak current evidence |

Compared with the original GA, the proposed hybrid algorithm provides several advantages.

1.Stronger exploration and exploitation balance:

GA performs global exploration by evolving a population of solutions, while ALNS focuses on intensive local improvement.

The combination achieves a better balance between exploration and exploitation.

Better capability for handling complex constraints

The destroy-and-repair mechanism of ALNS makes it easier to incorporate additional constraints, such as:

time windows,
battery capacity,
charging stations,
vehicle capacity,
truck-drone synchronization (future work),
nonlinear charging constraints (future work).

Therefore, the hybrid framework has better scalability than the original GA.

2.Improved solution quality:

Instead of stopping after GA evolution, the algorithm performs an additional local optimization stage, which provides more opportunities to escape local optima and improve routing quality.

3.Higher extensibility:

The hybrid architecture is modular.

Future neighborhood operators can be added without redesigning the GA framework, making the method suitable for increasingly complex EVRP variants.

### 4. Future Research Direction: Truck-Drone Collaborative E-VRPTW-NL
### 4.1 Problem Extension
The next research goal is to extend the current E-VRPTW into:
Truck-Drone Collaborative E-VRPTW-NL

This problem combines:<br>
Electric truck routing<br>
Drone-assisted delivery<br>
Customer time windows<br>
Truck battery constraints<br>
Drone battery constraints<br>
Charging stations<br>
Linear charging<br>
Nonlinear charging<br>
Full recharge<br>
Partial recharge<br>
Truck-drone synchronization<br>

The future experiments should compare four charging modes.
| Mode | Charging Curve | Recharge Policy |
|---|---|---|
| LC-FR | Linear charging | Full recharge |
| LC-PR | Linear charging | Partial recharge |
| NLC-FR | Nonlinear charging | Full recharge |
| NLC-PR | Nonlinear charging | Partial recharge |

### 5. Conclusion
This week’s work shows that GA+ALNS should not be considered automatically superior to GA or ALNS. The simplest post-processing version did not improve GA. The strengthened ALNS version produced a small improvement, but it also increased runtime and travel distance.<br>
The main contribution of this week is the construction of a more complete experimental and diagnostic framework. This framework makes it possible to compare different hybrid mechanisms fairly and identify which operators are actually useful.<br>
For future work, the research direction should move from simple truck-only E-VRPTW toward truck-drone collaborative E-VRPTW-NL. The key modeling challenges will be drone launch/recovery, truck-drone synchronization, drone battery constraints, nonlinear charging, and partial recharge decisions.
