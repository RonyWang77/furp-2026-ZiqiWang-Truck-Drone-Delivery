# Experimental Report: Truck-Drone EVRPTW-NL



## Evidence Coverage Statement

This report uses three evidence levels. **Controlled final evidence** refers to the final 25-customer 108-run matrix and is the only basis for formal performance claims. **Developmental evidence** refers to 5/10/25/50-customer stage experiments, method logs, Hybrid audits, and smoke tests; it explains why the algorithms evolved but is not treated as a controlled ablation unless explicitly stated. **Diagnostic evidence** refers to operator calls, accepted/improved counts, violation fields, runtime outliers, candidate diagnostics, and petal/crossing metrics; it is used to explain mechanisms. The main sources are `final_model_freeze_spec.md`, final code, final CSV/JSONL results, `ga_development_report.md`, `alns_development_report.md`, `hybrid_development_report.md`, `hybrid_stage6_report.md`, `hybrid_final_audit.md`, `hybrid_final_25_smoke_audit.md`, `petal_route_design_report.md`, and `modeling_and_progress.md`.

## 1. Executive Summary

The research focus is **constraint-aware metaheuristic solution and computational analysis for a unified Truck-Drone EVRPTW-NL**. The final problem couples truck routing, drone service assignment, hard time windows, truck and drone energy propagation, launch-recovery synchronization, charging-station decisions, and four charging policies: LFC, LPC, NFC, and NPC.

The final 25-customer controlled experiment contains 108 runs across C101/R101/RC101, GA/ALNS/Hybrid, LFC/LPC/NFC/NPC, and three seeds. In the controlled final evidence, ALNS has the highest feasible rate at 75.0%, Hybrid follows at 72.222%, and GA reaches 66.667%. GA uses fewer feasible vehicles on average (7.666667) than Hybrid (7.884615) and ALNS (8.888889). ALNS obtains the shortest feasible total distance on average (874.735865), while Hybrid obtains the lowest feasible paper cost (1232.753151) and the most stable runtime median/mean profile (63.404685s / 62.724606s). These results do not support a universal winner; they support a search-behavior interpretation.

Developmental evidence explains why. Early algorithms generated rough routes and relied heavily on shared simulation/evaluation. That made feasibility less attributable to each algorithm and weakened Hybrid complementarity. GA therefore moved toward structured representation and constraint-aware decoding. ALNS moved from generic removal/insertion toward time, energy, drone, charging, spatial, and local diagnostic operators. Hybrid moved from naive GA-best refinement to Top-K, vehicle-preserving refinement, periodic/stagnation triggering, local neighborhoods, and finally diverse candidate generation. The final 108-run matrix tests these accumulated design decisions; it does not erase the negative development evidence. Hybrid is competitive, especially in paper cost, but it still does not dominate GA or ALNS.

## 2. Research Questions

RQ1 asks how GA and ALNS became constraint-aware rather than generic routing methods. RQ2 compares final search behavior and trade-offs. RQ3 studies C/R/RC sensitivity. RQ4 studies the 2 x 2 charging-policy design. RQ5 studies when Hybrid improves or fails. RQ6 studies computational robustness and runtime heavy tails. These questions are interpreted through the three evidence levels defined above.

## 3. Literature and Research Context

This study sits at the intersection of four research streams rather than inside a single established benchmark. Solomon's VRPTW work introduced heterogeneous C, R, and RC spatial structures and showed that time-window placement changes heuristic behavior (Solomon, 1987). Schneider, Stenger, and Goeke added electric-vehicle energy propagation and intermediate recharging stations to VRPTW (Schneider, Stenger and Goeke, 2014). Montoya et al. modeled SOC-dependent charging duration, while Keskin and Catay treated charging amount as a route decision rather than assuming every stop restores a full battery (Keskin and Çatay, 2016; Montoya et al., 2017). Truck-drone research introduced service assignment and launch/recovery synchronization; the Flying Sidekick TSP is an early canonical example, and later reviews document the breadth of this family (Liang and Luo, 2022; Macrina et al., 2020; Murray and Chu, 2015). ALNS supplies the adaptive destroy-repair principle used here (Pisinger and Ropke, 2007; Ropke and Pisinger, 2006). The project-local ETRD-NL source is now identified as a truck-based robot problem with nonlinear charging (Yu, Zhu and Puchinger, 2026); it is a modeling influence, not evidence that the present truck-drone formulation is identical or first.

The closest streams solve important subsets. EVRPTW studies typically model an electric road vehicle, time windows, and recharging but not a coordinated drone mission. Truck-drone studies model service assignment and synchronization but often omit electric-truck charging or treat endurance as a simple sortie limit. Nonlinear and partial-charging EVRP studies make charging amount and SOC-dependent duration decisions but generally do not combine them with multi-customer drone routes and recovery synchronization. Metaheuristic studies explain GA population search, ALNS neighborhood adaptation, or hybridization, but their generic mechanisms do not themselves encode this project's coupled feasibility conditions.

| Research stream | TW | Electric truck | Drone/auxiliary route | Synchronization | Nonlinear/partial charging | Relation to this study |
|---|---:|---:|---:|---:|---:|---|
| Solomon VRPTW | Yes | No | No | No | No | Instance structure and hard-window basis |
| Schneider E-VRPTW | Yes | Yes | No | No | Recharging, not this four-policy design | Truck energy/station basis |
| Flying Sidekick TSP | Usually not Solomon TW | No | Yes | Yes | No | Launch/recovery and collaboration basis |
| Nonlinear/partial EVRP | Usually | Yes | No | No | Explicit | Charging-law and charging-target basis |
| ETRD-NL project source | Yes | Energy-constrained | Ground robot | Yes | Nonlinear emphasis | Closest project-local auxiliary-vehicle influence |
| Final Truck-Drone EVRPTW-NL | Yes | Yes | Multi-customer drone | Yes | LFC/LPC/NFC/NPC | Unified computational problem studied here |

The defensible research gap is therefore integration and computational adaptation, not an unverified claim of being the first model. The report investigates how generic GA and ALNS mechanisms must change when customer assignment, truck routing, drone missions, two energy states, charging amount, and synchronization are evaluated together; it then tests how the resulting methods behave across instance structures and charging policies. A broader systematic review would be required before asserting novelty beyond this carefully bounded claim.

## 4. Problem Motivation

A VRP chooses routes and customer order. A VRPTW additionally chooses feasible service times: an edge that shortens distance may push every downstream customer beyond its due time (Solomon, 1987). EVRPTW adds state of charge (SOC), station choice, and charging duration (Schneider, Stenger and Goeke, 2014). Truck-drone routing adds a service-mode decision, launch and recovery positions, and two clocks that must meet (Macrina et al., 2020; Murray and Chu, 2015). Partial and nonlinear charging make the target SOC itself consequential because charging one extra unit near high SOC may consume more time than at low SOC (Keskin and Çatay, 2016; Montoya et al., 2017).

The coupling is causal rather than additive. Reassigning customer (i) from truck to drone removes a truck detour but changes the truck's arrival at launch and recovery. It also creates a drone sequence with its own capacity, time windows, SOC, and possible station visits. Whichever vehicle arrives first at recovery waits; that wait shifts all later truck services and may create a time-window violation. A charging stop can restore energy feasibility while destroying temporal feasibility. Consequently, a route cannot be judged by distance alone, and feasibility cannot reliably be bolted on after the route has been generated.

Operationally, the truck provides capacity, range, and a moving launch/recovery platform; the drone can remove expensive local detours. The benefit is conditional: a drone mission is useful only if saved truck distance exceeds drone travel, charging, and synchronization costs without violating hard constraints. This explains the study's central methodological choice. Generic permutation search or generic insertion neighborhoods are retained as search principles, but the representation, decoder, state, operators, and acceptance rules are made constraint-aware.

Figure A1 summarizes the physical entities. It is schematic and does not claim that the saved route shown elsewhere is optimal.

![Final Truck-Drone EVRPTW-NL problem schematic](assets/figures/A1_problem_schematic.png)

*Figure A1. Problem schematic. Source: frozen model specification. Supported conclusion: the model couples truck routes, drone missions, stations, time, and energy. Unsupported conclusion: the schematic does not establish performance or optimality.*

## 5. Final Mathematical Model and Coupling Logic

The following is a conceptual mathematical representation of the implemented problem. The solvers do not solve this formulation as a MILP; they manipulate structured solution objects, while `route_simulator.py` propagates state and `evaluator.py` performs final checks.

### 5.1 Sets, indices, and parameters

Let $C$ be customers, $F$ existing charging stations, $0$ the depot, and $N=C\cup F\cup\{0\}$. Let $K$ index truck routes and $M_k$ the ordered drone missions attached to route $k$. Parameters include Euclidean distance $d_{ij}$, vehicle-specific travel time $t^v_{ij}=d_{ij}/s_v$, demand $q_i$, time window $[e_i,l_i]$, service time $s_i$, capacities $Q_T,Q_D$, batteries $B_T,B_D$, and distance-energy rates $\rho_T,\rho_D$. Charging uses linear rate $r_L$, SOC-segment rates $r_h$, and safety margin $\delta$.

Conceptually, $x^T_i,x^D_i\in\{0,1\}$ indicate truck or drone service; $y^k_{ij}$ indicates a truck arc; $z^m_{ij}$ a drone-mission arc; $a_i^v,b_i^v$ arrival and service-start times; $E_i^v$ arrival energy; and $g_i^v$ charged energy. In code these are reconstructed states, not optimization variables stored in a mathematical-programming model.

### 5.2 Service, route, and capacity constraints

Every customer is served exactly once:

$$
x_i^T+x_i^D=1,\qquad i\in C.
$$

