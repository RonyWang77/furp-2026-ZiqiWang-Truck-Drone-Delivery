# ALNS Development Report

本文档记录 `TruckDrone_EVRPTW_NL` 中 ALNS 方法从 scaffold 到独立可对比算法的改造过程。当前阶段目标不是使用 GA 解作为初始解，而是让 ALNS 自己构造初始解，并通过 destroy、repair、local search 算子独立求解 Truck-Drone EVRPTW-NL。

## 1. Current Position

当前 ALNS 的定位：

- 独立方法，不调用 GA 求解结果；
- 允许多车辆；
- 支持多客户无人机任务结构；
- 支持无人机访问已有充电站；
- 支持卡车充电和无人机充电；
- 支持 LFC、LPC、NFC、NPC 四种充电策略；
- 统一使用项目已有 evaluator 和 route simulator 做最终可行性判断。

OR-Tools 和 PyVRP 仍作为 truck-only baseline，不参与完整 Truck-Drone ALNS。

## 2. Phase 1 Implemented

### 2.1 State Structure

新增：

```text
TruckDrone_EVRPTW_NL/solvers/alns/state.py
```

核心结构：

```python
ALNSState(
    clean_truck_routes=[[0, ..., 0], ...],
    drone_tasks=[...],
    unassigned_customers=[],
    metadata={}
)
```

设计原因：

- `clean_truck_routes` 不含充电站，避免 destroy/repair 直接操作充电站导致客户结构混乱；
- 评价前再 materialize 成完整 solution；
- `drone_tasks` 显式保存 `route_index`、`launch`、`recover`、`drone_route`、`customers` 和无人机充电计划。

### 2.2 Independent Initial Solution

新增独立初始构造逻辑：

```text
customers sorted by due_time / ready_time
-> regret insertion into truck routes
-> limited vehicle expansion
-> materialize truck charging
-> try drone rebuild
-> evaluate
```

该流程不使用 GA 输出。它先追求 truck-only 可行，再尝试无人机任务改善。

### 2.3 Destroy Operators

当前已实现并命名：

| Operator | Purpose |
|---|---|
| D-Random | 随机移除客户，提供基础扰动 |
| D-WorstTime | 优先移除时间窗压力大的客户 |
| D-RouteRemoval | 删除低利用率路线，尝试减少车辆 |
| D-DroneTask | 删除无人机任务并释放其客户 |

### 2.4 Repair Operators

当前已实现并命名：

| Operator | Purpose |
|---|---|
| R-Regret2 | 选择 regret 值高的客户优先插入，避免困难客户最后无处可插 |
| R-TWAware | 当前复用完整 evaluator 评分，插入时考虑时间窗违反 |
| R-EnergyAware | 当前复用完整 evaluator 评分，插入时考虑电量和充电违反 |
| R-DroneAware | 修复后尝试无人机任务重建 |

说明：当前 `R-TWAware` 与 `R-EnergyAware` 已经通过统一 evaluator 做完整约束评分，但内部仍不是严格增量传播版本。后续若优化运行速度，需要进一步改为局部增量计算。

### 2.5 Local Search Operators

当前已实现：

| Operator | Purpose |
|---|---|
| LS-RouteMerge | 尝试合并两条路线，减少车辆数 |
| LS-Relocate | 移动客户到其他位置或路线，改善局部结构 |
| LS-DroneRebuild | 重新构造多客户无人机任务、发射点、回收点和无人机充电 |

### 2.6 Acceptance and Adaptive Selection

当前 ALNS 主循环：

```text
current_state
-> select destroy
-> destroy
-> select repair
-> repair
-> local search
-> evaluator
-> feasibility-first acceptance
-> update best
-> update operator weights
```

接受规则：

- 更优解直接接受；
- 轻微变差解按模拟退火概率接受；
- 严重不可行解拒绝；
- best solution 必须通过统一 ranking 比较，不把明显更差解作为最终结果。

比较顺序：

```text
1. feasible
2. total_violation
3. vehicle_count
4. completion_time
5. total_distance
6. charging_time
7. waiting_time
```

## 3. Diagnostics

新增输出：

```text
TruckDrone_EVRPTW_NL/results/alns_diagnostics.csv
TruckDrone_EVRPTW_NL/results/alns_operator_summary.csv
TruckDrone_EVRPTW_NL/results/alns_ablation_summary.csv
```

