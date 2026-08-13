# Petal Route Design Report

本文档记录 Truck-Drone EVRPTW-NL 中“花瓣状路线”软约束的设计、实现和当前实验观察。

## 1. Definition

花瓣状路线不是硬约束，而是一种空间结构质量目标：

```text
每辆卡车负责一个相对连续的空间区域；
路线从仓库出发，服务该区域客户，再返回仓库；
不同车辆路线之间尽量少交叉；
无人机任务服务本卡车路线附近客户。
```

硬约束优先级始终高于花瓣状软目标：

```text
customer coverage
capacity
time window
battery
charging
synchronization
```

## 2. Metrics

新增空间指标：

| Metric | Meaning | Better Direction |
|---|---|---|
| `route_compactness` | 每条路线服务区域的紧凑程度 | lower |
| `sector_coherence` | 每条路线客户相对仓库的角度跨度 | lower |
| `crossing_count` | 卡车路线交叉数量 | lower |
| `depot_radial_consistency` | 路线是否从仓库向外再返回 | lower |
| `petal_score` | 综合花瓣状惩罚 | lower |

当前 `petal_score`：

```text
petal_score =
  1.0 * route_compactness
  + 0.5 * sector_coherence
  + 50.0 * crossing_count
  + 10.0 * route_overlap_penalty
  + 5.0 * depot_radial_consistency
```

说明：

- 无人机客户也会计入所属卡车路线的服务区域。
- 充电站不计入路线区域紧凑度，但会影响实际路线距离和时间。
- `crossing_count` 当前只统计卡车路线交叉。

## 3. GA Changes

GA 新增空间结构引导：

- `default_ga_orders()` 新增：
  - sweep order；
  - reverse sweep order；
  - cluster order；
  - cluster + time-window order。
- `route_split_bias` 部分来自角度聚类。
- GA 评分中加入低权重 `petal_score`。
- mutation 中加入轻量 sweep-aware 片段调整。

重要修正：

- 初始修改后，`RC101-10 + GA + NFC` 曾出现不可行。
- 原因是空间候选过早挤掉了旧的时间窗稳健候选。
- 已修正为：旧 GA 稳健候选优先，花瓣状候选作为补充。

## 4. ALNS Changes

ALNS 新增空间 destroy：

| Operator | Purpose |
|---|---|
| `D-Cluster` | 移除空间相近客户 |
| `D-AngleSector` | 移除一个极角扇区 |
| `D-Crossing` | 移除导致路线交叉的客户 |
| `D-RouteOverlap` | 处理路线区域重叠 |
| `D-SyncCritical` | 处理同步等待大的无人机任务 |
| `D-ChargingCritical` | 处理充电绕行大的片段 |

ALNS 新增空间 repair：

| Operator | Purpose |
|---|---|
| `R-ClusterInsertion` | 优先插入空间相近路线 |
| `R-SweepInsertion` | 按极角顺序插入 |
| `R-PetalAware` | 以花瓣状软惩罚参与插入评分 |
| `R-VehicleReduction` | 尝试减少车辆数 |

ALNS 新增 local search：

| Operator | Purpose |
|---|---|
| `LS-RouteMergeV2` | 合并后重排、重插充电、重建无人机 |
| `LS-RelocateV2` | relocate 后处理交叉 |
| `LS-CrossingRemoval` | 专门移除交叉相关客户并重插 |
| `LS-PetalPolish` | 对路线做扫角式局部整理 |
| `LS-ChargingCleanup` | 保持 clean route，不保留不必要充电站 |

## 5. Validation

已完成：

```powershell
python -m compileall TruckDrone_EVRPTW_NL
python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 10 --method ga --charging-policy NPC
python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 10 --method alns --charging-policy NPC
python -m TruckDrone_EVRPTW_NL.run_single --instance RC101 --customers 10 --method ga_td_petal --charging-policy NFC
python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 25 --method alns_td_petal --charging-policy NPC
python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml
```

关键结果：

| Case | Method | Feasible | Vehicles | Distance | Petal Score | Crossings |
|---|---|---:|---:|---:|---:|---:|
| R101-10 NPC | GA | True | 3 | 240.500 | 211.529 | 4 |
| R101-10 NPC | ALNS | True | 3 | 240.500 | 211.529 | 4 |
| RC101-10 NFC | GA | True | 4 | 525.141 | 169.687 | 3 |
| R101-25 NPC | ALNS | True | 9 | 710.524 | 967.846 | 19 |