Without this condition an apparently short solution could omit or duplicate a customer. `_check_customer_coverage` records `customer_missing`, `customer_duplicate`, and `customer_coverage`; this is a hard constraint and final evaluator check.

Each nonempty truck route starts and ends at the depot, $R_k=(0,\ldots,0)$, and its consecutive arcs form a continuous sequence. Route load satisfies

$$
\sum_{i\in R_k\cap C} q_i\le Q_T.
$$

For mission $m$, the served demand satisfies

$$
\sum_{i\in P_m\cap C}q_i\le Q_D.
$$

Without these constraints a route could begin in mid-network or load more freight than the assigned vehicle. The simulator's route and capacity checks accumulate `truck_route` and `capacity` violations.

### 5.3 Drone mission structure

A mission is $m=(k,\ell_m,P_m,r_m)$, where launch $\ell_m$ and recovery $r_m$ occur on the same truck route $R_k$, with truck positions satisfying

$$
\operatorname{pos}_{R_k}(\ell_m)<\operatorname{pos}_{R_k}(r_m).
$$

The stored `drone_route` starts at launch, ends at recovery, and may contain multiple customers and existing stations. Drone-served customers are removed from truck service. Missions belonging to one route must not overlap in truck-route order. Without these rules the drone could be recovered before launch, recovered by another truck, or serve a customer twice. `_check_drone_tasks` records `drone_mission`; cross-truck recovery is outside the frozen model.

### 5.4 Time windows and synchronization

For vehicle $v\in\{T,D\}$, state propagation is

$$
a_j^v=b_i^v+s_i+t_{ij}^v+c_i^v,\qquad
b_j^v=\max(a_j^v,e_j),\qquad b_j^v\le l_j.
$$

Here $c_i^v$ is charging time when charging occurs. The final inequality is hard. Waiting $w_j^v=\max(0,e_j-a_j^v)$ is a performance metric unless it causes later infeasibility.

At recovery,

$$
b_{r_m}^{sync}=\max(a_{r_m}^{T},a_{r_m}^{D}),
$$

with truck and drone waits given by the difference from this maximum. Without synchronization the truck could depart while the drone remained airborne. Time-window excess accumulates in `time_window`; structural synchronization errors contribute to `drone_mission`.

### 5.5 Energy and charging constraints

For each traversed arc,

$$
E_j^v=E_i^v+g_i^v-\rho_vd_{ij},\qquad 0\le E_j^v\le B_v.
$$

Charging is permitted only at existing station nodes represented in the route or drone mission. The target satisfies $E_i^v\le E_i^{target}\le B_v$, and $g_i^v=E_i^{target}-E_i^v$. Without nonnegativity a route could traverse an arc after exhausting its battery. Violations are separated into `truck_battery`, `drone_battery`, and `charging`.

### 5.6 Feasibility and evaluation hierarchy

The evaluator declares a solution feasible exactly when every recorded hard-violation component is at most $10^{-6}$. Distance, vehicle count, completion, waiting, charging time, crossing count, and petal score are performance metrics rather than independent feasibility constraints. The evaluator does not impose one universal scalar objective.

GA candidate ordering uses `(feasible, vehicle_count, total_distance + charging_time)`. ALNS uses a richer feasibility-first rank and simulated-annealing scalar internally. Final diverse Hybrid uses feasibility, total violation, vehicle count, `paper_cost`, distance, completion, combined delay, and petal score lexicographically. The reported paper cost is

$$
C_{paper}=D_{total}+T_{chg}+0.25T_{wait}+0.25T_{wait}^{D}.
$$

This is a reporting and Hybrid-comparison quantity, not proof that every solver optimizes an identical single objective.

The full implementation mapping is stored in `results/report_deepening/model_code_mapping.csv`; where a constraint is anticipated during search, the shared simulator/evaluator nevertheless remains the final feasibility authority.

## 6. Mathematical Charging Model

The implementation treats charging as a $2\times2$ design. For arrival energy $E^a$, capacity $B$, required downstream energy $E^{req}$, and safety margin $\delta$, the target is

$$
E^t=\begin{cases}
B,&p\in\{LFC,NFC\},\\
\max(E^a,\min(B,E^{req}+\delta)),&p\in\{LPC,NPC\}.
\end{cases}
$$

Linear charging uses the constant-rate approximation common in early EVRPTW models (Schneider, Stenger and Goeke, 2014):

$$
T^{chg}_{lin}(E^a,E^t)=\frac{\max(0,E^t-E^a)}{r_L}.
$$

For nonlinear charging, the code sorts SOC segments by endpoint. If segment $h$ covers energy interval $[B\sigma_{h-1},B\sigma_h]$ at rate $r_h$, cumulative time is

$$
H(E)=\sum_h\frac{\max(0,\min(E,B\sigma_h)-B\sigma_{h-1})}{r_h},
\qquad
T^{chg}_{nl}=H(E^t)-H(E^a).
$$

The final configuration uses linear rate 2.0 and nonlinear low/mid/high-SOC rates 2.5, 1.4, and 0.7; therefore high-SOC charging is deliberately slower, following the routing-level motivation of nonlinear charging models (Montoya et al., 2017). This is an engineering segmented approximation, not an electrochemical battery model.

| | Full target | Partial target |
|---|---|---|
| Linear | LFC | LPC |
| Nonlinear | NFC | NPC |

Charging changes more than a charging metric. A higher target increases station residence time, shifts downstream service, can change synchronization wait, and can turn a battery-feasible route into a time-window-infeasible one. Partial charging can avoid unnecessary high-SOC time, but it may leave less energy slack and therefore does not guarantee higher feasibility.

![Charging mechanism and policy design](assets/figures/A2_charging_mechanism.png)

*Figure A2. Charging mechanism and the LFC/LPC/NFC/NPC design. Source: `charging.py` and final configuration. Supported conclusion: nonlinear high-SOC segments cost more time and partial targets can avoid them. Unsupported conclusion: the segmented curve is not a calibrated physical battery model.*

## 7. Unified Computational Framework

All final methods use the same final solution schema, simulator, evaluator, and CSV pipeline. This shared evaluator is important for fairness: GA, ALNS, and Hybrid can make different construction choices, but they are judged by the same feasibility and metric definitions. It also explains why early development had to move constraints into the algorithms. If all methods merely generated rough structures and then relied on the same downstream checks, method-specific search behavior became difficult to distinguish.

## 8. Final GA Method with Integrated Evolution

### 8.1 Core principle and actual implementation scope

Genetic algorithms search with a set of candidate individuals and variation operators. Selection exploits currently good structures; crossover and mutation explore alternative structures. Routing GAs commonly combine order evolution with route decoding or splitting (Baker and Ayechew, 2003; Prins, 2004). The final implementation follows this population-search principle, but it is not a textbook long-generation GA. `solve_ga.py` builds a bounded structured candidate pool, applies mutation and an order-preserving crossover, decodes/evaluates candidates under a time budget, and returns the best feasibility-first result. This distinction prevents overstating the implementation.

### 8.2 Individual and search space

An individual contains `customer_order`, `service_mode`, `drone_priority`, `charging_policy`, `max_vehicle_count`, `route_split_bias`, and `drone_charging_preference`. These fields are search intentions. The decoder maps them to `truck_routes`, `drone_tasks`, and `charging_plan`; arrival times and SOC are then recomputed by the shared simulator.

The search space is therefore larger than customer permutations. Order changes sequence pressure; route-split bias changes vehicle allocation; service-mode changes truck versus drone responsibility; drone priority changes grouping; charging preference changes whether a station is considered; and maximum vehicle count bounds incremental expansion. Sweep, reverse-sweep, cluster, time-window, ID, and randomized orders supply structural diversity.

Mutation toggles up to two eligible customers between truck and drone, swaps order positions, may reverse a segment, perturbs drone priorities and route-split biases, and can alter charging preference or maximum vehicles. Crossover inherits an order slice from one parent, fills missing customers in the other parent's order, and independently inherits service mode, drone priority, and split bias. Both operations can create infeasible intentions; the constraint-aware decoder and fallback prevent those intentions from becoming silently accepted illegal solutions.

### 8.3 Constraint-aware decoding

For vehicle counts $1,\ldots,V_{max}$, the decoder inserts customers into candidate routes, evaluates route consequences, materializes charging, and attempts drone replacement. It stops at the first feasible vehicle count and otherwise returns the least-ranked near-feasible solution. Drone intentions are accepted only when capacity, mission structure, energy, time windows, and synchronization survive evaluation; otherwise the customer falls back to truck service. Multi-customer drone routes may contain existing station nodes. Evaluation caching avoids recomputing identical solution structures.

This component exists because early permutation-first construction left feasibility mostly to downstream checking. Developmental R101-5 evidence reported about 40% TW feasibility and total violation around 3.086 under an earlier configuration. It is not a controlled ablation, but it motivated moving TW, energy, charging, drone, and synchronization awareness into decoding.

![Final GA workflow](assets/figures/M1_final_ga_workflow.png)

*Figure M1. Final GA workflow. Constraint-aware decoding is highlighted; the stopping decision returns to candidate generation when the budget permits. Source: final `solve_ga.py` and `ga_tools.py`.*

### 8.4 Exploration, exploitation, and ranking

Exploration comes from multiple deterministic/random orders, mode-shifted individuals, mutation, crossover, and Hybrid-specific typed candidates. Exploitation comes from feasibility-first ranking, deterministic decoding, and retention of the best evaluated candidates. Strong feasibility selection can collapse diversity; this is why the final Hybrid candidate generator explicitly creates distance-, vehicle-, TW-, drone-, charging-, petal-, and balanced-oriented candidates.