记录内容包括：

- candidate_solution_count；
- feasible_candidate_count；
- accepted_solution_count；
- improved_solution_count；
- route_merge_attempts；
- route_merge_successes；
- drone_rebuild_attempts；
- drone_rebuild_successes；
- new_vehicle_created_count；
- operator_success_rate。

终端也会打印简明诊断：

```text
ALNS diagnostics:
  candidates: ...
  feasible rate: ...
  acceptance rate: ...
  improvement rate: ...
  route merge successes: ...
  drone rebuild successes: ...
```

## 4. Validation Results

已运行最小验证：

| Instance | Policy | Feasible | Vehicles | Total Distance | Charging Count | Runtime |
|---|---|---:|---:|---:|---:|---:|
| R101-5 | NPC | True | 3 | 161.151 | 0 | 0.845s |
| R101-10 | NPC | True | 3 | 240.500 | 3 | 5.497s |
| C101-5 | NPC | True | 2 | 258.629 | 3 | 0.932s |
| RC101-5 | NPC | True | 2 | 249.188 | 3 | 1.042s |

观察：

- ALNS 已经从不可行 scaffold 变成能独立构造可行解的方法；
- R101-5、R101-10、C101-5、RC101-5 均满足硬约束；
- C101-5 出现了无人机任务，说明 `drone_route` 结构、同步和无人机充电接口可用；
- 当前路线仍偏保守，route merge 成功率较低，说明后续需要强化减少车辆数和距离的局部搜索。

已运行批量回归：

```powershell
python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml
```

批量范围：

- instances: `R101`, `C101`, `RC101`
- customer counts: `5`, `10`
- charging policies: `LFC`, `LPC`, `NFC`, `NPC`
- methods: `GA`, `ALNS`, `Hybrid`

批量结果：

- `summary.csv` 正常更新；
- `raw_results.jsonl` 正常更新；
- ALNS 诊断文件正常追加；
- ALNS 在该批次中均返回 `feasible=True`。

阶段性判断：

- Phase 1 已满足“小规模独立可行构造”的目标；
- 当前 ALNS 已可作为独立方法进入后续对比；
- 但当前 ALNS 仍偏保守，尤其是 `route_merge_successes` 较低，说明它还没有充分体现 ALNS 的路线压缩能力。

## 5. Current Limitations

1. `R-TWAware` 和 `R-EnergyAware` 仍主要依赖完整 evaluator 评分，不是高性能增量版本。
2. `LS-DroneRebuild` 能生成无人机任务，但当前目标函数下不一定愿意接受无人机任务。
3. `LS-RouteMerge` 成功率暂时较低，说明路线合并需要与客户重排、充电重排一起做。
4. 当前还没有实现 `D-Cluster`、`D-SyncCritical`、`D-ChargingCritical`。
5. 当前还没有正式做 25/50 客户批量消融实验。

## 6. Next ALNS Phases

### Phase 2：25 Customers Feasibility

重点：

- 强化 `D-RouteRemoval`；
- 实现更强的 `R-VehicleReduction`；
- 加入更细的 TW/Energy incremental insertion；
- 限制新开车辆，优先塞回已有路线。

### Phase 3：Drone Task Deep Support

重点：

- 增强 `R-DroneAware`；
- 增强 `R-SyncAware`；
- 增强 `LS-DroneRebuild`；
- 更主动地调整 launch/recover；
- 比较无人机多客户任务和卡车服务之间的真实收益。

### Phase 4：Vehicle and Distance Optimization

重点：

- `LS-RouteMerge`；
- `LS-Relocate`；
- `LS-2OptStar`；
- `LS-Swap`；
- 在可行前提下降低车辆数和总距离。

### Phase 5：Nonlinear Charging Optimization

重点：

- `LS-ChargingCleanup`；
- charging station replacement；
- partial charge target adjustment；
- LFC/LPC/NFC/NPC 对比。

### Phase 6：Ablation Study

重点：

- 输出 `operator_summary.csv`；
- 输出 `alns_ablation_summary.csv`；
- 对比每个算子组合的贡献；
- 形成可写入论文的方法分析。

## 7. Petal-Shaped ALNS Extension

