# Stage 7-9: Final Hybrid Closing Optimization

## Motivation

前几轮 Hybrid 的问题已经比较明确：继续提高 ALNS 调用频率没有根本意义，因为 GA 候选池本身过于同质。ALNS 即使被触发，也经常只能在相似结构附近做微调，难以产生可以替换 GA 精英解的明显改进。

因此最后一轮不再继续堆 H operator，而是把 Hybrid 的核心改为：

```text
GA 生成多类型、高差异候选解
-> 按质量、结构差异和候选类型覆盖选择 Top-K
-> ALNS 对不同结构候选做同车辆数局部精修
-> 使用 paper-cost-priority 规则决定最终解
```

## Algorithm Changes

### Diverse GA Candidate Generation

新增 Hybrid 专用候选类型：

| Candidate Type | Purpose |
|---|---|
| `distance_oriented` | 优先降低总距离 |
| `vehicle_oriented` | 优先减少车辆数 |
| `time_window_oriented` | 优先降低时间窗压力和完成时间 |
| `drone_aggressive` | 更积极使用无人机分担卡车任务 |
| `drone_conservative` | 仅在无人机明确有收益时使用 |
| `charging_oriented` | 优先降低充电时间和充电次数 |
| `petal_oriented` | 优先保持花瓣状结构和低交叉 |
| `balanced` | 保留当前综合策略 |

这些候选只用于 Hybrid，不改变 GA baseline。

### New Hybrid Modes

新增两个方法入口：

| Method | Meaning |
|---|---|
| `hybrid_diverse_topk` | 多类型 GA 候选 + Top-K 多起点 ALNS 精修 |
| `hybrid_diverse_stagnation` | 多类型 GA 候选 + 停滞触发 ALNS + 最终 Top-K 精修 |

旧方法 `hybrid_topk`、`hybrid_stagnation`、`hybrid_preserve` 保留，用于对比。

### Paper-priority Comparison

新增 `paper_cost_priority` 比较规则：

```text
1. feasible=True
2. total_violation=0
3. vehicle_count 更少
4. paper_cost 更低
5. total_distance 更低
6. completion_time 更低
7. charging_time + waiting_time + sync_wait 更低
8. petal_score 更低
```

其中第一版 `paper_cost` 定义为：

```text
paper_cost = total_distance + charging_time + 0.25 * waiting_time + 0.25 * drone_waiting_time
```

该规则避免把“距离下降但车辆数增加”的解误判为主结果更好。

## Runtime Fix

调试时发现 `C101-10 hybrid_diverse_topk` 曾出现约 532 秒异常运行。原因是单个 ALNS refine 候选内部枚举过多，超过外部预期预算。

修复包括：

- Hybrid 调度层按剩余 wall-clock 时间动态分配候选预算；
- diverse refine 默认使用更适合小邻域精修的 `alns_hybrid_local`；
- 给 `refine_state()` 传入随候选预算变化的 `max_iterations`；
- ALNS refine 在 local search 链内部增加预算检查。

复测后，`C101-10 hybrid_diverse_topk` 运行时间降至约 4.8 秒，并保持 `feasible=True`。

## Debug Results

配置：

```text
instances: R101, C101, RC101
customer_count: 10
charging_policy: NPC
seed: 1987
methods:
  - ga
  - alns_full
  - hybrid_topk
  - hybrid_stagnation
  - hybrid_diverse_topk
  - hybrid_diverse_stagnation
```

结果：

| Method | Feasible Rate | Avg Vehicles | Avg Distance | Avg Paper Cost | Avg Runtime |
|---|---:|---:|---:|---:|---:|
| GA | 100.00% | 3.000 | 349.970 | 528.437 | 3.536s |
| ALNS-full | 100.00% | 3.667 | 351.370 | 553.472 | 18.613s |
| hybrid_topk | 100.00% | 3.000 | 371.125 | 549.292 | 4.260s |
| hybrid_stagnation | 100.00% | 3.000 | 361.346 | 542.751 | 17.720s |
| hybrid_diverse_topk | 100.00% | 2.667 | 344.074 | 494.442 | 4.584s |
| hybrid_diverse_stagnation | 100.00% | 3.000 | 342.752 | 501.626 | 15.596s |

## 25-customer Single-case Check

`R101-25 + NPC` 单例结果：

| Method | Feasible | Vehicles | Distance | Runtime | Notes |
|---|---:|---:|---:|---:|---|
| GA | True | 7 | 810.202 | 75.659s | 车辆数更少 |
| hybrid_diverse_topk | True | 8 | 771.314 | 68.779s | 距离更短，但车辆数更多 |