### Algorithm 1: Constraint-Aware GA

```text
Input: instance I, charging policy p, seed s, time budget tau
P <- build structured individuals from TW, sweep, cluster and random orders
P <- P union Mutate(P) union Crossover(selected parents)
E <- empty evaluated pool
for individual g in P while elapsed < tau do
    for vehicle count v = 1,...,Vmax(g) do
        S <- decode g with TW/energy/charging/drone/sync-aware construction
        S <- apply truck fallback for rejected drone intentions
        F <- shared_evaluator(I, S, p)
        retain best v-level result; break when feasible
    end for
    add (g,S,F) to E
end for
return lexicographically best evaluated result in E
```

### 8.5 Constraint responsibility and limitations

Coverage, route structure, TW, energy, charging, drone structure, and synchronization are anticipated during decoding; exact state propagation and final hard-feasibility remain shared-evaluator responsibilities. GA's constructive bias helps control vehicle count, but the bounded candidate-pool implementation provides less iterative evolutionary feedback than a full generational GA and can remain sensitive to candidate diversity and decoding cost.

## 9. Final ALNS Method with Integrated Evolution

### 9.1 Core principle and state

ALNS inherits large-neighborhood removal and reinsertion from LNS (Shaw, 1998) and selects specialized neighborhoods adaptively (Pisinger and Ropke, 2007; Ropke and Pisinger, 2006). A simulated-annealing acceptance rule permits some non-improving moves so the search is not purely greedy. The internal `ALNSState` stores station-free `clean_truck_routes`, structured `drone_tasks`, `unassigned_customers`, and metadata. Charging stations are materialized when the state is evaluated, preventing permanent station artifacts from dominating customer-level neighborhoods.

### 9.2 Complete search flow

The independent solver constructs its own initial state. Each iteration selects destroy and repair operators by weighted random choice, removes customers or tasks, repairs unassigned customers, applies configured local searches, and evaluates the result. Geometry and local feasibility filters reduce candidate volume, while the full shared evaluator remains the final judge. Current and best solutions are distinct: an accepted candidate can become current without becoming the global best.

Weights begin at 1.0. After each iteration `_update_weight` rewards accepted moves and especially new-best improvement; weighted selection therefore changes future operator probability. Temperature starts at 5% of the current objective scalar, decreases by 0.995 per iteration, and controls acceptance probability $\exp[-\max(0,\Delta)/T]$. Candidates with violation exceeding `max(10, 1.5 current_violation + 1)` are rejected. Search stops at either the iteration limit or time budget.

![Final ALNS workflow](assets/figures/M2_final_alns_workflow.png)

*Figure M2. Final ALNS workflow. “No” at the stopping decision means a new adaptive destroy-repair iteration; the long return arrow is omitted for legibility. Source: final ALNS code.*

### 9.3 Search space, exploration, and exploitation

Destroy operators provide exploration by releasing random, worst-time, charging-critical, drone-task, route, cluster, angle, crossing, or synchronization-critical structures. Repair operators exploit feasibility information through regret, TW, energy, drone, synchronization, charging, and vehicle-reduction insertion. Local search further exploits route relocation, merge, crossing removal, drone rebuilding, launch/recovery adjustment, waiting reduction, and charging cleanup. Larger or spatially clustered removal moves explore farther but increase evaluation cost.

Generic ALNS is insufficient because ordinary insertion does not know whether a customer changes two synchronized clocks or forces a station visit. A distance-improving repair can also add a route. The final operators therefore use problem-specific state, while Hybrid profiles disable or reject disruptive vehicle-count changes.

### Algorithm 2: Constraint-Aware ALNS

```text
Input: instance I, policy p, seed s, budget tau, operator profile O
X <- independent constraint-aware initial state; Xbest <- X
initialize destroy/repair weights to 1 and temperature T
while iterations remain and elapsed < tau do
    d <- weighted destroy operator; r <- weighted repair operator
    Y <- r(d(copy(X)))
    Y <- apply configured local-search operators
    evaluate Y through quick/local filters and the shared evaluator
    if violation is not excessive and SA acceptance succeeds then X <- Y
    if Y is feasibility-first better than Xbest then Xbest <- Y
    update weights from acceptance and best improvement; cool T
end while
materialize charging stations in Xbest and return shared evaluation
```

### 9.4 Constraint responsibility and limitations

Time, energy, charging, drone assignment, synchronization, vehicle count, and geometry influence operator construction or ranking. Exact multi-route timing, SOC, mission overlap, and coverage remain shared checks. This layered design improves interpretability but is expensive: many operators invoke full evaluation, and final ALNS retains a heavy runtime tail. Operator adaptivity also does not imply every operator is useful; Section 10 compares motivation with observed yield.

## 10. ALNS Operator Analysis: Motivation, Outcome, Interpretation

The diagnostics aggregate development and final-profile runs and therefore constitute **diagnostic evidence**, not a controlled ablation. A call means that an operator was attempted; an accepted result means that the operator returned a state admitted by the search logic; an improvement means that the state improved the recorded best criterion. These events are not interchangeable.

| Operator | Family | Calls | Improved | Improvement rate | Diagnostic reading |
|---|---|---:|---:|---:|---|
| H-DroneReassign | Local search | 9,098 | 1,433 | 15.75% | Highest observed yield; changes service assignment |
| LS-DroneRebuildV2 | Local search | 18,998 | 2,791 | 14.69% | High-frequency and high-yield mission reconstruction |
| LS-DroneRebuild | Local search | 7,320 | 812 | 11.09% | Earlier drone rebuild remained productive |
| D-ChargingCritical | Destroy | 5,350 | 193 | 3.61% | Targeted energy/charging disruption |
| R-EnergyAware | Repair | 7,724 | 264 | 3.42% | Feasibility-aware reinsertion has measurable yield |
| LS-CrossingRemoval | Local search | 18,261 | 65 | 0.36% | Geometry polish is rarely best-improving |
| LS-ChargingCleanup | Local search | 21,729 | 0 | 0.00% | Frequent but zero recorded best improvement |

The table is intentionally selective; full operator-level and family-level statistics remain in `results/report_deepening/alns_operator_detailed.csv` and `alns_operator_family_summary.csv`.

### 10.1 Destroy operators: targeted disruption outperforms blind disruption

Drone- and constraint-critical destroy operators provide the clearest yield. `D-DroneTask` produced 375 improvements in 10,701 calls (3.50%), `D-ChargingCritical` 193/5,350 (3.61%), `D-Crossing` 171/4,815 (3.55%), and `D-WorstTime` 210/7,530 (2.79%). By contrast, `D-Random` produced 19/2,717 (0.70%) and `D-RouteRemoval` 28/4,225 (0.66%), despite acceptance rates of 68.9% and 79.9%. The historical motivation is consistent with this outcome: once time, energy, geometry, and drone synchronization became explicit bottlenecks, removals aimed at those bottlenecks opened more useful repair neighborhoods than indiscriminate removal.

Acceptance without improvement is informative. `D-RouteRemoval` was accepted frequently but rarely improved the best state. It can generate a valid alternative while failing to reduce the lexicographic objective, and vehicle compression remains difficult because all released customers must be reinserted without creating a new route. `D-Cluster` achieved 20 improvements in 1,094 calls (1.83%), but its weighted mean runtime was 10.389s, far above the sub-second values of most destroy operators. Thus it is neither useless nor computationally attractive: its structural search is expensive relative to its observed yield.

### 10.2 Repair operators: feasibility knowledge has measurable value

`R-TWAware` achieved 329 improvements in 9,899 calls (3.32%), `R-EnergyAware` 264/7,724 (3.42%), and `R-Regret2` 262/9,434 (2.78%). These figures support the development decision to move feasibility knowledge into repair rather than ask a generic insertion to create a route and rely on downstream rejection. `R-DroneAware` improved 98/6,170 (1.59%): lower than TW/energy repair, but still evidence that service-mode decisions are reachable during repair. `R-ChargingAwareV2` accepted 153 of 194 calls but recorded no best improvement. The sample is small and the operator may preserve feasibility rather than objective quality; the data do not justify claiming that charging-aware repair is generally ineffective.

### 10.3 Local search: drone structure is the dominant productive neighborhood

The strongest local searches are explicitly drone-aware. `H-DroneReassign` improved 1,433/9,098 calls (15.75%), `LS-DroneRebuildV2` 2,791/18,998 (14.69%), and `LS-DroneRebuild` 812/7,320 (11.09%). They modify service assignment and mission structure, simultaneously changing truck detour, drone distance, launch/recovery timing, and synchronization. Their performance is consistent with a search landscape in which discrete truck-versus-drone assignment creates larger useful moves than polishing an already materialized truck route.

Route-level operators remain useful but less productive: `LS-RouteMergeV2` improved 393/13,701 (2.87%), `LS-RelocateV2` 254/21,738 (1.17%), and no-new-vehicle cross-route relocation 121/9,098 (1.33%). Geometry-only improvement is rare: `LS-CrossingRemoval` improved 65/18,261 (0.36%) and `LS-PetalPolish` 1/8,574. This supports treating petal and crossing measures as soft diagnostics rather than dominant objectives.

Several polish operators show zero recorded best improvements: `LS-ChargingCleanup` (21,729 calls), `H-ChargingPolish`, `H-WaitingReduction`, and `H-PetalPolish` (9,098 each), as does the earlier `LS-RouteMerge` (7,320 calls). Their original hypotheses were defensible: redundant stations, waiting peaks, and poor geometry can degrade a route. The diagnostic outcome suggests rare trigger conditions, overlap with materialization/evaluation, or objective misalignment. It does not prove that the code paths never preserve feasibility or improve an unreported secondary metric.