本阶段加入花瓣状空间结构引导。

新增 ALNS operators：

| Type | Operators |
|---|---|
| Destroy | `D-Cluster`, `D-AngleSector`, `D-Crossing`, `D-RouteOverlap`, `D-SyncCritical`, `D-ChargingCritical` |
| Repair | `R-ClusterInsertion`, `R-SweepInsertion`, `R-PetalAware`, `R-VehicleReduction`, `R-DroneAwareV2`, `R-SyncAwareV2`, `R-ChargingAwareV2` |
| Local Search | `LS-RouteMergeV2`, `LS-RelocateV2`, `LS-2OptStar`, `LS-CrossingRemoval`, `LS-RouteRecluster`, `LS-DroneRebuildV2`, `LS-ChargingCleanup`, `LS-PetalPolish` |

评价函数新增软指标：

- `petal_score`
- `crossing_count`
- `route_compactness`
- `sector_coherence`
- `depot_radial_consistency`

当前观察：

- 小规模可行性保持较好。
- 25 客户可运行并保持可行。
- 但 25 客户候选数偏低，说明 V2 算子计算成本较高。
- `crossing_count` 在 25 客户下仍偏高，后续应继续强化 crossing removal 和 2-opt*。

## 8. Targeted Operator Simplification and Repair

本阶段针对“算子过多但有效改善不足”的问题进行修复。

### 8.1 修改动机

当前 ALNS 已经可以稳定输出可行解，但默认组合过大，部分算子只是对已有逻辑的轻量封装；同时 `route_merge_successes` 经常为 0，车辆压缩能力不足。25 customers 下完整 evaluator 调用较多，也会放大运行时间。

### 8.2 默认组合调整

默认 profile 改为 `alns_core`。

| Type | Default operators |
|---|---|
| Destroy | `D-Random`, `D-WorstTime`, `D-RouteRemoval`, `D-DroneTask`, `D-Crossing` |
| Repair | `R-Regret2`, `R-TWAware`, `R-EnergyAware`, `R-DroneAware`, `R-VehicleReduction` |
| Local Search | `LS-RouteMergeV2`, `LS-RelocateV2`, `LS-CrossingRemoval`, `LS-DroneRebuildV2`, `LS-ChargingCleanup` |

弱封装算子仍保留在代码中，但不再默认启用。

### 8.3 关键算子增强

- `LS-CrossingRemoval`：优先尝试同路线 2-opt、跨路线 2-opt*，失败后才移除 crossing customers 并重插。
- `LS-RouteMergeV2`：增加路线对快速筛选，优先测试空间相近、角度相邻、规模较小的路线对。
- `R-VehicleReduction`：记录 vehicle reduction attempts/successes，用于判断车辆压缩是否真实发生。

### 8.4 Profile 消融接口

新增 profile：`alns_core`, `alns_vehicle`, `alns_petal`, `alns_drone`, `alns_full`。

新增配置：`TruckDrone_EVRPTW_NL/configs/alns_ablation_debug.yaml`。

### 8.5 验证结果

| Case | Profile | Feasible | Vehicles | Distance | Runtime | Key Diagnostics |
|---|---|---:|---:|---:|---:|---|
| R101-5 NPC | alns_core | True | 3 | 161.151 | 2.056s | feasible rate 100% |
| R101-10 NPC | alns_core | True | 3 | 240.500 | 4.084s | crossing candidates 80 |
| R101-25 NPC | alns_core | True | 9 | 710.524 | 47.507s | evaluator calls 965 |
| R101-5 NPC | alns_petal | True | 3 | 161.151 | 2.008s | crossing successes 1 |

### 8.6 当前结论

- 可行性没有被破坏。
- 候选筛选后 R101-25 运行时间有所下降。
- profile 消融已经可以批量运行。
- crossing 相关算子能触发，但在 10/25 customers 下还没有稳定改善最终路线。
- route merge 仍是最弱环节，后续需要继续增强车辆压缩逻辑。

## 9. Paper-Level Layered Candidate Evaluation

### 9.1 Motivation

当前 ALNS 的主要问题不是缺少算子名称，而是候选评价成本过高、车辆压缩成功率低、无人机任务贡献不稳定。若每个候选都直接进入完整 evaluator，25/50 customers 下运行时间会迅速放大，并且不利于系统消融。因此本阶段引入三层候选评价。