该结果说明 Hybrid 在中规模下已经可以找到更短距离结构，但尚未稳定满足“车辆数不高于 GA”的主方法要求。因此 25 customers 需要批量实验，不能只用单例下结论。

## Current Judgment

当前最强 Hybrid 版本是 `hybrid_diverse_topk`，不是 `hybrid_stagnation`。

原因：

- `hybrid_diverse_topk` 在 10 customers debug 中平均车辆数、平均距离、平均 paper_cost 都优于 GA 和 ALNS。
- `hybrid_diverse_stagnation` 距离也有优势，但运行时间明显更高。
- 停滞注入本身仍不稳定，说明最终提升更多来自候选多样性，而不是周期或停滞触发。

## Remaining Risks

- 10 customers 结果不能直接支撑论文主方法结论。
- 25 customers 单例存在“距离更短但车辆数更多”的冲突。
- ALNS refine 的深度贡献仍有限，很多情况下最终选择的是 GA 多样候选，而不是 ALNS 改进后的候选。
- 如果 25 customers 批量中 Hybrid 平均车辆数高于 GA，则不能主打 Hybrid，只能把 Hybrid 作为增强或探索方法。

## Next Decision

必须运行：

```powershell
D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_experiments --config configs/hybrid_final_25.yaml
D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.hybrid_final_report
```

根据结果决定论文方向：

| Outcome | Paper Direction |
|---|---|
| Hybrid 在 25 customers 平均车辆数不高于 GA，且 paper_cost / distance 更好 | 主打 `Diverse GA + ALNS Hybrid` |
| Hybrid 只在部分指标优于 GA | 主打约束感知 GA，Hybrid 作为增强和消融 |
| Hybrid 仍不优于 GA | 主打建模 + GA，Hybrid 作为负结果分析 |

# GA+ALNS Hybrid Development Report

## 1. Method Position

GA+ALNS Hybrid 的目标不是简单比较 GA 和 ALNS 谁更好，而是让两者承担不同角色：

- GA：负责全局结构搜索，包括车辆划分、客户顺序、truck/drone 服务方式、无人机任务倾向和充电策略倾向。
- ALNS：负责在已有可行结构附近做局部精修，包括路线压缩、客户重插入、无人机任务重建、充电计划优化和花瓣状结构改善。

当前保留两种 Hybrid：

| Method | Meaning | Role |
|---|---|---|
| `hybrid_selector` | GA 和独立 ALNS 分别运行，然后选择更好结果 | 浅层组合 baseline |
| `hybrid_refine` | GA 先生成解，ALNS 从 GA 解继续搜索 | 真正融合 Stage 1 |

`hybrid` 默认指向 `hybrid_refine`。

## 2. Stage 1 Algorithm

Stage 1 采用 single-best post-processing：

```text
GA solve
-> GA best solution
-> solution_to_alns_state()
-> ALNS refine_state()
-> unified evaluator
-> compare_hybrid_results()
-> final result
```

关键原则：

- ALNS 不重新构造初始解，而是从 GA 解转换得到的 `ALNSState` 开始。
- 不允许 ALNS 不可行解替换 GA 可行解。
- 如果 ALNS 距离更短但车辆数更多，仍按车辆数优先规则保留 GA。
- 时间、电量、等待和充电状态全部由 evaluator 重新计算。

## 3. Conversion Rules

`solution_to_alns_state()` 的转换规则：

| Input field | ALNS state field | Handling |
|---|---|---|
| `truck_routes` | `clean_truck_routes` | 删除充电站，保留仓库和客户 |
| `drone_tasks` | `drone_tasks` | 保留合法任务 |
| `drone_route` | `drone_route` | 保留客户和已有充电站 |
| `charging_plan` | rebuilt later | 不直接继承 |
| timing / energy states | recalculated | 不直接继承 |

如果发现缺失客户，会写入 `unassigned_customers`，交给 ALNS repair 处理。

## 4. Comparison Rule

Hybrid 比较采用可行性优先的词典序：

```text
1. feasible
2. total_violation
3. vehicle_count
4. completion_time
5. total_distance + charging_time
6. waiting_time + drone_waiting_time
7. petal_score
```

因此，ALNS refine 并不是只要距离更短就替换 GA。车辆数或完工时间更差时，可能仍保留 GA。

## 5. Validation Results