![ALNS operator effectiveness](assets/figures/G1_alns_operator_effectiveness_bubble.png)

*Figure G1. Calls versus improvement rate; bubble size reflects improved count. Source: aggregated ALNS diagnostics. Supported conclusion: drone-aware local neighborhoods provide the highest observed best-improvement yield. Unsupported conclusion: zero recorded improvement is not proof that an operator is universally unnecessary.*

The resulting method lesson is selective. Problem-aware disruption and drone reconstruction deserve emphasis; expensive low-yield clustering and zero-yield polish operators are candidates for future controlled removal studies. They are retained in the frozen implementation because the current evidence mixes profiles and stages and is not a strict operator ablation.

## 11. Final Hybrid GA-ALNS with Integrated Evolution

### 11.1 Principle and complementarity

The final Hybrid combines population-level structural exploration with selected ALNS exploitation. Hybrid genetic search research motivates combining population diversity and local improvement (Vidal et al., 2013). GA proposes different order, split, service-mode, drone, and charging intentions; ALNS then searches local neighborhoods around a small number of decoded solutions. Complementarity is plausible because the search units differ, but it is not guaranteed: shared feasibility machinery, homogeneous candidates, objective mismatch, or disruptive refinement can make the combined method equal to or worse than a component method.

### 11.2 Conversion and information preservation

`solution_to_alns_state` removes station nodes from truck routes, globally deduplicates customers, validates drone tasks, removes drone-served customers from truck routes, and records any missing customer as unassigned. It preserves truck route membership, drone route, route index, launch, recovery, and customer list. Charging plans, arrival times, SOC, waits, and traces are deliberately rebuilt during materialization; these are derived states, not trustworthy inherited decisions. This conversion protects structural information while ensuring one feasibility authority.

### 11.3 From GA-best to diverse Top-K

Naive best-only refinement assumed the best GA rank was the best ALNS start. Development contradicted this: Top-K selected rank-3 starts in R101-10 and R101-25. GA rank measures current decoded quality, whereas refinement potential depends on whether useful ALNS moves are locally reachable. Quality-only Top-K could still be homogeneous, so final Hybrid creates eight candidate orientations and selects candidates by rank, type coverage, and edge-set similarity.

ALNS refinement is vehicle-preserving for an already feasible GA candidate. This rule came from cases where distance fell only because vehicle count rose. Under `paper_cost_priority`, a feasible refined result must not add vehicles and must lower paper cost or distance before it can replace its GA source. Periodic and stagnation variants remain development evidence: their frequent zero injection showed that timing alone could not create useful neighborhoods.

![Final Hybrid workflow](assets/figures/M3_final_hybrid_workflow.png)

*Figure M3. Final diverse Top-K Hybrid. Every selected candidate is refined independently; failed feasibility, vehicle preservation, or paper-cost checks retain the original GA candidate. Source: final Hybrid code.*

### Algorithm 3: Diverse Top-K GA-ALNS Hybrid

```text
Input: instance I, policy p, seed s, total budget tau, K, similarity eta
G <- generate typed GA candidates within allocated GA budget
rank G by feasibility-first GA criterion
Q <- select up to K candidates with type coverage and edge similarity <= eta
R <- empty candidate result set
for q in Q do
    X <- convert q.solution to station-free ALNSState
    y <- vehicle-preserving ALNS refinement of X within per-candidate budget
    if y is feasible, does not add vehicles, and lowers paper cost or distance
        add y to R
    else add q to R
end for
return best member of R under paper-cost-priority rank
```

### 11.4 Exploration, exploitation, runtime, and limitations

GA candidate typing and diversity screening provide exploration across structural basins; ALNS local profiles provide exploitation inside each basin. Top-K and fixed budget splitting bound runtime. The cost is that only a few basins receive refinement and strict vehicle preservation can reject a genuine distance gain. Final evidence therefore supports conditional effectiveness, not automatic synergy.

### 11.5 Method-level comparison

| Dimension | GA | ALNS | Hybrid |
|---|---|---|---|
| Search unit | bounded population/candidate pool | one current structured state plus best state | typed GA pool plus selected ALNS states |
| Main exploration source | initialization, route split, crossover, mutation, typed diversity | destroy size, operator diversity, simulated-annealing acceptance | GA structural diversity and diverse Top-K screening |
| Main exploitation source | decoder-guided construction and selection pressure | repair, local search, adaptive operator weighting | vehicle-preserving ALNS around selected GA candidates |
| Constraint handling | decoder estimates TW, energy, drone, charging and synchronization | problem-aware destroy/repair plus layered evaluation | GA handling, state conversion, ALNS handling, final preserve/cost filters |
| Dependence on initial solution | population reduces single-start dependence | stronger dependence on constructed current state | deliberately tests several starts |
| Observed strength | fewer vehicles | feasibility and shorter distance | lower mean paper cost and bounded runtime in final matrix |
| Observed weakness | lower feasibility and heavy runtime tail | more vehicles and heavy runtime tail | conditional gain; 14 losses against GA |
| Final validation authority | shared simulator/evaluator | shared simulator/evaluator | shared simulator/evaluator |

This comparison is project-specific. It combines final implementation and controlled evidence rather than repeating generic textbook properties.

## 12. Algorithm Development History as Causal Evidence

![Method evolution causal map](assets/figures/M4_method_evolution_causal_map.png)

*Figure M4. Failure-to-design causal map. Each transition is grounded in the developmental evidence summarized below. It explains why final components exist; it is not a performance curve and does not imply that every later stage dominated every earlier stage.*

| Stage | Method | Observed problem | Hypothesis | Modification | Experiment | Before result | After result | Observed improvement | Observed degradation | Final status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GA Stage 0 | GA | Customer-order-only encoding could not express truck/drone assignment, launch/recovery, charging, or multi-vehicle structure. | A richer solution representation is required before GA can search the final Truck-Drone EVRPTW-NL space. | Move from simple customer_order to structured solution with truck_routes, drone_tasks, charging_plan. | Developmental evidence - not controlled ablation | Early GA produced infeasible cases; time-window feasibility was reported around 20-40% in user-provided diagnostics. | Later GA output could represent multi-route truck-drone charging-capable solutions. | Representation no longer blocked drone/charging/multi-vehicle modeling. | Larger search space increased decoder complexity. | Superseded by final structured GA |
| GA Stage 1-3 | GA | Drone tasks were decorative when limited to single-customer missions without station visits. | Allowing multi-customer drone_route and drone charging should make drone service a real routing decision. | Upgrade drone task to route_index + launch + drone_route + recover + customers; allow station nodes and charging_plan vehicle='drone'. | Developmental evidence - not controlled ablation | Single-customer sortie could not express realistic drone contribution. | Final raw results contain drone_tasks and truck/drone distances in 25-customer solutions. | Drone service became representable and evaluable. | Drone construction required pruning to avoid runtime explosion. | Retained in final method |
| GA Stage 4-8 | GA | Multi-customer drone and charging search created a large candidate space and could threaten runtime. | Hierarchical pruning, evaluation cache, route rebalance, specialized mutation, route split, and diversity anchors can keep GA usable at 25/50 customers. | Add layered drone search, caching, Truck-Drone mutations, incremental vehicle expansion, route-preserving crossover, and time budget. | Developmental evidence - not controlled ablation | Unbounded drone construction risked slow or infeasible outputs. | GA development report states GA can generate feasible 25/50-customer solutions, but remains conservative. | Feasibility and scale handling improved. | Vehicles and distances can be conservative. | Retained in final GA |
| ALNS Phase 1 | ALNS | Initial ALNS scaffold was not a real independent ALNS; it could not explain destroy/repair/local operator effects. | An explicit ALNSState and independent initial construction can make ALNS a fair standalone comparison method. | Add ALNSState, initial solution, D-Random/D-WorstTime/D-RouteRemoval/D-DroneTask, R-Regret/TW/Energy/Drone, and local operators. | Developmental evidence - not controlled ablation | Scaffold behavior was not comparable to final GA. | R101-5 True, 3 vehicles, distance 161.151, runtime 0.845s; R101-10 True, 3 vehicles, distance 240.500, runtime 5.497s; C101-5 and RC101-5 also True. | ALNS became independently runnable and feasible on small cases. | Quality and scale robustness were not yet sufficient. | Modified later |
| ALNS layered/petal/post-stage | ALNS | ALNS was feasible but conservative; full evaluator calls and many weak operators increased runtime. | Layered candidate evaluation and targeted operators can improve distance, crossing, drone, charging, and vehicle behavior without uncontrolled runtime. | Add route merge V2, crossing removal, drone rebuild, charging cleanup, vehicle reduction, spatial/petal metrics, and quick/local/full evaluation layers. | Developmental evidence - not controlled ablation | R101-25 alns_core True, 9 vehicles, distance 710.524, runtime 47.507s, evaluator calls 965. | Later R101-25 alns_core True, 9 vehicles, distance 643.225, runtime 45.195s, crossing successes 7; post-stage alns_full True, 10 vehicles, distance 780.638, drone tasks 4 in one snapshot. | Crossing and candidate filtering could improve route structure and distance in some profiles. | Vehicle count and drone contribution remained uneven; some improvements traded distance, vehicles, and waiting. | Retained in final ALNS with limitations |
| Hybrid Stage 1 | Hybrid | Simple GA best -> ALNS refine often failed to improve final accepted solution. | GA global search plus ALNS local refinement should be complementary. | Implement single-best post-processing from GA solution to ALNS state. | Developmental evidence - not controlled ablation | No true integration; selector simply chose GA or ALNS. | R101-5 retained GA because ALNS used more vehicles; R101-10 ALNS refine replaced GA with improvement_percentage about 0.64%; R101-25 retained GA because ALNS distance was shorter but vehicles higher. | Real conversion/refinement worked and sometimes improved. | Vehicle-count side effect blocked many refinements. | Superseded by Top-K |
| Hybrid Stage 2-2.5 | Hybrid | GA rank-1 was not always the best ALNS starting point; ALNS could reduce distance by adding vehicles. | Diverse Top-K plus vehicle-preserving refinement improves robustness. | select_diverse_top_k and preserve_vehicle_count. | Developmental evidence - not controlled ablation | Single-best refine was blocked by vehicle increases. | R101-10 Top-K selected rank 3 GA candidate; R101-25 Top-K selected rank 3; preserve kept R101-5 and R101-25 vehicle counts while accepting same-vehicle improvement on R101-10. | Candidate choice and ranking became more defensible. | Preserve rule can reject distance gains. | Retained in final Hybrid logic |
| Hybrid Stage 3-6 | Hybrid | Post-processing might be too late, but fixed ALNS triggering did not guarantee injection. | Periodic/stagnation ALNS and hybrid-local operators can inject improvements during candidate evolution. | Periodic elite improvement, stagnation-triggered ALNS, H-local operators. | Developmental evidence - not controlled ablation | Top-K alone could be limited. | R101-5 periodic injected 1 candidate; R101-25 periodic completed in about 97.2s but injection count was 0. Stagnation R101-10/25 triggered but injected 0. Stage6 summary: GA 100% feasible, 3.000 vehicles, distance 349.970; hybrid_topk 371.125; hybrid_preserve 358.810. | Hybrid-local successes existed but did not consistently change final solution. | Runtime increased and injection was often zero. | Supporting evidence |
| Hybrid Stage 7-9 | Hybrid | GA candidate pool was too homogeneous; ALNS refined similar neighborhoods. | Multi-type high-diversity candidates plus paper-cost priority can give ALNS better starts and make final ranking consistent. | distance/vehicle/TW/drone/charging/petal/balanced candidate types, hybrid_diverse_topk, paper_cost_priority. | Developmental evidence plus final controlled evidence | C101-10 hybrid_diverse_topk once had about 532s runtime before fix. | Debug: hybrid_diverse_topk 100% feasible, 2.667 vehicles, distance 344.074, paper cost 494.442, runtime 4.584s; final 108-run matrix retained for controlled conclusions. | Diverse Hybrid became the final method and fixed a major runtime pathology in debug. | 25-customer smoke: Hybrid had 7 vehicles and distance 812.254 vs GA 7 vehicles and 810.202 in one case; final audit kept non-dominance caution. | Retained in final Hybrid |
| Petal/spatial development | GA/ALNS/Hybrid metrics | Distance and vehicle count alone did not describe route shape; routes could cross or overlap spatially. | Petal/spatial soft metrics help diagnose and guide route quality without becoming hard constraints. | Add petal_score, crossing_count, route_compactness, sector_coherence, depot_radial_consistency. | Developmental evidence - not controlled ablation | R101-25 alns_core crossing_count 19 and petal_score 967.846 in one report. | Updated alns_full snapshot showed crossing_count 8 and petal_score 411.927 but vehicle_count 10 and distance 780.638. | Spatial quality improved in some snapshots. | Better spatial shape can trade off against vehicles or distance. | Retained as soft metric/diagnostic |