### 9.2 Algorithm Changes

- `_insertion_options()`：改为 quick candidate -> local estimate -> full evaluator。
- `LS-RouteMergeV2`：只对空间相近、角度相邻、重构后分数靠前的 Top-K route merge 候选做完整评价。
- `LS-CrossingRemoval`：先按 crossing waste 排序，再尝试 same-route 2-opt 和 cross-route 2-opt*。
- `LS-DroneRebuildV2`：先计算 `drone_gain`，只对少量 launch/recover 组合做完整评价。
- 新增 `alns_charging` profile，用于后续充电策略消融。

### 9.3 Diagnostics Added

新增诊断字段：

| Field | Meaning |
|---|---|
| `quick_candidate_count` | Layer 1 生成的候选总数 |
| `local_checked_candidate_count` | Layer 2 局部估计的候选数 |
| `filtered_by_geometry` | 被空间/角度/Top-K 过滤的候选数 |
| `filtered_by_time_window` | 被局部时间窗估计过滤的候选数 |
| `filtered_by_energy` | 被局部电量估计过滤的候选数 |
| `accepted_after_full_eval` | 通过完整 evaluator 后被接受的候选数 |
| `removed_route_customer_count` | route removal 释放客户数量 |
| `distance_delta` | 被接受候选带来的距离变化累计 |
| `runtime_delta` | 被接受局部搜索消耗时间累计 |

### 9.4 Validation Results

| Case | Profile | Feasible | Vehicles | Distance | Runtime | Key Diagnostics |
|---|---|---:|---:|---:|---:|---|
| R101-5 NPC | alns_core | True | 3 | 161.151 | 0.708s | full evaluator calls 4653 |
| R101-10 NPC | alns_core | True | 3 | 240.500 | 4.033s | full evaluator calls 11558 |
| R101-25 NPC | alns_core | True | 9 | 643.225 | 45.195s | crossing successes 7 |
| R101-5 NPC | alns_charging | True | 3 | 161.151 | 0.521s | profile runnable |

### 9.5 Current Conclusion

- 可行性没有被破坏，R101-5/10/25 均保持 `feasible=True`。
- crossing 局部搜索开始有有效贡献，R101-25 中出现 `crossing_successes=7`。
- 车辆压缩仍是最大短板，`route_merge_successes` 和 `vehicle_reduction_successes` 仍为 0。
- 无人机任务仍没有稳定贡献，后续应单独强化 `R-DroneAware` 和 `LS-DroneRebuildV2`。
- 分层评价已经形成论文级实验所需的诊断基础，但 25 customers 下 `full_evaluator_calls` 仍偏高，50 customers 前还需要进一步减少完整评价调用。

---

## 2026-08-11 ALNS Post-stage Optimization

### Motivation

当前 ALNS 已经从 scaffold 发展为可独立运行的 Truck-Drone EVRPTW-NL 方法，但仍不完全满足论文级对比算法要求。主要短板包括：

- 车辆压缩诊断长期偏弱，`route_merge_successes` 经常为 0。
- 无人机任务经常为空，说明 drone-aware 算子没有稳定进入最终解。
- 充电清理没有真实贡献，`charging_cleanup_successes` 仍为 0。
- 25 customers 下候选数量和完整 evaluator 调用仍偏高。

本阶段目标是强化已有关键算子，而不是继续堆叠新算子名称。

### Algorithm Changes

| Area | Change | Purpose |
|---|---|---|
| Vehicle reduction | `R-VehicleReduction` 增加禁止新开车的严格插回阶段 | 让删除路线释放的客户优先插入已有路线 |
| Route removal | `D-RouteRemoval` 改为综合客户数、距离、局部风险、空间重叠和时间窗松弛度选路线 | 优先删除更可能被吸收的低利用路线 |
| Route merge | `LS-RouteMergeV2` 新增“删除一条路线并将客户重插其他路线”的候选 | 不再只依赖直接拼接式合并 |
| Drone repair | `R-DroneAware` 在 repair 阶段比较 truck insertion 与 drone insertion | 让无人机进入构造过程，而不是只做后处理 |
| Drone rebuild | `LS-DroneRebuildV2` 从单客户到多客户逐步尝试 | 避免多客户组合不可行时直接放弃 |
| Drone acceptance | 新增 drone-aware comparison | 在可行和车辆数不变时，允许保留能降低 `truck_distance` 的无人机任务 |
| Charging cleanup | `LS-ChargingCleanup` 从 no-op 改为尝试路线重排和充电减少 | 为后续 LFC/LPC/NFC/NPC 消融提供入口 |
| Diagnostics | 新增 evaluator 时间、Top-K 存活率、affected route eval 等字段 | 支持运行时间分析和算子消融 |