| Instance | Method | Feasible | Selected Source | Vehicles | Result |
|---|---|---:|---|---:|---|
| R101-5 NPC | `hybrid_refine` | True | GA | 2 | ALNS 距离更短但车辆数更多，未替换 |
| R101-10 NPC | `hybrid_refine` | True | ALNS refine | 3 | ALNS refine 替换 GA，`improvement_percentage≈0.64%` |
| R101-25 NPC | `hybrid_refine` | True | GA | 7 | ALNS 距离更短但车辆数更多，未替换 |
| R101-5 NPC | `hybrid_selector` | True | GA | 2 | 旧浅层 baseline 正常运行 |

## 6. Current Limitations

- Stage 1 只精修 GA 的单个最优解。
- 如果 GA 最优解已经处于 ALNS 当前邻域下的局部最优，改进会很小。
- 25 customers 中 ALNS refine 可能用更多车辆换更短距离，导致无法替换 GA。
- 当前尚未实现 Top-K diverse candidates、周期性精英改进和停滞触发。

## 7. Next Step

下一阶段建议实现 Stage 2：Top-K diverse GA candidates。

目标：

- 不只把 GA 第一名交给 ALNS；
- 选择多个质量较高但结构不同的 GA 解；
- 每个候选分配短时 ALNS refine；
- 在相同总时间预算下选择最好可行结果。

这一步能判断：GA 第一名是否一定是 ALNS 最好的起点，以及多起点是否能提升 Hybrid 稳定性。

---

## 8. Stage 2: Top-K Diverse Candidates

### 8.1 Motivation

Stage 1 的问题不是不能运行，而是只使用 `GA best solution` 一个起点。这个起点在 GA 的目标函数下最好，但不一定最适合 ALNS 继续改进。

实际测试中出现过两类情况：

- ALNS 能降低距离，但会增加车辆数，因此不能替换 GA 解。
- GA 第一名并不一定比 GA 第二名、第三名更适合最终 Hybrid 目标。

因此 Stage 2 改为：

```text
GA candidate pool
-> select diverse Top-K candidates
-> ALNS refine each candidate
-> unified evaluator
-> select best feasible result
```

### 8.2 Algorithm Changes

| File | Change |
|---|---|
| `TruckDrone_EVRPTW_NL/solvers/solve_ga.py` | 新增 `generate_ga_candidates_for_hybrid()`，在不改变 GA baseline 返回格式的前提下，为 Hybrid 提供多个已评价候选解 |
| `TruckDrone_EVRPTW_NL/solvers/hybrid_tools.py` | 新增 `select_diverse_top_k()` 和 `solution_similarity()` |
| `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py` | 新增 `hybrid_topk` 模式 |
| `TruckDrone_EVRPTW_NL/run_single.py` | 新增 `hybrid_topk` 方法入口 |
| `TruckDrone_EVRPTW_NL/run_experiments.py` | `summary.csv` 新增 Top-K 诊断字段 |

候选相似度第一版使用路线边集合：

```text
similarity = shared_edges / union_edges
```

边集合包括 truck route edges 和 drone route edges。默认 `top_k = 3`，`similarity_threshold = 0.75`。

### 8.3 Comparison Rule

Stage 2 仍使用同一套 Hybrid 比较规则：

```text
1. feasible
2. total_violation
3. vehicle_count
4. completion_time
5. total_distance + charging_time
6. waiting_time + drone_waiting_time
7. petal_score
```

这意味着 ALNS refinement 不是只要距离更短就会被接受。如果它增加车辆数，即使距离下降，也可能被拒绝。

### 8.4 Validation Results

| Instance | Method | Feasible | Selected Candidate | Selected Source | Main Observation |
|---|---:|---:|---:|---|---|
| R101-5 NPC | `hybrid_topk` | True | rank 1 | GA | ALNS 降低距离但增加车辆数，最终保留 GA |
| R101-10 NPC | `hybrid_topk` | True | rank 3 | GA candidate | Top-K 找到比 GA 第一名更好的结构 |
| R101-25 NPC | `hybrid_topk` | True | rank 3 | GA candidate | 中规模下 Top-K 仍能发挥多起点作用 |

### 8.5 Current Interpretation

Stage 2 的主要贡献是“多起点选择”，不是 ALNS 算子本身的大幅提升。

当前可以得出三个判断：

1. GA 第一名不一定是 Hybrid 最好起点。
2. Top-K diverse candidates 能提高 Hybrid 的结构搜索范围。
3. ALNS refine 仍需要更强的 vehicle-preserving refinement，否则容易出现“距离下降但车辆数增加”的情况。

### 8.6 Remaining Limitations