This matrix is developmental evidence. It explains design decisions but does not replace the controlled 108-run experiment. Its most important lesson is that each final component was introduced after a concrete failure: route representation after expression limits, constraint-aware decoding after feasibility failures, drone charging after decorative drone tasks, layered evaluation after runtime pressure, vehicle preservation after ALNS vehicle inflation, and diverse Top-K after Hybrid candidate homogeneity.

## 13. Experimental Design and Data Quality

Before the controlled matrix, the project used several scales for different research purposes. Table 13-1 and Figure B4 make this hierarchy explicit; they are an evidence map, not a cross-scale performance ranking.

| Evidence tier | Scale | Representative retained evidence | Research use | What it cannot establish |
|---|---:|---|---|---|
| Developmental | 5 | R101 feasible, 3 vehicles, distance 161.151, runtime 0.845s; C101/RC101 feasible checks | Mechanism and schema validation | Final ranking or scalability |
| Developmental | 10 | Single-best improvement about 0.64%; Top-K selected GA rank 3; C101 runtime guard case 532s to about 4.8s | Hybrid and runtime-control development | Controlled superiority |
| Developmental | historical 25 | ALNS 710.524 to 643.225 in one changed profile; spatial crossing 23 to 8 with vehicle/distance trade-off | Intermediate diagnosis | Direct comparison with the final matrix |
| **Controlled final** | **25** | **108 complete runs: 3 families x 3 methods x 4 policies x 3 seeds** | **Formal performance evidence** | Global optimality or broad instance-generalization |
| Supporting stress | 50 | Feasible cases and forced runtime limits documented; no complete comparable raw matrix | Stress and failure-mode evidence | Formal scalability curve |

![Experimental evidence hierarchy](assets/figures/B4_experimental_evidence_overview.png)

*Figure B4. Experimental evidence hierarchy. Source: retained development reports, historical result inventory, and the final raw JSONL. Supported conclusion: the project contains a staged evidence chain beyond the final 25-customer matrix. Unsupported conclusion: configurations across scales are not controlled and must not be averaged into a scalability claim.*

### 13.1 Controlled main matrix

The formal experiment contains 108 runs: three Solomon source families (`C101`, `R101`, `RC101`) x three final methods (GA, ALNS, Hybrid) x four charging policies (LFC, LPC, NFC, NPC) x three seeds (1987, 42, 128), with 25 customers, eight generated stations, and a nominal 90s budget. C/R/RC supply clustered, random, and mixed spatial-time-window structures; the study uses one source instance per family, so conclusions concern these three constructed cases rather than every Solomon instance.

The comparison unit is an instance-policy-seed cell. Feasibility rate uses all runs. Vehicle count, distance, completion, charging, waiting, and paper cost are reported primarily on feasible runs. Runtime uses every run and retains outliers. The same instance builder, solution schema, simulator, evaluator, station count, customer count, seeds, and nominal budget are used across the three methods. Hybrid divides its budget between GA candidate generation and ALNS refinement; this is an algorithmic allocation inside the same nominal envelope, not an additional full budget.

Three seeds provide repeat observations but limited inferential power. The report therefore emphasizes matched differences, medians, distributions, and win/tie/loss rather than claiming broad statistical significance. OR-Tools and PyVRP solve truck-only reference formulations and are excluded from the complete-model ranking. Parameter development occurred before the frozen matrix and was not a fully nested tuning study; this limits claims of universally optimal parameterization.

### 13.2 Reproducibility and missing environment evidence

The final configuration records algorithm, policy, seeds, station count, and budget. Exact CPU model, RAM, operating-system build, Python version, and thread-affinity metadata are not consistently embedded in every raw run: **Data unavailable** for a submission-grade hardware table. Runtime is therefore valid for within-matrix empirical comparison on the recorded environment, but not a hardware-independent complexity claim.

### 13.3 Data-quality audit

The raw JSONL contains 108 unique method-policy-seed-instance combinations, with zero duplicate keys and zero missing combinations. Thirty-one runs are infeasible and remain in feasibility and runtime statistics. No row has `feasible=True` with nonzero total violation. Four runs exceed 500s; they are retained. Derived summaries are reproducible from `results/report_deepening/main_run_index.csv` and related analysis CSVs; raw results remain authoritative.

| Audit item | Result | Treatment |
|---|---:|---|
| Expected / observed runs | 108 / 108 | complete matrix |
| Duplicate unique keys | 0 | no deletion |
| Missing combinations | 0 | no imputation |
| Infeasible runs | 31 | retained |
| Feasible/violation contradictions | 0 | none detected |
| Runtime > 500s | 4 | retained as pathology |

This design supports controlled comparisons among the final GA, ALNS, and Hybrid on the frozen 25-customer problem. It does not support global-optimality claims, a formal 50-customer scalability conclusion, or direct fairness claims against truck-only solvers.

## 14. RQ1 Constraint Adaptation Evidence

RQ1 asks how constraint handling moved from downstream checking into method-specific search. Early implementations could generate a route and rely on shared repair/simulation to expose its problems. That architecture ensured a common feasibility judge, but it made feasible output less attributable to GA or ALNS and reduced meaningful complementarity: two methods could feed similarly rough structures to the same downstream machinery.

The final division of responsibility is different. GA anticipates feasibility in decoding; ALNS uses problem-aware states and neighborhoods; Hybrid preserves candidate structure and applies explicit acceptance guards. Exact propagation remains centralized.

| Constraint | Final GA | Final ALNS | Final Hybrid | Shared simulator/evaluator |
|---|---|---|---|---|
| Coverage/duplicates | Construct once; fallback | State/unassigned repair | Conversion deduplicates and records unassigned | Final hard check |
| Capacity | Insertion/mission screening | Capacity-aware repair | Inherited and rechecked | Final hard check |
| Time windows | Route insertion propagation | Worst-time/TW-aware neighborhoods | Candidate and refinement screening | Exact truck/drone propagation |
| Truck/drone battery | Energy-aware decode | Energy/charging-aware operators | Refined state re-materialized | Exact SOC and violation |
| Charging | Station/target construction | Materialization and cleanup | Rebuilt after conversion | Exact policy time |
| Launch/recovery | Same-route mission construction | Drone rebuild/reassign | Structure preserved/validated | Mission hard check |
| Mission overlap | Decoder task scheduling | State/task operators | Valid-task conversion | Final structural check |
| Synchronization | Local mission scoring | Sync-aware neighborhoods | Waiting-sensitive acceptance | Exact recovery propagation |
| Vehicle count | Incremental expansion/ranking | Route removal/merge can change it | Vehicle-preserving guard | Reported metric |
| Route geometry | Sweep/cluster soft guidance | Crossing/petal operators | Secondary ranking | Soft diagnostics only |