## 6. Current Findings

1. 空间指标已经可用于评价和 CSV 输出。
2. GA 加入花瓣状候选后仍可恢复小规模可行性。
3. ALNS 在 25 客户下能保持可行，但当前 V2 算子较重。
4. `R101-25` 的 `crossing_count = 19`，说明花瓣状优化还没有完全解决。
5. 后续需要重点优化 `LS-CrossingRemoval` 和 `LS-RouteMergeV2` 的效率与成功率。

## 7. Remaining Issues

- 25/50 客户下候选数偏低，说明每次完整 evaluator 成本仍偏高。
- 花瓣状软约束已进入目标函数，但权重仍偏保守。
- 当前 crossing removal 只是移除交叉相关客户后重插，还不是几何 2-opt 式强优化。
- 50 客户尚未完整运行验证。

## 8. Next Recommendations

下一步优先级：

1. 对 `LS-CrossingRemoval` 做几何 2-opt / 2-opt* 增强。
2. 对 `LS-RouteMergeV2` 做候选筛选，避免 25/50 规模下候选数过低。
3. 给 ALNS 增加增量 petal metric 估计，减少完整 evaluator 调用次数。
4. 对 `petal_score` 权重做消融实验。
5. 正式运行 `petal_25.yaml`，再选择少量 50 客户压力测试。

## 9. Targeted Petal-Related ALNS Repair

本阶段没有继续增加新的花瓣状算子名称，而是修复已有花瓣状相关算子的实际行为。

### 9.1 修改内容

- 默认 ALNS 不再启用全部花瓣状封装算子，改为 `alns_core` 精简组合。
- `LS-CrossingRemoval` 从“移除 crossing customers 后重插”升级为：
  - 同一路线 crossing 优先尝试 2-opt 片段反转；
  - 不同路线 crossing 优先尝试 2-opt* 尾段交换；
  - 上述失败后才 fallback 到移除重插。
- `LS-RouteMergeV2` 增加快速筛选，只优先测试空间相近、角度相邻、规模合适的路线对。
- 新增 `alns_petal` profile，用于单独观察 crossing 和花瓣状优化的贡献。

### 9.2 新增诊断指标

- `full_evaluator_calls`
- `quick_filtered_candidates`
- `route_merge_candidates`
- `crossing_candidates`
- `crossing_successes`
- `vehicle_reduction_attempts`
- `vehicle_reduction_successes`

这些指标用于判断花瓣状优化是否只是增加计算量，还是确实改善路线结构。

### 9.3 当前观察

| Case | Profile | Feasible | Distance | Crossing Count / Success | Observation |
|---|---|---:|---:|---|---|
| R101-5 NPC | alns_petal | True | 161.151 | crossing successes 1 | 小规模能触发 crossing 修复 |
| R101-10 NPC | alns_core | True | 240.500 | crossing candidates 80, successes 0 | 发现 crossing，但改善候选未通过可行性与 ranking |
| R101-25 NPC | alns_core | True | 710.524 | crossing_count 19 | 大规模仍需要更强几何优化 |

### 9.4 结论

- 花瓣状指标和 profile 消融已经具备实验基础。
- 当前 crossing 修复已经有真实 2-opt/2-opt* 逻辑，但成功率还不稳定。
- 25/50 customers 下的下一步重点不是继续加新算子，而是强化 route merge、vehicle reduction 和 crossing candidate 的快速评价。

## 10. Layered Petal and Crossing Evaluation

### 10.1 Purpose

本阶段的花瓣状优化不再新增大量装饰性算子，而是强化已有 crossing / route merge / relocate 的候选评价。花瓣状结构仍然是软目标，不能覆盖客户覆盖、时间窗、电量、容量、充电和同步等硬约束。

### 10.2 Changes

- `LS-CrossingRemoval`：
  - 检测 crossing edges；
  - 按 crossing waste 排序；
  - 同路线优先尝试 2-opt；
  - 跨路线优先尝试 2-opt*；
  - 失败后才移除 crossing customers 并 sweep 重新插入。