- 当前仍属于 post-processing 多起点，不是 GA 演化过程内融合。
- 相似度主要看 route edges，对无人机任务结构和充电结构的区分还比较粗。
- ALNS 对 GA candidate 的改进仍不够稳定，特别是 25 customers 以上。

### 8.7 Next Stage

下一阶段建议实现 Stage 3：Periodic Elite Improvement。

目标：

```text
GA evolution
-> every interval generations
-> select diverse elites
-> short ALNS refine
-> inject improved feasible solutions back to population
```

这样 ALNS 不再只是最后补救，而是参与 GA 演化过程。Stage 3 能检验两种方法是否真的互补。
---

## 9. Stage 2.5: Vehicle-Preserving ALNS Refinement

### 9.1 Motivation

Stage 2 的 Top-K diverse candidates 解决了“只精修 GA 第一名”的问题，但仍暴露出一个关键矛盾：ALNS 有时能减少总距离，却会增加车辆数。由于当前研究目标采用可行性和车辆数优先的词典序规则，这类结果不能替换 GA 解。

因此 Stage 2.5 的目标不是让 ALNS 更激进，而是让 ALNS 成为真正的局部精修器：

```text
如果 GA candidate 已经 feasible：
    ALNS 只能接受不增加车辆数的改进
如果 GA candidate 不可行：
    ALNS 可以通过增加车辆数修复可行性
```

### 9.2 Algorithm Changes

| File | Change |
|---|---|
| `TruckDrone_EVRPTW_NL/solvers/alns/solve.py` | `refine_state()` 新增 `preserve_vehicle_count`、`baseline_vehicle_count` 参数 |
| `TruckDrone_EVRPTW_NL/solvers/alns/solve.py` | 新增 `alns_hybrid_preserve` profile |
| `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py` | 新增 `hybrid_preserve` 模式 |
| `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py` | `hybrid_topk` 默认调用 vehicle-preserving ALNS |
| `TruckDrone_EVRPTW_NL/run_single.py` | 新增 `hybrid_preserve` 入口 |
| `TruckDrone_EVRPTW_NL/run_experiments.py` | summary 增加 preserve/refine 诊断字段 |

`alns_hybrid_preserve` 使用较轻的局部精修组合：

```text
Destroy:
- D-WorstTime
- D-Crossing
- D-DroneTask
- D-ChargingCritical

Repair:
- R-Regret2
- R-TWAware
- R-EnergyAware
- R-DroneAware

Local Search:
- LS-RelocateV2
- LS-CrossingRemoval
- LS-DroneRebuildV2
- LS-ChargingCleanup
```

它默认不启用强车辆结构变更型 `LS-RouteMergeV2`，因为 Hybrid 精修阶段的重点是保护 GA 已找到的车辆划分。

### 9.3 Validation Results

| Instance | Method | Feasible | Vehicles | Main Result |
|---|---|---:|---:|---|
| R101-5 NPC | `hybrid_preserve` | True | 2 | ALNS 产生 3 车短距离候选，但被拒绝，最终保留 GA 2 车解 |
| R101-10 NPC | `hybrid_preserve` | True | 3 | ALNS 在同车辆数下被接受，`accepted_same_vehicle_improvements=1` |
| R101-25 NPC | `hybrid_preserve` | True | 7 | ALNS 高车辆数 refinement 未替换 GA，保持车辆数优先 |

### 9.4 Interpretation

Stage 2.5 已经解决了一个具体且重要的问题：Hybrid 不再因为 ALNS 局部距离下降而接受更多车辆的解。  
这使得 Hybrid 的行为更符合当前论文实验目标：

```text
先保证可行
再控制车辆数
再比较距离、充电、等待和路线形态
```

但 Stage 2.5 本身不会显著扩大搜索空间。它更像一个“过滤和保护机制”，保证 ALNS 不破坏 GA 的全局结构。

### 9.5 Remaining Limitations

- 若 GA candidate 已经很强，ALNS 在同车辆数下的可改进空间有限。
- preserve rule 会拒绝一些距离更短但车辆数更多的解，这在车辆数优先目标下是正确行为，但也会降低 ALNS 的表面改进率。
- 当前精修仍属于后处理式融合，ALNS 尚未真正参与 GA 搜索过程。

---

## 10. Stage 3: Periodic Elite Improvement

### 10.1 Motivation

Stage 1 和 Stage 2 都属于后处理：GA 结束后，ALNS 才开始工作。这样做稳定，但融合较浅。  
Stage 3 让 ALNS 在 GA candidate pool 演化过程中周期性参与，目标是：