This migration is partial by design. Search-time estimates reduce wasted candidates, but duplicating the complete simulator inside every operator would create inconsistent feasibility definitions. The shared evaluator therefore remains the final authority. The supported conclusion is methodological: the final methods search a more constraint-relevant space than early route-first versions. A strict causal estimate of how much each moved constraint improves performance is unavailable because the development configurations were not a controlled ablation.

## 15. RQ2 Overall Algorithm Behavior

The comparison unit is one algorithm-policy-instance-seed run. Feasibility uses all 36 runs per method; quality metrics use feasible runs only; runtime uses all runs. This separation prevents a method from appearing strong by reporting quality only on a few successful runs.

| Method | Feasible rate | Feasible vehicles | Feasible total distance | Feasible paper cost | Runtime median |
|---|---:|---:|---:|---:|---:|
| GA | 66.667% | 7.667 | 906.231 | 1262.173 | 76.122s |
| ALNS | 75.000% | 8.889 | 874.736 | 1319.028 | 90.530s |
| Hybrid | 72.222% | 7.885 | 891.438 | 1232.753 | 63.405s |

**Feasibility.** ALNS leads GA by 8.333 percentage points and Hybrid by 2.778 points. This is consistent with ALNS repeatedly repairing a current structured state instead of relying on one construction pass. Counter-evidence is family-specific: on RC101, GA and Hybrid reach 100%, so the global ALNS advantage is not universal.

**Vehicle-distance conflict.** GA uses 1.222 fewer feasible vehicles than ALNS on average, while ALNS saves 31.495 distance units relative to GA. These two findings are not contradictory. GA incrementally expands vehicle count and stops at the first feasible count, creating a construction bias toward fleet compression. ALNS can improve local route geometry and feasibility while retaining or creating more routes. Development had already exposed the same conflict when an ALNS refinement shortened a GA solution but added a vehicle; this directly motivated Hybrid's preserve rule.

**Hybrid compromise.** Hybrid sits between GA and ALNS in feasibility, vehicles, and distance, yet has the lowest paper cost. Relative to GA, its feasible paper cost is lower by 29.420 (2.33%); relative to ALNS it is lower by 86.275 (6.54%). The mechanism is not that Hybrid minimizes every component. Diverse starts and constrained refinement can select a combination with favorable distance, charging, and waiting without accepting an extra vehicle. Counter-evidence is the nontrivial loss count in RQ5, so this is an average trade-off rather than dominance.

**Drone contribution.** Nonzero drone distance confirms operational drone use, but distance alone is not a causal saving estimate. A valid contribution claim requires matched truck-distance and total-cost comparison; the final data support meaningful missions, not the assertion that every mission improves its run.

**Interpretation.** The final behavior matches the design history: constructive GA favors fleet structure, ALNS favors feasible local restructuring and distance, and Hybrid conditionally combines them. The unsupported conclusion would be to call any method universally best or globally optimal.

![Vehicle count versus total distance](assets/figures/D2_vehicle_count_vs_total_distance.png)

*Figure D2. Feasible-run vehicle-distance trade-off. Source: final 108-run matrix; infeasible runs excluded only from quality coordinates. Supported conclusion: methods occupy different trade-off regions. Unsupported conclusion: the lower-left point is not proven globally optimal.*

## 16. RQ3 Instance Sensitivity

Final feasibility is strongly instance-dependent. Across methods and policies, C101 yields 33.333% feasibility, whereas R101 and RC101 are substantially easier. Method-level rates are: C101 33.333% for all three methods; R101 66.667% GA, 100% ALNS, and 83.333% Hybrid; RC101 100% GA/Hybrid and 91.667% ALNS.

| Source family | GA feasible | ALNS feasible | Hybrid feasible | Dominant observed failure signature |
|---|---:|---:|---:|---|
| C101 | 33.333% | 33.333% | 33.333% | Truck-battery violations in 8/12 runs per method; one additional GA TW failure |
| R101 | 66.667% | 100.000% | 83.333% | GA/Hybrid time-window pressure; one Hybrid coverage failure |
| RC101 | 100.000% | 91.667% | 100.000% | One ALNS coverage failure |

The violation decomposition changes the explanation. In C101, truck-battery violation appears in 8 of 12 runs for each method; summed magnitude is 32.014 for GA and 32.322 for ALNS and Hybrid. GA additionally has one C101 time-window failure of 13.469. Thus the controlled evidence supports an energy-reachability diagnosis more directly than a generic claim that clustered C101 is hard because of time windows. One plausible mechanism is that clustered service sequences encourage compact customer tours whose station connectivity or return legs remain energy-critical. This remains an interpretive inference because no counterfactual station-layout experiment was run.

R101 failures have a different signature. GA records time-window violation in four runs, while Hybrid has two time-window failures and one missing-customer/coverage failure. ALNS achieves 100% feasibility, consistent with its worst-time removal and TW-aware repair strength. RC101 is nearly fully feasible; its only observed formal failure is one ALNS missing-customer/coverage case.

The family result therefore cannot be reduced to “C is harder.” C101 is systematically energy-sensitive under this generated-station design; R101 is more temporally sensitive for GA/Hybrid; RC101 is mostly robust but not immune to structural repair failure. Historical logs suggest C-family runtime and feasibility pressure, but they do not isolate the cause. No road-network, alternate station-layout, or customer-resampling experiment exists, so geometric causality remains unverified.

![Method by instance feasibility](assets/figures/C2_method_instance_feasibility_heatmap.png)

*Figure C2. Feasibility by method and source family. Source: all 108 final runs. Supported conclusion: feasibility ranking depends on instance family. Unsupported conclusion: the heatmap alone cannot identify a causal geometric mechanism.*

## 17. RQ4 Charging Policy Analysis

Charging policies form a factorial design: charging law (linear/nonlinear) crossed with target type (full/partial). The primary descriptive result is robust charging-time reduction under partial targets.

| Method | LFC | LPC | NFC | NPC |
|---|---:|---:|---:|---:|
| GA | 200.759 | 110.421 | 248.166 | 124.416 |
| ALNS | 166.309 | 80.752 | 242.731 | 76.091 |
| Hybrid | 157.640 | 97.580 | 287.642 | 101.119 |

For GA, LPC reduces mean feasible charging time by 90.338 relative to LFC and NPC reduces it by 123.750 relative to NFC. For ALNS the reductions are 85.557 and 166.640; for Hybrid, 60.060 and 186.523. The larger nonlinear partial effect is consistent with avoiding the slow high-SOC segment defined in Section 6.

The nonlinear effect depends on target type. Under full charging, NFC exceeds LFC by 47.408 (GA), 76.422 (ALNS), and 130.002 (Hybrid). Under partial charging, NPC differs from LPC by only +13.995 for GA, -4.661 for ALNS, and +3.539 for Hybrid. The difference-in-differences is therefore strongly negative for charging time: partial targets remove much of nonlinear full charging's penalty.

This mechanism does not imply automatic feasibility improvement. Partial charging shortens residence time but reduces SOC slack; a route can become more sensitive to later detours. Paper cost and completion also include route and waiting effects, so their policy ranking need not exactly mirror charging time. Runtime effects for GA and ALNS are dominated by two pathological NFC runs; consequently, very large mean nonlinear-runtime differences are observed but cannot be attributed solely to charging physics without profiling.

![Charging policy factorial analysis](assets/figures/F1_charging_policy_2x2.png)

*Figure F1. Linear/nonlinear × full/partial charging analysis. Source: feasible-only quality metrics from the final matrix. Supported conclusion: partial charging sharply reduces charging time. Unsupported conclusion: partial charging is not guaranteed to improve feasibility or every cost component.*

## 18. RQ5 Hybrid Effectiveness

Hybrid effectiveness is evaluated on 36 matched instance-policy-seed cells. Recalculation with the final `paper_cost_priority` rank gives Hybrid versus GA: 18 wins, 4 ties, and 14 losses; versus ALNS: 25 wins and 11 losses. An older generated summary reported 18/5/13 against GA because it used a different tie/comparison convention. The report uses the final-code-aligned reconstruction and preserves the older CSV as a historical artifact rather than silently deleting it.

| Baseline | Overall W/T/L | C101 W/T/L | R101 W/T/L | RC101 W/T/L | Main interpretation |
|---|---:|---:|---:|---:|---|
| GA | 18/4/14 | 7/1/4 | 6/0/6 | 5/3/4 | Competitive but not dominant; R101 is evenly split |
| ALNS | 25/0/11 | 11/0/1 | 6/0/6 | 8/0/4 | Strongest relative advantage on C101; no stable R101 synergy |

Family-level behavior is revealing. Against GA, Hybrid records 7/1/4 W/T/L on C101, 6/0/6 on R101, and 5/3/4 on RC101. Against ALNS it records 11/0/1 on C101, 6/0/6 on R101, and 8/0/4 on RC101. Hybrid is therefore especially competitive against ALNS on C101, while R101 exposes the clearest lack of stable synergy.

The case-level mechanism follows the development chain. Single-best refinement failed because GA rank measures current quality, not local improvability. Top-K broadened starts; preserve rules blocked distance gains purchased with another vehicle; periodic/stagnation experiments often injected zero and showed that timing was not the main bottleneck; Hybrid-local moves reduced disruption; typed diverse Top-K finally targeted candidate homogeneity.