### Validation Results

| Case | Profile | Feasible | Vehicles | Distance | Drone Tasks | Key Diagnostics |
|---|---|---:|---:|---:|---:|---|
| R101-5 NPC | alns_vehicle | True | 3 | 161.151 | 0 | `vehicle_reduction_successes=6/64` |
| R101-10 NPC | alns_drone | True | 3 | 291.057 | 2 | `drone_rebuild_successes=2` |
| R101-10 NPC | alns_charging | True | 3 | 240.500 | 0 | `charging_cleanup_successes=0/129` |
| R101-25 NPC | alns_full | True | 10 | 780.638 | 4 | `vehicle_reduction_successes=7/7`, `drone_rebuild_successes=1` |

### Interpretation

本阶段解决了一个关键问题：ALNS 现在可以产生有效无人机任务，说明算法已经不是纯 truck-only feasible constructor。但无人机参与后，候选解可行率明显下降，且 R101-25 中车辆数和总距离变差，说明当前 drone-aware 规则更适合作为消融组件，而不是直接作为默认质量最优策略。

车辆压缩方面，`vehicle_reduction_successes` 不再为 0，说明严格插回已有路线的流程有效；但 `route_merge_successes` 仍不稳定，说明真正减少车辆数仍需要更强的路线合并与路线重构。

充电方面，`LS-ChargingCleanup` 已有可运行入口和诊断，但当前测试中成功次数仍为 0。原因可能是当前候选被时间窗过滤，或者已有充电插入已经是局部可行下的较优选择。后续需要加入 station replacement 和 partial SOC target 的显式候选。

### Current Limitations

- `alns_vehicle` 当前可能受到 drone rebuild 影响，消融边界不够干净。
- 无人机任务能降低 `truck_distance`，但可能增加 `total_distance` 和同步等待。
- `full_evaluator_calls` 在 25 customers 下仍高，50 customers 运行前需要继续控制候选规模。
- `charging_cleanup_successes=0`，充电策略优化还没有形成实验证据。

### Next Step

1. 先隔离 profile：`alns_vehicle` 不应默认运行 drone rebuild，`alns_drone` 专门检验无人机贡献。
2. 强化 `LS-RouteMergeV2`，让路线合并真正减少车辆数。
3. 强化 `LS-ChargingCleanup`，加入 station replacement 和 partial charge target。
4. 运行正式消融：`alns_core`, `alns_vehicle`, `alns_drone`, `alns_charging`, `alns_petal`, `alns_full`。

---

## 2026-08-11 ALNS Freeze-preparation Fix

### Problem

固化 ALNS 前发现一个消融边界问题：即使 `alns_vehicle` 的 profile 没有启用无人机 repair/local search，初始解构造阶段仍会默认调用一次 drone rebuild。这会导致 vehicle profile 可能混入无人机任务，使“车辆压缩贡献”和“无人机贡献”难以区分。

### Change

- `_construct_initial_state()` 增加 `enable_drone_rebuild` 参数。
- `solve()` 根据当前 profile 的算子名称自动判断是否启用初始无人机重建。
- 如果 profile 中包含 `Drone` 或 `Sync` 算子，则允许初始 drone rebuild；否则保持 truck-only 初始解。

### Validation

| Case | Profile | Feasible | Drone Tasks | Result |
|---|---|---:|---:|---|
| R101-10 NPC | `alns_vehicle` | True | 0 | vehicle profile 不再被无人机任务污染 |
| R101-10 NPC | `alns_drone` | True | 2 | drone profile 仍能生成无人机任务 |

### Conclusion

该修补不改变 ALNS 的求解能力，只是让消融实验边界更清楚。完成该修补后，ALNS 可以固化为当前阶段的独立对比方法，并转向 GA+ALNS 混合方法优化。