```text
GA 负责产生多样结构
ALNS 周期性精修精英候选
若精修结果同车辆数更优，则注入候选池
继续生成下一批候选
```

### 10.2 Algorithm Changes

新增 `hybrid_periodic` 模式。当前 GA 并不是传统长代数 population loop，因此 Stage 3 第一版采用分批候选池演化：

```text
initial GA candidate pool
-> rank and diversify
-> expand top candidates by mutation/crossover
-> every interval batch refine top elites by ALNS preserve profile
-> inject accepted refinements
-> keep diverse top candidates
-> final Top-K preserve refine
```

新增关键诊断字段：

| Field | Meaning |
|---|---|
| `periodic_trigger_count` | 周期性 ALNS 触发次数 |
| `periodic_selected_elites` | 被选中精修的 elite 数量 |
| `periodic_injected_count` | ALNS 精修后成功注入的数量 |
| `periodic_rejected_count` | 被拒绝的周期精修数量 |
| `periodic_best_before` | 周期阶段开始前最优目标 |
| `periodic_best_after` | 周期阶段结束后最优目标 |
| `population_diversity_before` | 候选池初始多样性 |
| `population_diversity_after` | 候选池最终多样性 |

### 10.3 Runtime Control

第一次 25 customers 测试中，periodic 运行时间接近 240s，说明候选池扩展过大。随后加入预算控制：

- 初始候选数量按规模限制；
- 每批 expansion 数量按规模限制；
- 主循环使用总预算约 75% 后停止；
- final Top-K refine 只使用剩余预算；
- 如果剩余时间不足 1s，则跳过 final refine。

### 10.4 Validation Results

| Instance | Method | Feasible | Runtime | Vehicles | Observation |
|---|---|---:|---:|---:|---|
| R101-5 NPC | `hybrid_periodic` | True | about 3.4s | 2 | 触发 1 次周期精修，成功注入 1 个候选 |
| R101-10 NPC | `hybrid_periodic` | True | about 15.7s | 3 | 可运行但周期注入不稳定，最终结果不一定优于 Top-K |
| R101-25 NPC | `hybrid_periodic` | True | about 97.2s | 7 | 在 120s 预算内；距离低于同次 `hybrid_preserve` 测试，但周期注入次数为 0 |

### 10.5 Interpretation

Stage 3 已经完成了“机制实现”：ALNS 可以在候选池演化过程中周期性参与，并且不会破坏可行性或无限增加运行时间。  
但从当前结果看，它的“有效注入能力”仍不足：

- 10/25 customers 中 `periodic_injected_count` 经常为 0；
- 最终结果改善更多来自候选池扩展和 final Top-K selection；
- ALNS preserve refine 与 GA decoder 的行为仍有重叠，导致同车辆数下可接受改进较少。

### 10.6 Current Conclusion

Stage 3 不是无效，但目前还不是稳定优于 `hybrid_topk` 的主方法。它的研究价值在于证明：

1. 周期性融合可以稳定运行；
2. 时间预算可以控制；
3. ALNS 注入必须有更强互补邻域，否则固定周期调用的收益有限。

### 10.7 Next Step

下一步不建议盲目提高 ALNS 周期频率。更合理的方向是：

```text
Stage 4: Stagnation-triggered ALNS
```

也就是只有当 GA candidate pool 连续若干批次没有改善时，才触发 ALNS，并配合随机移民或结构扰动。这比固定周期调用更节省时间，也更符合 ALNS 作为“跳出局部停滞工具”的定位。
---

## 11. Stage 4: Stagnation-triggered ALNS

### 11.1 Motivation

Stage 3 的 `hybrid_periodic` 已经证明 ALNS 可以参与 GA candidate pool 的演化过程，但固定周期调用存在一个问题：ALNS 被调用时，GA 可能还没有停滞，因此很多 refine 结果会被拒绝，`periodic_injected_count` 经常为 0。

Stage 4 将触发方式改为：

```text
GA candidate pool 正常演化
如果连续若干 batch 没有改进
或候选池多样性过低
才触发 ALNS
```

这不是 failure-triggered ALNS，而是 stagnation-triggered ALNS。GA 可行但停滞时，ALNS 才作为跳出局部停滞的工具介入。

### 11.2 Algorithm Changes

新增 `hybrid_stagnation` 模式：

```text
initial GA candidate pool
-> expand candidates by mutation/crossover
-> detect no-improvement stagnation
-> detect low population diversity
-> refine diverse elites with alns_hybrid_preserve
-> inject improved solutions
-> if no injection, add immigrant candidates
-> final Top-K preserve refinement
```