Three success patterns are supported: the selected GA candidate is not rank one but has a refinable local structure; ALNS lowers paper cost without increasing vehicles; or Hybrid retains a better original candidate when refinement is harmful. Three failure patterns remain: candidates are structurally similar, ALNS improves a secondary metric but fails the final rank, or the constituent GA/ALNS solution is already better for that family-policy cell. Diagnostic fields are incomplete for some cases, so not every loss can be assigned a unique rejection cause.

![Hybrid paired paper-cost differences](assets/figures/E2_paired_delta_paper_cost.png)

*Figure E2. Paired Hybrid-minus-baseline paper-cost differences. Source: matched final runs. Supported conclusion: Hybrid gains are scenario-dependent. Unsupported conclusion: negative mean delta does not imply universal dominance.*

## 19. RQ6 Computational Robustness

Runtime uses all runs and retains every outlier. GA has median 76.122s, mean 402.307s, standard deviation 1811.425s, and maximum 10922.699s. ALNS has median 90.530s, mean 456.634s, standard deviation 1835.505s, and maximum 10929.262s. Hybrid is much tighter: median 63.405s, mean 62.725s, standard deviation 6.039s, and maximum 73.821s.

| Method | Median (s) | Mean (s) | Std. dev. (s) | Maximum (s) | >500s | >1000s | >10000s |
|---|---:|---:|---:|---:|---:|---:|---:|
| GA | 76.122 | 402.307 | 1811.425 | 10922.699 | 2 | 2 | 1 |
| ALNS | 90.530 | 456.634 | 1835.505 | 10929.262 | 2 | 2 | 1 |
| Hybrid | 63.405 | 62.725 | 6.039 | 73.821 | 0 | 0 | 0 |

Both GA and ALNS have two runs above 500s, two above 1000s, and one above 10000s. Hybrid has none. Infeasible runs are especially expensive on average: 969.089s for GA and 1295.184s for ALNS, versus feasible-run means of 118.916s and 177.117s. This association does not establish direction of causality; difficult search can consume time and still fail, while a pathological execution may itself prevent adequate search.

Development explains the engineering response. Constraint-aware decoding, multi-customer drone enumeration, charging checks, ALNS operator pools, and full evaluator calls all add computational work. Caching, geometry filters, affected-route evaluation, Top-K screening, and explicit budget splitting were introduced to contain it. Final Hybrid's stability is consistent with bounded candidate generation and per-candidate refinement, even though the conceptual algorithm is more complex.

The exact cause of the 10,000-second cases is unresolved without profiling. Existing logs identify affected instance/policy/method combinations but do not prove a deadlock, infinite loop, or one responsible operator. They are therefore retained as runtime pathology rather than removed or assigned a speculative root cause.

![Runtime empirical cumulative distribution](assets/figures/H2_runtime_ecdf.png)

*Figure H2. Runtime ECDF with all observations retained. Source: all 108 final runs. Supported conclusion: standalone GA and ALNS have heavy tails; final Hybrid is bounded in this matrix. Unsupported conclusion: the figure does not identify the responsible code path.*

## 20. Supporting Experiments as Methodological Evidence

The supporting experiments are **developmental evidence**. They explain why mechanisms were introduced; they are not pooled with the 108-run means because versions, budgets, or configurations changed.

| Scale/stage | Concrete retained observation | Design decision supported | Evidence boundary |
|---|---|---|---|
| 5-customer | R101 feasible, 3 vehicles, distance 161.151, runtime 0.845s | Complete constraint pipeline could be exercised cheaply | Correctness-oriented, not ranking evidence |
| 10-customer | Top-K selected rank 3; preserve accepted a same-vehicle improvement | GA rank differs from ALNS potential; preserve vehicle count | Configurations changed across stages |
| Historical 25 | GA 7 vehicles/810.202 vs Hybrid candidate 8/771.314 | Vehicle-distance conflict required explicit acceptance rules | Single developmental case |
| Historical 25 | Periodic about 97.2s with zero injection; stagnation trigger with zero injection | Trigger timing was not the sole bottleneck | Not a population-wide causal test |
| 50-customer | Reports record feasible cases under forced runtime limits | Budget guards and stress-test positioning | Consolidated comparable raw matrix unavailable |

### 20.1 Five-customer mechanism validation

Small cases tested whether the complete pipeline could create a feasible structured solution and propagate coverage, time, SOC, charging, and synchronization. A documented R101-5 ALNS run was feasible with three vehicles, distance 161.151, and runtime 0.845s; C101-5 and RC101-5 checks were also feasible at roughly 0.9-1.0s. Their scientific role is correctness-oriented: a failure can expose a schema or simulator defect cheaply. Their limitation is equally important: abundant slack and few interacting missions cannot predict 25-customer ranking.

### 20.2 Ten-customer method evolution

Ten-customer runs exposed interaction mechanisms. Single-best Hybrid refinement improved R101-10 by about 0.64% in one stage, while Top-K later selected a GA rank-3 candidate, supporting the hypothesis that current GA rank and ALNS refinement potential differ. Stage-6 results under a different development configuration were GA distance 349.970, hybrid_topk 371.125, and hybrid_preserve 358.810. The final diverse variants reached 344.074 and 342.752 in the debug summary, but the settings and methods changed; this is developmental evidence rather than a controlled improvement chain. A C101-10 Hybrid run near 532s motivated explicit wall-clock/iteration guards and subsequently completed near 4.8s, showing an engineering correction rather than a general complexity theorem.

### 20.3 Twenty-five-customer development

Medium-scale smoke tests revealed the decisive vehicle-distance conflict. In one R101-25 NPC audit, GA used seven vehicles and distance 810.202, whereas diverse Top-K Hybrid used eight vehicles and distance 771.314. The shorter route was not unambiguously preferable under vehicle-first ranking, directly motivating vehicle-preserving refinement and paper-cost alignment. Another ALNS development snapshot changed R101-25 distance from 710.524 to 643.225 at nine vehicles with seven crossing successes, but profiles differed; it indicates reachable improvement, not a controlled ablation.

### 20.4 Fifty-customer stress evidence

Fifty-customer runs were constrained stress tests intended to expose runtime and feasibility limits. The preserved reports state that GA/ALNS could generate feasible solutions in some 50-customer settings, while runtime had to be forcibly bounded. Configuration heterogeneity and incomplete consolidated raw evidence prevent a formal 5/10/25/50 curve. The supported conclusion is that scale pressure motivated caching, pruning, layered evaluation, and explicit budgets. Formal scalability beyond 25 customers remains unestablished.

## 21. Representative Solutions

A saved 25-customer Hybrid solution is available and is used without rerunning or visually altering the route. Figure I1 shows `RC101_25_seed128_td`, LFC, feasible, eight vehicles, total distance 861.2, and paper cost 1106.8. It was selected as an existing representative full-solution asset with visible truck-drone collaboration, rather than because it is the visually most attractive route.

![Representative Hybrid solution](assets/figures/I1_representative_hybrid_solution.png)

*Figure I1. Saved RC101-25 Hybrid solution under LFC (seed 128). Depot, customers, stations, truck routes, and a drone mission are distinguished. The radial multi-route pattern reflects the eight-vehicle solution; the dashed mission demonstrates actual service-mode coupling. Source: saved final raw solution. The map supports structural interpretation, not an optimality claim.*

The overview illustrates why scalar distance is incomplete. Multiple routes leave the depot in different sectors, while the drone mission bypasses part of a truck sequence and must still satisfy launch/recovery timing and energy. Station markers show available/used charging structure, but a static map does not reconstruct SOC or synchronization trajectories. A submission-grade mission zoom and SOC-time trace require sufficiently detailed saved event traces; **Data unavailable** for a verified trajectory figure. No synthetic trace is introduced.

## 22. Negative Results and Failure Analysis

### 22.1 Hybrid non-dominance

**Evidence.** Final matched comparisons give Hybrid 18 wins, 4 ties, and 14 losses against GA, and 25 wins/11 losses against ALNS under final ranking. Earlier stages already warned of this: naive refinement often retained GA; R101-25 periodic refinement ran about 97.2s with zero injection; stagnation could trigger yet inject zero; and Stage-6 top-K/preserve distances (371.125/358.810) did not beat GA (349.970).

**Mechanism and counter-evidence.** Combining population exploration with local search creates an opportunity, not a guarantee. Candidates may be homogeneous, the constituent solution may already be locally strong, or an ALNS move may improve distance while violating vehicle priority. Diverse Top-K and aligned acceptance improved the mechanism, and Hybrid still beats GA in half the matched cells. The final lesson is conditional synergy, not failure of hybridization as a concept.

### 22.2 Vehicle-distance conflict

Development exposed the conflict directly: R101-25 Hybrid reduced distance from GA's 810.202 to 771.314 but increased vehicles from seven to eight. Final evidence preserves the same structural pattern at method level: ALNS has the lowest mean feasible distance (874.736) and highest vehicles (8.889), while GA has fewer vehicles (7.667) and longer distance (906.231). Vehicle-preserving refinement makes Hybrid claims more defensible, but it deliberately rejects some distance gains. The limitation is normative: a different operational cost for vehicles could change the preferred trade-off.

### 22.3 C101 systematic difficulty

All three methods achieve only 33.333% feasibility on C101. Diagnostic decomposition identifies truck-battery violations in eight of twelve runs for each method; GA also has one time-window failure. This supports an energy-sensitive interpretation for the generated C101 station layout. It does not prove that clustered geometry itself is causal, because station-layout and resampling controls were not run.

### 22.4 Ineffective and expensive ALNS operators