- `LS-RouteMergeV2`：
  - 先筛选空间中心接近、极角相邻、客户数合适的路线对；
  - 对合并客户尝试 sweep order、reverse sweep、cluster order、due-time order、nearest insertion；
  - 只对 Top-K 候选调用完整 evaluator。

- `R-Regret2` / insertion：
  - 插入候选先通过 quick score 计算距离、车辆数、局部风险和 petal penalty；
  - 再进行局部时间窗、电量估计；
  - 最后才进入完整 evaluator。

### 10.3 Observed Results

| Case | Method | Feasible | Vehicles | Distance | Crossing Count | Crossing Successes |
|---|---|---:|---:|---:|---:|---:|
| R101-10 NPC | alns_core | True | 3 | 240.500 | 4 | 0 |
| R101-25 NPC | alns_core | True | 9 | 643.225 | 20 | 7 |

### 10.4 Interpretation

- R101-25 中 crossing local search 已经能产生可接受改进，说明 2-opt / 2-opt* 不再只是形式化存在。
- 但最终 crossing_count 仍为 20，说明花瓣状结构还没有完全形成。
- 当前更重要的瓶颈是车辆压缩和路线重构：如果路线数量偏多且客户分配保守，单纯消除 crossing 不能显著改善整体图形。

### 10.5 Next Steps

1. 强化 `R-VehicleReduction` 和 `LS-RouteMergeV2`，先让路线数量下降。
2. 在 route merge 成功后重新执行 drone rebuild 和 charging cleanup。
3. 对 `alns_core/alns_vehicle/alns_petal/alns_drone/alns_charging/alns_full` 做正式消融，验证花瓣状指标是否改善距离和车辆数，而不是只改善图片外观。

---

## 2026-08-11 Petal-related ALNS Update

### Purpose

本阶段继续把“花瓣状路线”作为软目标，而不是硬约束。所有客户覆盖、容量、时间窗、电量、充电和同步约束仍然必须优先满足。

### Changes

- `LS-CrossingRemoval` 继续采用 crossing edge 检测、crossing waste 排序、同路线 2-opt 和跨路线 2-opt* 候选。
- `LS-RouteMergeV2` 增加路线释放重插候选，尝试通过路线重构间接改善花瓣状结构。
- ALNS 诊断新增 `top_k_survival_rate`、`affected_route_eval_calls`、`average_candidate_eval_time`，用于判断花瓣状优化是否带来过高计算成本。
- 无人机任务现在可以进入最终解，因此花瓣状评价需要同时观察 `truck_distance`、`drone_distance`、`sync_wait` 和 `crossing_count`，不能只看图形是否更好看。

### Validation Snapshot

| Case | Profile | Feasible | Vehicles | Distance | Crossing Count | Petal Score | Drone Tasks |
|---|---|---:|---:|---:|---:|---:|---:|
| R101-25 NPC | previous alns_full snapshot | True | 9 | 652.362 | 23 | 1166.787 | 0 |
| R101-25 NPC | updated alns_full | True | 10 | 780.638 | 8 | 411.927 | 4 |

### Discussion

更新后的 ALNS 明显改善了路线空间结构：`crossing_count` 从约 23 降到 8，`petal_score` 从约 1166 降到约 412。这说明 crossing / drone rebuild / route restructuring 已经能影响最终路线形态。

但这个改善不是免费的。R101-25 中车辆数从 9 增加到 10，总距离也增加。这说明“花瓣状更好”和“目标函数更优”并不总是一致。后续论文实验中必须把花瓣状指标作为辅助分析，而不能单独用它证明算法更优。

### Remaining Issues

- 当前花瓣状改善主要来自更强的无人机重建和路线分区，而不是稳定的 route merge。
- 如果 `alns_vehicle` 和 `alns_petal` 混入同一批 local search，消融解释会不清楚。
- 后续需要分别报告：
  - `alns_vehicle` 是否降低车辆数；
  - `alns_petal` 是否降低 crossing 和 petal score；
  - `alns_drone` 是否降低 truck_distance；
  - `alns_full` 是否能综合平衡这些目标。

### Next Recommendation

花瓣状约束继续保留为软目标。下一阶段重点不是继续压低 `petal_score`，而是把花瓣状改善与车辆数、总距离、无人机贡献分开做消融，避免“图变好但解变差”的结论混淆。