新增诊断字段：

| Field | Meaning |
|---|---|
| `stagnation_trigger_count` | 停滞触发次数 |
| `stagnation_selected_elites` | 被 ALNS 精修的 elite 数量 |
| `stagnation_injected_count` | 成功注入的 refined candidate 数量 |
| `stagnation_rejected_count` | 被拒绝的 ALNS refine 数量 |
| `stagnation_immigrant_count` | ALNS 失败后注入的 immigrant 数量 |
| `stagnation_best_before` | 停滞阶段前的 best cost |
| `stagnation_best_after` | 最终 best cost |
| `stagnation_batches` | 触发停滞的 batch 编号 |
| `alns_called_due_to_no_improvement` | 因无改进触发 ALNS 的次数 |
| `alns_called_due_to_low_diversity` | 因多样性过低触发 ALNS 的次数 |

### 11.3 Validation Results

| Instance | Method | Feasible | Vehicles | Runtime | Trigger | Injected | Observation |
|---|---|---:|---:|---:|---:|---:|---|
| R101-5 NPC | `hybrid_stagnation` | True | 2 | about 3.1s | 1 | 1 | 低多样性触发，成功注入 1 个候选 |
| R101-10 NPC | `hybrid_stagnation` | True | 3 | about 17.6s | 1 | 0 | 无改进触发，ALNS 未成功注入，注入 3 个 immigrants |
| R101-25 NPC | `hybrid_stagnation` | True | 7 | about 94.8s | 1 | 0 | 预算内完成，最终可行，但 ALNS 停滞注入仍未成功 |

### 11.4 Interpretation

Stage 4 达到了工程目标：

1. `hybrid_stagnation` 可以独立运行；
2. 触发原因可以区分为 no improvement 和 low diversity；
3. 运行时间可控；
4. 可行性没有被破坏；
5. ALNS 仍遵守 vehicle-preserving rule。

但从效果上看，Stage 4 也暴露了更明确的问题：

```text
触发机制已经有效
但 ALNS 在 GA 高质量解附近的同车辆数改进能力仍不足
```

因此，当前瓶颈不再是“什么时候调用 ALNS”，而是“ALNS 被调用后能不能做出 GA 做不到的局部改进”。

### 11.5 Comparison with Stage 3

| Aspect | `hybrid_periodic` | `hybrid_stagnation` |
|---|---|---|
| Trigger | 固定 batch 间隔 | 无改进或低多样性 |
| ALNS role | 周期性尝试精修 | 停滞时尝试跳出局部最优 |
| Runtime | 已可控 | 已可控 |
| Injection | 不稳定 | 小规模可注入，中规模仍偏弱 |
| Research meaning | 证明过程内融合可运行 | 证明触发机制更合理，但邻域仍需增强 |

### 11.6 Current Conclusion

`hybrid_stagnation` 比 `hybrid_periodic` 更符合 Hybrid 的算法逻辑，但还没有证明稳定优于 `hybrid_topk`。当前最重要的发现是：

```text
继续调整触发频率意义不大。
下一步必须增强 Hybrid 专用 ALNS 邻域。
```

### 11.7 Next Step

Stage 5 应实现 Hybrid-specific ALNS neighborhood。重点不是新建独立 ALNS baseline，而是给 Hybrid refine 增加更适合 GA 解附近局部优化的小邻域：

```text
H-RelocateSameVehicle
H-SwapSameVehicle
H-CrossRouteRelocateNoNewVehicle
H-DroneReassign
H-LaunchRecoverAdjust
H-ChargingPolish
H-WaitingReduction
H-PetalPolish
```

目标是提高：

```text
accepted_same_vehicle_improvements
stagnation_injected_count
hybrid_stagnation 相对 hybrid_topk 的稳定优势
```
---

## 12. Stage 5: Hybrid-Specific ALNS Local Neighborhood

### 12.1 Motivation

Stage 4 的结果说明，`hybrid_stagnation` 的触发机制已经可以运行，但中规模实例中 `stagnation_injected_count` 仍经常为 0。也就是说，问题不再主要是“什么时候调用 ALNS”，而是“ALNS 被调用后能否在 GA 已有可行解附近做出低风险、同车辆数的有效精修”。

因此 Stage 5 不再增加大范围 destroy/repair，而是新增 Hybrid 专用小邻域。它们只在 GA 解附近做局部调整，并且遵守 vehicle-preserving rule。

### 12.2 New Hybrid-Specific Profile