ChargingCleanup, ChargingPolish, WaitingReduction, and Hybrid PetalPolish recorded zero best improvements, while D-Cluster cost about 10.389s weighted runtime per diagnostic record. These operators arose from observed charging, waiting, geometry, and clustering concerns, but final diagnostics do not establish favorable cost-effectiveness. A controlled removal ablation is still needed before deleting them from a future method.

### 22.5 Runtime pathology

GA and ALNS each contain two runs above 1000s and one above 10000s; Hybrid contains none. Infeasible runs are much slower on average for GA and ALNS. Existing logs do not identify a single responsible loop or operator, so the root cause remains **Unverified hypothesis** without profiling. The evidence supports heavy-tail reporting and wall-clock protection, not a claim that a deadlock was found.

### 22.6 Early shared-repair dependence

Early route-first/search-first versions delegated much feasibility work to shared materialization and evaluation. That made feasibility less attributable to the method and reduced genuine search-space differentiation. Moving TW, energy, drone, charging, and synchronization awareness into GA decoding and ALNS neighborhoods improved methodological independence, while final hard validation correctly remains shared. This is a design lesson rather than a controlled numerical ablation.

## 23. Discussion

### 23.1 Constraint-aware search changes what is explored

The central contribution is not merely adding constraint checks after route generation. Coverage, time-window pressure, energy reachability, drone eligibility, charging intent, and synchronization increasingly influence candidate construction or neighborhood choice. Developmental evidence motivated this shift; the final matrix tests its frozen outcome. The shared evaluator still protects comparability, but it no longer supplies the entire algorithmic intelligence.

### 23.2 The methods exhibit distinct search biases

GA's structured construction and route-split decisions favor compact vehicle usage: 7.667 feasible vehicles on average, versus 8.889 for ALNS. ALNS's destroy-repair and drone rebuild neighborhoods favor local distance and feasibility: 75.0% feasibility and distance 874.736, versus GA's 66.667% and 906.231. Hybrid occupies the trade-off region with 72.222% feasibility, 7.885 vehicles, distance 891.438, and the lowest reported mean paper cost 1232.753. These are tendencies with counterexamples by family and policy, not immutable algorithm properties.

### 23.3 Structural complementarity is necessary for Hybrid synergy

The development sequence identifies three requirements: diverse starting structures, a conversion that preserves decisions while rebuilding derived state, and an acceptance rule aligned with the paper objective. Timing ALNS calls more frequently did not solve candidate quality, as zero-injection periodic/stagnation runs showed. Diverse Top-K targets a different bottleneck: giving ALNS neighborhoods that are not copies of the GA best. Even then, final W/T/L confirms conditional rather than universal synergy.

### 23.4 Candidate quality and candidate diversity are different resources

A rank-3 GA candidate can be a better ALNS start because ranking measures present quality while refinement potential measures reachable quality. Selecting only top-ranked, edge-similar candidates wastes ALNS budget on the same basin. Typed candidates broaden order, split, drone, charging, and geometry intentions. The cost is budget dilution: each candidate receives less refinement time, and a useful basin can still be missed.

### 23.5 Charging policy reshapes time-energy coupling

Partial charging consistently lowers feasible charging time, especially under nonlinear charging, because it avoids slow high-SOC segments. Yet lower charging time need not yield higher feasibility: lower SOC reserve can expose a later route to energy risk, and a shorter station stay changes truck-drone synchronization. This explains why policy effects must be read jointly across charging, completion, waiting, feasibility, and paper cost.

### 23.6 Instance structure changes algorithm ranking

C101's 33.333% feasibility and repeated battery failures contrast with stronger R101/RC101 performance. R101 exposes more time-window difficulty for GA/Hybrid, whereas RC101 is mostly robust with one ALNS structural coverage failure. These observed mechanisms are instance-specific. With one source instance per family, the report cannot generalize to all clustered, random, or mixed Solomon cases.

### 23.7 Development evidence and final evidence can disagree

The 10-customer diverse Hybrid debug summary was encouraging, but the 108-run matrix did not establish dominance. This is scientifically useful: development experiments validate mechanisms and expose failure modes; controlled final experiments test robustness. Treating a debug gain as a final claim would confuse these roles.

### 23.8 Negative results are reusable design knowledge

Zero-yield polish operators, vehicle-distance conflict, C101 energy failures, Hybrid losses, and runtime tails constrain the credible claims and identify future work. The present methods are practically usable for many 25-customer runs, but 31/108 infeasible outcomes and severe standalone runtime outliers preclude describing the framework as universally robust. A future study should prioritize controlled operator removal, profiler-guided runtime repair, broader source instances, and cost calibration rather than adding more named operators.

## 24. Limitations

The main formal scale is 25 customers. 50-customer evidence is stress/developmental. OR-Tools and PyVRP are truck-only references, not complete-model competitors. Truck and drone use Euclidean distance; road networks, airspace, wind, no-fly zones, and cross-truck drone recovery are not modeled. Charging curves are engineering approximations. No global optimality is proven. Hybrid is competitive but not universally dominant. Runtime outliers remain and are retained.

## 25. Contribution-Evidence Mapping

| Contribution | RQ | Evidence | Table/Figure | Limitation |
| --- | --- | --- | --- | --- |
| Unified Truck-Drone EVRPTW-NL computational model | RQ1 | final model, simulator, evaluator | model-code map, problem schematic | engineering model, not complete real-world physics |
| Constraint-aware GA adaptation | RQ1/RQ2 | solve_ga.py, ga_tools.py, final results | GA method table, overall summary | not globally optimal |
| Independent ALNS with diagnostics | RQ1/RQ2 | ALNS code and operator summary | operator bubble/heatmap | operator effects uneven |
| Diverse Top-K GA-ALNS Hybrid | RQ5 | hybrid code and diagnostics | win/tie/loss, paired deltas | conditional, not universal dominance |
| Charging policy analysis | RQ4 | charging.py and final 108 rows | 2x2 charging figure | segmented approximation |
| Runtime robustness analysis | RQ6 | runtime fields | runtime ECDF/outlier table | no profiling proof |

## 26. References

Baker, B.M. and Ayechew, M.A. (2003) 'A genetic algorithm for the vehicle routing problem', *Computers & Operations Research*, 30(5), pp. 787–800. Available at: https://doi.org/10.1016/S0305-0548(02)00051-5

Keskin, M. and Çatay, B. (2016) 'Partial recharge strategies for the electric vehicle routing problem with time windows', *Transportation Research Part C: Emerging Technologies*, 65, pp. 111–127. Available at: https://doi.org/10.1016/j.trc.2016.01.013

Liang, Y. and Luo, Z. (2022) 'A survey of truck-drone routing problem: Literature review and research prospects', *Journal of the Operations Research Society of China*, 10, pp. 343–377. Available at: https://doi.org/10.1007/s40305-021-00383-4

Macrina, G., Pugliese, L.D.P., Guerriero, F. and Laporte, G. (2020) 'Drone-aided routing: A literature review', *Transportation Research Part C: Emerging Technologies*, 120, article 102762. Available at: https://doi.org/10.1016/j.trc.2020.102762

Montoya, A., Guéret, C., Mendoza, J.E. and Villegas, J.G. (2017) 'The electric vehicle routing problem with nonlinear charging function', *Transportation Research Part B: Methodological*, 103, pp. 87–110. Available at: https://doi.org/10.1016/j.trb.2017.02.004

Murray, C.C. and Chu, A.G. (2015) 'The flying sidekick traveling salesman problem: Optimization of drone-assisted parcel delivery', *Transportation Research Part C: Emerging Technologies*, 54, pp. 86–109. Available at: https://doi.org/10.1016/j.trc.2015.03.005

Pisinger, D. and Ropke, S. (2007) 'A general heuristic for vehicle routing problems', *Computers & Operations Research*, 34(8), pp. 2403–2435. Available at: https://doi.org/10.1016/j.cor.2005.09.012

Prins, C. (2004) 'A simple and effective evolutionary algorithm for the vehicle routing problem', *Computers & Operations Research*, 31(12), pp. 1985–2002. Available at: https://doi.org/10.1016/S0305-0548(03)00158-8

Ropke, S. and Pisinger, D. (2006) 'An adaptive large neighborhood search heuristic for the pickup and delivery problem with time windows', *Transportation Science*, 40(4), pp. 455–472. Available at: https://doi.org/10.1287/trsc.1050.0135

Schneider, M., Stenger, A. and Goeke, D. (2014) 'The electric vehicle-routing problem with time windows and recharging stations', *Transportation Science*, 48(4), pp. 500–520. Available at: https://doi.org/10.1287/trsc.2013.0490

Shaw, P. (1998) 'Using constraint programming and local search methods to solve vehicle routing problems', in Maher, M. and Puget, J.-F. (eds.) *Principles and Practice of Constraint Programming – CP98*. Berlin: Springer, pp. 417–431. Available at: https://doi.org/10.1007/3-540-49481-2_30

Solomon, M.M. (1987) 'Algorithms for the vehicle routing and scheduling problems with time window constraints', *Operations Research*, 35(2), pp. 254–265. Available at: https://doi.org/10.1287/opre.35.2.254

Vidal, T., Crainic, T.G., Gendreau, M. and Prins, C. (2013) 'A hybrid genetic algorithm with adaptive diversity management for a large class of vehicle routing problems with time-windows', *Computers & Operations Research*, 40(1), pp. 475–489. Available at: https://doi.org/10.1016/j.cor.2012.07.018

Yu, S., Zhu, T. and Puchinger, J. (2026) 'Electric truck-based robot delivery problem with nonlinear charging', *Transportation Research Part E: Logistics and Transportation Review*, 213, article 104958. Available at: https://doi.org/10.1016/j.tre.2026.104958