新增 ALNS profile：

```text
alns_hybrid_local
```

该 profile 用于 Hybrid refine 阶段，默认由 `hybrid_stagnation` 调用。独立 ALNS baseline 不使用该 profile，因此不会改变 ALNS 作为独立对比方法的行为。

`alns_hybrid_local` 的 local operators 包括：

| Operator | Purpose |
|---|---|
| `H-RelocateSameVehicle` | 在同一辆车内部移动客户，尝试降低距离、等待或时间窗压力 |
| `H-SwapSameVehicle` | 在同一辆车内部交换两个客户，减少局部绕行 |
| `H-CrossRouteRelocateNoNewVehicle` | 跨路线移动客户，但不允许新增车辆 |
| `H-DroneReassign` | 重建 truck/drone 服务方式，保留有收益的无人机任务 |
| `H-LaunchRecoverAdjust` | 调整无人机任务的 launch/recover，降低同步等待 |
| `H-ChargingPolish` | 局部替换或删除充电安排 |
| `H-WaitingReduction` | 专门尝试降低 waiting time 和 sync wait |
| `H-PetalPolish` | 在不破坏硬约束的前提下改善路线形态 |

### 12.3 Acceptance Rule

所有 H operators 都采用保守接受规则：

```text
candidate must be feasible
candidate vehicle_count must equal baseline vehicle_count
candidate rank must be better than current rank
```

rank 仍沿用项目当前统一规则：

```text
feasible
-> total_violation
-> vehicle_count
-> completion_time
-> total_distance
-> charging_time
-> waiting_time + petal_score
```

因此，H operators 不能通过增加车辆数、放松时间窗或隐藏电量违反来获得表面改进。

### 12.4 Diagnostics

新增诊断字段：

| Field | Meaning |
|---|---|
| `hybrid_local_operator_calls` | H operators 总调用次数 |
| `hybrid_local_operator_successes` | H operators 成功产生更优可行解次数 |
| `same_vehicle_relocate_successes` | 同车 relocate 成功次数 |
| `same_vehicle_swap_successes` | 同车 swap 成功次数 |
| `no_new_vehicle_relocate_successes` | 跨路线但不增车 relocate 成功次数 |
| `drone_reassign_successes` | 无人机任务重建成功次数 |
| `launch_recover_adjust_successes` | launch/recover 调整成功次数 |
| `charging_polish_successes` | 充电微调成功次数 |
| `waiting_reduction_successes` | 等待压缩成功次数 |
| `petal_polish_successes` | 花瓣状微调成功次数 |

这些字段同时写入 `hybrid_details` 和批量实验的 `summary.csv`。

### 12.5 Validation Results

| Instance | Feasible | Vehicles | Runtime | Hybrid Profile | Local Calls | Local Successes | Injected | Key Observation |
|---|---:|---:|---:|---|---:|---:|---:|---|
| R101-5 NPC | True | 2 | about 3.79s | `alns_hybrid_local` | 3200 | 194 | 1 | 小规模中可直接注入改进候选 |
| R101-10 NPC | True | 3 | about 16.98s | `alns_hybrid_local` | 3008 | 114 | 0 | 有局部成功，但未超过最终候选选择规则 |
| R101-25 NPC | True | 7 | about 98.13s | `alns_hybrid_local` | 1832 | 67 | 0 | 预算内可行，最终目标约改善 8.01%，但停滞阶段未直接注入 |

### 12.6 Operator-Level Interpretation

本轮测试中，最有效的算子是：

```text
H-DroneReassign
H-CrossRouteRelocateNoNewVehicle
```

这说明当前 GA 解的主要可优化空间仍集中在：

1. 哪些客户由无人机服务；
2. 无人机任务如何替代卡车绕行；
3. 个别客户是否可以跨路线移动且不增加车辆。

成功数仍为 0 的算子包括：

```text
H-RelocateSameVehicle
H-SwapSameVehicle
H-LaunchRecoverAdjust
H-ChargingPolish
H-WaitingReduction
H-PetalPolish
```

这不一定说明这些思路无效，而是说明当前实现的候选生成仍偏保守，或者 GA 生成的路线已经在这些简单邻域下较难继续改进。

### 12.7 Current Conclusion

Stage 5 的工程目标已经达到：

1. `hybrid_stagnation` 默认使用 Hybrid-specific ALNS local neighborhood；
2. 新 H operators 不破坏可行性；
3. 25 customers 能在预算内运行；
4. 诊断字段能显示每类小邻域的真实贡献；
5. 小邻域确实能产生局部成功。

但 Stage 5 还没有完全解决 Hybrid 的核心研究问题：

```text
ALNS refine 的局部成功仍不稳定转化为最终注入。
```

这意味着当前 Hybrid 已经比简单串联更深入，但距离“稳定优于 GA 和 ALNS 单方法”的论文级混合算法仍需要批量实验验证。

### 12.8 Next Step

下一步不应继续盲目增加 H operator，而应先做批量对比：

```text
GA
ALNS-full
hybrid_topk
hybrid_preserve
hybrid_periodic
hybrid_stagnation
```

如果批量结果显示 Stage 5 在 10/25 customers 上稳定优于 Stage 4，则继续强化：

```text
same-vehicle relocate
same-vehicle swap
waiting reduction
launch/recover adjustment
```

如果批量结果显示 Stage 5 只在少数实例有效，则下一阶段应转向：

```text
GA candidate diversity redesign
```

因为这说明 ALNS 小邻域本身不是唯一瓶颈，GA 提供给 ALNS 的候选结构可能过于同质。
## 2026-08-11 Stage 6: Batch Validation Before Further Hybrid Enhancement

### Motivation

Stage 5 已经把 `hybrid_stagnation` 接入 `alns_hybrid_local`，并能在单算例中保持可行。但单个 R101 结果不足以判断 Hybrid 是否真的优于 GA、ALNS 或旧 Hybrid。Stage 6 因此先建立批量验证和自动汇总，而不是继续新增算子。

### Changed files

| File | Role |
|---|---|
| `configs/hybrid_stage6_debug.yaml` | 10 customers debug 批量验证配置 |
| `configs/hybrid_stage6_25.yaml` | 25 customers 中规模验证配置 |
| `hybrid_stage6_report.py` | 从最新 `summary.csv` 生成 Hybrid 对比汇总 |
| `results/hybrid_stage6_summary.csv` | 方法级汇总结果 |
| `docs/hybrid_stage6_report.md` | Stage 6 自动分析报告 |

### Experiment setup

Debug 批次采用：

```text
instances: R101, C101, RC101
customer_counts: 10
charging_policies: NPC
seed: 1987
methods:
  - ga
  - alns_full
  - hybrid_topk
  - hybrid_preserve
  - hybrid_periodic
  - hybrid_stagnation
```

### Observed debug results

| Method | Feasible Rate | Avg Vehicles | Avg Distance | Avg Runtime | Hybrid Local Successes | Stagnation Injected |
|---|---:|---:|---:|---:|---:|---:|
| GA | 100.00% | 3.000 | 349.970 | 4.625s | 0 | 0 |
| ALNS-full | 100.00% | 3.667 | 351.370 | 4.036s | 0 | 0 |
| hybrid_topk | 100.00% | 3.000 | 371.125 | 13.598s | 0 | 0 |
| hybrid_preserve | 100.00% | 3.000 | 358.810 | 8.213s | 0 | 0 |
| hybrid_periodic | 100.00% | 3.000 | 361.742 | 17.699s | 0 | 0 |
| hybrid_stagnation | 100.00% | 3.000 | 361.346 | 18.146s | 169 | 0 |

### Interpretation

Stage 6 debug 结果说明：

1. 所有方法在 10 customers debug 批次中都能保持可行。
2. `hybrid_stagnation` 的 H operators 确实产生了局部成功动作，`hybrid_local_operator_successes = 169`。
3. 但 `stagnation_injected_count = 0`，说明这些局部动作尚未稳定变成可注入、可替换、可改善最终候选池的解。
4. GA 在平均距离和运行时间上仍然很强，当前 Hybrid 不能简单宣称已经明显优于 GA。
5. `hybrid_stagnation` 与 `hybrid_topk` 的胜负关系不稳定，因此下一步重点应是验证 25 customers，并优先考虑 GA candidate diversity。

### Next decision

如果 25 customers 中仍出现：

```text
hybrid_local_operator_successes > 0
stagnation_injected_count = 0
hybrid_stagnation 不稳定优于 hybrid_topk / GA
```

则下一阶段不应继续增加 H operator，而应转向：

```text
1. 增强 GA 候选多样性；
2. 增强 route split / service_mode / drone task / charging policy 多样性；
3. 让 Top-K 起点真正结构不同；
4. 再让 ALNS 做局部精修。
```

### Validation commands

```powershell
D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m compileall VRP_project/TruckDrone_EVRPTW_NL
D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_experiments --config configs/hybrid_stage6_debug.yaml
D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.hybrid_stage6_report
```
