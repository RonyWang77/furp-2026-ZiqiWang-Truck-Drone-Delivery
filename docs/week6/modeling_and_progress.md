# Truck-Drone EVRPTW-NL 建模与进度记录

本文档用于长期记录 Truck-Drone EVRPTW-NL 问题的建模规则、约束实现方式、方法定位、阶段性工作成果和后续修改记录。

后续凡是修改 `TruckDrone_EVRPTW_NL` 中的数据结构、评价规则、充电逻辑、GA、ALNS、Hybrid 或实验脚本，都必须同步更新本文档。

---

## 1. Problem Definition

### 1.1 研究问题

Truck-Drone EVRPTW-NL 指：

```text
一辆电动卡车携带一架无人机，从单仓库出发，在客户时间窗内完成配送。
客户可由卡车或无人机服务一次。
卡车受容量、电池和充电站约束。
无人机受续航、容量、起飞/回收和同步约束。
卡车充电支持线性/非线性、满充/部分充电策略。
```

### 1.2 模型来源

| 模型组成 | 来源 | 说明 |
|---|---|---|
| 时间窗 | Schneider E-VRPTW | 客户有 ready time 和 due time，早到可等待，迟到不可行 |
| 电动卡车 | Schneider E-VRPTW | 卡车有电池容量和能耗约束 |
| 充电站 | Schneider E-VRPTW | 卡车可访问固定充电站补电 |
| 释放/回收 | ETRD-NL | 辅助配送设备从卡车释放，在后续节点回收 |
| 同步等待 | ETRD-NL | 卡车和辅助设备在回收点等待并同步 |
| 非线性充电 | ETRD-NL | 高 SOC 区间充电更慢，可用分段函数近似 |
| 无人机直线飞行 | 本研究新增假设 | 无人机不同于地面机器人，采用欧氏直线距离 |
| 无人机续航 | 本研究新增假设 | 无人机每次 sortie 必须满足电池续航 |
| 无人机起降时间 | 本研究新增假设 | 通过 launch_time 和 recover_time 表示 |

### 1.3 第一版最小模型取舍

第一版只实现最小自洽模型：

- 单仓库；
- 单电动卡车；
- 单无人机；
- 无人机一次只服务一个客户；
- 无人机不访问地面充电站；
- 卡车支持 LFC、LPC、NFC、NPC 四种充电策略；
- OR-Tools 和 PyVRP 仅作为 truck-only baseline；
- GA、ALNS、GA+ALNS 作为后续主要扩展方法。

---

## 2. Entities and Data

### 2.1 实体表

| 实体 | 字段 | 来源 | 说明 |
|---|---|---|---|
| depot | id, x, y, time_window | Solomon | 仓库，默认 id 为 0 |
| customer | id, x, y, demand, ready_time, due_time, service_time | Solomon | 客户，必须被服务一次 |
| station | id, x, y | 生成 | 卡车充电站，无人机第一版不访问 |
| truck | capacity, battery, speed, consumption_rate | 配置生成 | 电动卡车 |
| drone | capacity, battery, speed, consumption_rate, launch_time, recover_time | 配置生成 | 无人机 |

### 2.2 数据来源规则

- 客户坐标、需求、时间窗、服务时间来自 Solomon JSON 数据。
- 充电站由实例构造器生成，不直接来自 Solomon 原始客户字段。
- 卡车容量优先沿用 Solomon vehicle capacity。
- 卡车电池、充电速率、无人机电池、无人机速度等由配置文件生成。
- 固定随机种子生成实例，保证不同方法使用相同数据。

### 2.3 当前默认数据策略

第一阶段建议使用：

```text
instances: R101, C101, RC101
customer_counts: 5, 10
seed: 1987
charging_policies: LFC, LPC, NFC, NPC
```

后续扩展到：

```text
customer_counts: 10, 25, 50, 100
seeds: 42, 64, 128, 256, 512
```

---

## 3. Solution Schema

### 3.1 完整解结构

Truck-Drone EVRPTW-NL 的完整解不能只用普通 `routes` 表示，至少需要保存卡车路线、无人机任务和充电计划。

```python
solution = {
    "truck_route": [0, ..., 0],
    "drone_tasks": [
        {"launch": i, "customer": k, "recover": j}
    ],
    "charging_plan": [
        {
            "station": s,
            "position_after": i,
            "arrival_energy": e1,
            "target_energy": e2,
            "charging_policy": "LFC|LPC|NFC|NPC"
        }
    ]
}
```

### 3.2 字段含义

| 字段 | 含义 |
|---|---|
| `truck_route` | 卡车访问顺序，包含仓库、卡车服务客户、无人机起飞/回收节点、充电站 |
| `drone_tasks` | 无人机任务列表，每个任务为 `(launch, customer, recover)` |
| `charging_plan` | 卡车充电决策，记录在哪个位置充电、充多少、采用哪种策略 |

### 3.3 模块职责边界

| 模块 | 是否允许修改 solution | 职责 |
|---|---:|---|
| `route_simulator.py` | 否 | 只计算时间、电量、等待、充电和违反情况 |
| `evaluator.py` | 否 | 汇总 feasible、violations 和 metrics |
| GA decoder | 是 | 根据染色体生成或改变 solution |
| ALNS operators | 是 | destroy/repair/local search 改变 solution |
| Hybrid | 是 | 组合 GA 全局结构和 ALNS 局部优化 |

重要原则：

```text
route_simulator.py 不是 repair。
它不能插入客户、删除客户、新增车辆、改变充电站或修改无人机任务。
```

---

## 4. Constraint Rules

### 4.1 约束总表

| 约束 | 数学/逻辑规则 | 实现位置 | 是否硬约束 |
|---|---|---|---|
| 客户唯一服务 | 每个客户由卡车或无人机服务一次 | evaluator | 是 |
| 卡车起终点 | `truck_route` 从 0 出发并返回 0 | evaluator | 是 |
| 无人机任务合法性 | launch/recover 必须在 truck_route 中，且 launch 在 recover 前 | evaluator | 是 |
| 卡车容量 | 所有客户需求不超过卡车容量 | route_simulator/evaluator | 是 |
| 无人机容量 | drone customer demand <= drone capacity | route_simulator/evaluator | 是 |
| 时间窗 | service_start <= due_time，早到可等待 | route_simulator/evaluator | 是 |
| 卡车电量 | truck energy 始终非负且不超过容量 | route_simulator/evaluator | 是 |
| 无人机续航 | sortie energy <= drone battery | route_simulator/evaluator | 是 |
| 充电策略 | LFC/LPC/NFC/NPC 决定 charging_time | charging/route_simulator | 是 |
| 同步 | recover 处早到方等待，双方汇合后卡车继续 | route_simulator/evaluator | 是 |

### 4.2 客户唯一服务

对每个客户 `k`：

```text
served_by_truck(k) + served_by_drone(k) = 1
```

实现规则：

- 若客户 `k` 出现在 `truck_route` 中，表示卡车服务。
- 若客户 `k` 出现在 `drone_tasks[].customer` 中，表示无人机服务。
- 同时出现表示重复服务。
- 都不出现表示客户遗漏。

输出违反项：

```text
customer_missing_violation
customer_duplicate_violation
customer_coverage_violation
```

### 4.3 卡车路线起终点

卡车路线必须满足：

```text
truck_route[0] = 0
truck_route[-1] = 0
```

如果卡车路线为空、起点不是仓库或终点不是仓库，则不可行。

### 4.4 无人机任务合法性

每个无人机任务：

```text
m = (launch, customer, recover)
```

必须满足：

```text
launch in truck_route
recover in truck_route
position(launch) < position(recover)
customer is drone-eligible
customer not served by truck
```

第一版只允许单客户 sortie，不允许一个任务连续服务多个客户。

### 4.5 单无人机资源约束

第一版只有一架无人机，因此无人机任务不能时间重叠：

```text
No overlapping drone sorties
```

实现上可以先通过路线顺序保证：后一项无人机任务的 launch 必须发生在前一项任务 recover 之后。

### 4.6 时间窗约束

客户 `k` 的服务开始时间必须满足：

```text
ready_time[k] <= service_start[k] <= due_time[k]
```

规则：

- 早到可以等待到 `ready_time`。
- 迟到不可行。
- 服务结束可以晚于 due time，但服务开始不能晚于 due time。

### 4.7 卡车时间传播

若卡车从节点 `i` 到节点 `j`：

```text
truck_arrival[j] = truck_departure[i] + truck_travel_time(i, j)
truck_service_start[j] = max(truck_arrival[j], ready_time[j])
truck_departure[j] = truck_service_start[j] + service_time[j] + charging_time[j] + sync_wait[j]
```

其中：

- `charging_time[j]` 只有当 `j` 是充电站且 charging_plan 指定在此充电时才大于 0；
- `sync_wait[j]` 只有当 `j` 是无人机 recover 节点时才可能大于 0。

### 4.8 无人机时间传播

对无人机任务 `(i, k, j)`：

```text
drone_launch_time = truck_departure[i] + launch_time
drone_arrival_customer = drone_launch_time + drone_travel_time(i, k)
drone_service_start = max(drone_arrival_customer, ready_time[k])
drone_depart_customer = drone_service_start + service_time[k]
drone_arrival_recover = drone_depart_customer + drone_travel_time(k, j) + recover_time
```

### 4.9 卡车-无人机同步

在 recover 节点 `j`：

```text
joint_departure[j] = max(truck_arrival[j], drone_arrival_recover)
truck_wait = max(0, drone_arrival_recover - truck_arrival[j])
drone_wait = max(0, truck_arrival[j] - drone_arrival_recover)
```

同步规则：

- 卡车先到，则卡车等待无人机。
- 无人机先到，则无人机等待卡车。
- 双方都到达后，卡车才能继续下一段路线。

### 4.10 容量约束

卡车出发时携带所有将由本系统服务的货物，包括卡车客户和无人机客户。

```text
sum(demand of all served customers) <= truck_capacity
```

无人机每次任务：

```text
demand[drone_customer] <= drone_capacity
```

### 4.11 电量约束

卡车电量传播：

```text
truck_energy_after_arc = truck_energy_before_arc - truck_consumption_rate * truck_distance(i, j)
0 <= truck_energy <= truck_battery_capacity
```

无人机电量传播：

```text
drone_energy_used =
    drone_consumption_rate * drone_distance(launch, customer)
  + drone_consumption_rate * drone_distance(customer, recover)

drone_energy_used <= drone_battery_capacity
```

### 4.12 距离与速度

第一版默认：

- 卡车距离使用 Solomon 坐标计算，可复用现有欧氏距离矩阵。
- 无人机距离使用欧氏直线距离。
- 卡车行驶时间 = 卡车距离 / 卡车速度。
- 无人机飞行时间 = 无人机距离 / 无人机速度。
- 若速度设为 1，则时间等于距离。

---

## 5. Charging Model

### 5.1 四种充电策略

| 策略 | 含义 | target energy | charging time |
|---|---|---|---|
| LFC | Linear Full Charging，线性满充 | battery capacity | 线性函数 |
| LPC | Linear Partial Charging，线性部分充电 | 后续可行所需电量 | 线性函数 |
| NFC | Nonlinear Full Charging，非线性满充 | battery capacity | 分段非线性函数 |
| NPC | Nonlinear Partial Charging，非线性部分充电 | 后续可行所需电量 | 分段非线性函数 |

### 5.2 线性充电

```text
charging_time = (target_energy - arrival_energy) / linear_recharge_rate
```

### 5.3 非线性充电

非线性充电使用 SOC 分段函数：

```text
SOC = energy / battery_capacity
charging_time = F(target_SOC) - F(arrival_SOC)
```

建模含义：

- 低 SOC 区间充电较快；
- 高 SOC 区间充电较慢；
- `F(SOC)` 是累计充电时间函数；
- 第一版可使用分段线性近似。

### 5.4 满充与部分充电

满充：

```text
target_energy = truck_battery_capacity
```

部分充电：

```text
target_energy = enough energy for next required feasible segment + safety_margin
```

第一版部分充电采用局部可行策略，不声明全局最优。

### 5.5 当前阶段取舍

- 第一版只对卡车建模充电。
- 无人机不访问地面充电站。
- 无人机每次起飞时视为可用满电或已完成车载换电。
- 无人机充电或换电属于后续扩展。

---

## 6. Method Mapping

### 6.1 方法定位表

| 方法 | 今日定位 | 后续实现方式 |
|---|---|---|
| OR-Tools | truck-only baseline | 不修改原实现，只作为仅卡车对比 |
| PyVRP | truck-only baseline | 不修改原实现，只作为仅卡车对比 |
| GA | 主扩展方法之一 | 编码客户顺序 + 服务方式 + 充电策略 |
| ALNS | 主扩展方法之一 | state 显式包含 truck_route、drone_tasks、charging_plan |
| GA+ALNS | 研究型混合方法 | GA 管全局结构，ALNS 管任务、同步和充电细节 |

### 6.2 OR-Tools

当前定位：

```text
仅卡车 VRPTW/E-VRPTW baseline。
```

原则：

- 不修改旧 OR-Tools 实现；
- 不强行加入无人机同步；
- 不强行加入非线性充电；
- 后续用于回答“如果没有无人机，仅卡车路线表现如何”。

### 6.3 PyVRP

当前定位：

```text
仅卡车 VRPTW/CVRPTW baseline。
```

原则：

- 不修改旧 PyVRP 实现；
- 不把 PyVRP 作为无人机协同主算法；
- 后续用于提供较强的 truck-only route baseline。

### 6.4 GA

后续扩展方向：

```text
customer_order: [k1, k2, ...]
service_mode:  [T, D, T, ...]
charging_policy: LFC/LPC/NFC/NPC
```

GA 负责：

- 搜索客户全局顺序；
- 决定客户由卡车还是无人机服务；
- 生成粗略卡车路线；
- 生成初始充电策略；
- 调用 simulator 评价，而不是依赖 full repair。

### 6.5 ALNS

后续 state 至少包含：

```python
state = {
    "truck_route": [...],
    "drone_tasks": [...],
    "charging_plan": [...],
    "unassigned_customers": [...]
}
```

ALNS 负责：

- 改变无人机任务；
- 优化 launch/recover；
- 插入或删除充电站；
- 调整目标 SOC；
- 进行局部路线优化；
- 基于 simulator 直接判断候选动作是否可行。

### 6.6 GA+ALNS

推荐分工：

```text
GA:
  global customer order
  truck/drone service mode
  rough route structure

ALNS:
  mission structure
  launch/recover optimization
  charging station placement
  target SOC refinement
  local route improvement
```

禁止：

```text
GA 和 ALNS 都只生成普通路线，然后交给同一个 full repair。
```

---

## 7. Today's Work Log

```text
Date: 2026-07-26

Today's goal:
建立 Truck-Drone EVRPTW-NL 初步建模方案，并明确各约束如何进入后续代码。

Completed:
1. 明确新问题不直接修改 EVRPTW_Schneider2014。
2. 明确 OR-Tools 和 PyVRP 仅作为 truck-only baseline。
3. 明确 GA、ALNS、GA+ALNS 是后续主研究方法。
4. 明确 route_simulator 只做状态传播，不做路线修复。
5. 明确完整 solution 需要保存 truck_route、drone_tasks、charging_plan。
6. 明确四种充电策略 LFC/LPC/NFC/NPC。
7. 明确后续从小规模到大规模的实验扩展路线。
8. 创建长期维护文档 TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md。
```

---

## 8. Change Log

## 2026-07-26 Change

Changed files:
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`

Reason:
- 为 Truck-Drone EVRPTW-NL 新问题建立长期维护的建模与进度记录文档。

Modeling impact:
- 明确了问题定义、实体、解结构、硬约束、充电策略和方法定位。
- 明确 `route_simulator.py` 只做状态传播，不做路线修复。

Algorithm impact:
- 暂未实现或修改任何算法。
- 明确 OR-Tools 和 PyVRP 后续仅作为 truck-only baseline。
- 明确 GA、ALNS、GA+ALNS 是后续主扩展方法。

Validation:
- 文档已创建。
- 内容包含问题定义、实体、解结构、约束、充电模型、方法映射、今日记录和后续变更日志模板。

Remaining issues:
- 尚未创建 `TruckDrone_EVRPTW_NL` 的代码模块。
- 尚未实现 `solution_schema.py`、`charging.py`、`route_simulator.py`、`evaluator.py`。
- 尚未实现无人机任务仿真和非线性充电实验。

## 2026-07-26 Change - Initial code expansion

Changed files:
- `TruckDrone_EVRPTW_NL/README.md`
- `TruckDrone_EVRPTW_NL/config.py`
- `TruckDrone_EVRPTW_NL/data_loader.py`
- `TruckDrone_EVRPTW_NL/instance_builder.py`
- `TruckDrone_EVRPTW_NL/solution_schema.py`
- `TruckDrone_EVRPTW_NL/charging.py`
- `TruckDrone_EVRPTW_NL/route_simulator.py`
- `TruckDrone_EVRPTW_NL/evaluator.py`
- `TruckDrone_EVRPTW_NL/visualization.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/configs/debug_small.yaml`
- `TruckDrone_EVRPTW_NL/solvers/common.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_alns.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_truck_only_ortools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_truck_only_pyvrp.py`

Reason:
- 将问题从 truck-only E-VRPTW 初步扩展为 Truck-Drone EVRPTW-NL。
- 建立可运行的新模块，避免直接修改 `EVRPTW_Schneider2014` 中已有 OR-Tools、PyVRP、GA、ALNS baseline。

Modeling impact:
- 新增完整解结构：`truck_route`、`drone_tasks`、`charging_plan`。
- 新增无人机参数：容量、电池、速度、能耗率、起飞时间、回收时间。
- 新增四种充电策略接口：LFC、LPC、NFC、NPC。
- `route_simulator.py` 只负责传播时间、电量、充电和同步状态，不负责修复路线。

Algorithm impact:
- 新增 `ga_td`：使用 GA-style 随机客户顺序构造 truck-drone 解。
- 新增 `alns_td`：使用 ALNS-style 最近邻客户顺序构造 truck-drone 解。
- 新增 `hybrid_td`：分别运行 GA-style 和 ALNS-style 构造器，保留统一 evaluator 下更好的结果。
- OR-Tools 和 PyVRP 只保留 truck-only baseline 占位 wrapper，本次没有修改旧代码。

Validation:
- 已通过单算例运行：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC`
- 已通过批量运行：
  - `python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
- 已通过路线图保存：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method hybrid --charging-policy NPC --save-plot`
- 输出文件：
  - `TruckDrone_EVRPTW_NL/results/raw_results.jsonl`
  - `TruckDrone_EVRPTW_NL/results/summary.csv`
  - `TruckDrone_EVRPTW_NL/figures/*.png`

Remaining issues:
- 当前 solver 只是初步构造方法，不是成熟优化算法。
- 当前可行性主要受时间窗违反影响，说明后续必须把 time-window-aware construction/insertion 写进 GA、ALNS 和 Hybrid。
- 当前充电决策只处理卡车电量，未处理无人机充电或换电。
- 当前无人机任务只支持单客户 sortie：`launch -> customer -> recover`。
- 当前 Hybrid 仍是浅层组合，后续需要让 GA 负责全局结构、ALNS 负责任务/同步/充电细节优化。

## 2026-07-27 Change - Feasibility diagnostics

Changed files:
- `TruckDrone_EVRPTW_NL/route_simulator.py`
- `TruckDrone_EVRPTW_NL/solution_schema.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`

Reason:
- 第一阶段诊断改造：把 `feasible=True/False` 拆解为百分比指标和逐节点诊断。
- 明确当前 R101-5 的不可行主要来自哪些时间窗失败节点，而不是只看到一个 `False`。

Modeling impact:
- `route_simulator.py` 仍然只做状态传播，不修改输入 solution。
- truck trace 增加节点类型、时间窗、电量、充电、同步等待和违反量。
- drone trace 增加无人机任务时间窗、电量使用、续航违反和回收时间。
- 新增 feasibility 字段，用百分比表达客户覆盖、时间窗、电量、容量、同步等约束满足程度。

Algorithm impact:
- 本次没有优化 GA、ALNS、Hybrid 的生成逻辑。
- 本次只增强诊断能力，为后续 TW-aware、Energy-aware、Sync-aware 算法改造提供依据。

Validation:
- 已通过语法检查：
  - `python -m compileall TruckDrone_EVRPTW_NL`
- 已通过 R101-5 单算例诊断：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC --diagnose`
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method alns --charging-policy NPC --diagnose`
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method hybrid --charging-policy NPC --diagnose`
- 已通过批量实验：
  - `python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
- `summary.csv` 已新增 `feasibility_rate`、各类约束百分比、失败节点和失败任务字段。

R101-5 initial diagnosis:
- GA + NPC:
  - `time_window_feasibility_rate = 20.00%`
  - failed nodes: `11, 52, 76, 77`
  - truck and drone battery feasibility are both `100.00%`
- ALNS + NPC:
  - `time_window_feasibility_rate = 40.00%`
  - failed nodes: `9, 11, 76`
  - truck and drone battery feasibility are both `100.00%`
- Hybrid + NPC:
  - same selected solution as ALNS in this test
  - `time_window_feasibility_rate = 40.00%`
- Conclusion: current infeasibility mainly comes from time-window order and synchronization timing, not from customer coverage, capacity, or battery.

Remaining issues:
- Percent rates are diagnostic indicators only; they do not make an infeasible solution feasible.
- Current GA/ALNS still need constraint-aware construction and insertion logic.
- Next stage should implement time-window-aware truck insertion and drone launch/recover evaluation.

## 2026-07-27 Change - GA aware decoder v1

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`

Reason:
- 优先优化 GA 方法，使 GA 不再依赖固定 `drone_stride` 机械分配无人机任务。
- 参考前期 GA 优化建议，将内部目标改为可行性优先：先压低约束违反，再考虑完成时间、距离、充电和等待。
- 增加简单 mutation 候选，包括客户顺序交换和路线片段反转。

Modeling impact:
- GA decoder 显式构造 `truck_route`、`drone_tasks`、`charging_plan`。
- 无人机任务仍限制为单客户 sortie：`launch -> customer -> recover`。
- 无人机任务必须保证 launch/recover 在卡车路线中且结构违反不能增加。
- 充电策略仍只作用于卡车，支持 LFC/LPC/NFC/NPC。

Algorithm impact:
- 新增 `ga_tools.py`，包含：
  - `simulate_partial_truck_route()`
  - `evaluate_truck_insertion()`
  - `evaluate_drone_task()`
  - `select_best_drone_task()`
  - `build_ga_aware_solution()`
  - `mutated_orders()`
- `solve_ga.py` 默认使用 `aware_insertion_v1` decoder。
- GA 内部插入评分采用：
  - 第一优先级：总约束违反量；
  - 第二优先级：客户覆盖、容量、电量、无人机任务结构违反；
  - 第三优先级：completion_time；
  - 第四优先级：total_distance + charging_time + waiting_time。
- ALNS 未做算子改造；Hybrid 因调用 GA，会自然使用新的 GA 结果。

Validation:
- 已通过语法检查：
  - `python -m compileall TruckDrone_EVRPTW_NL`
- 已通过 R101-5 GA 单算例诊断：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC --diagnose`
- 已通过 Hybrid 单算例诊断：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method hybrid --charging-policy NPC --diagnose`
- 已通过批量实验：
  - `python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
- 由于 `summary.csv` 被外部程序占用，本次批量结果保存为：
  - `TruckDrone_EVRPTW_NL/results/summary_20260727_175156.csv`

R101-5 GA comparison:
- Before GA-aware decoder:
  - `time_window_feasibility_rate = 20.00%`
  - `total_violation ≈ 372.561`
  - failed nodes: `11, 52, 76, 77`
- After GA-aware decoder with NPC:
  - `time_window_feasibility_rate = 40.00%`
  - `total_violation ≈ 3.086`
  - failed nodes: `9, 11, 76`
  - customer coverage, capacity, truck battery, drone battery and sync remain valid.
- Interpretation:
  - GA 仍未达到完全可行，但时间窗违反量显著下降。
  - 当前剩余问题已从“严重迟到”变为“少量边界时间窗违反”。

Remaining issues:
- 当前 GA 仍不是真正完整遗传算法，只是 GA-style 多候选 decoder。
- mutation 目前只作用于客户顺序，尚未显式编码服务方式、充电策略和 launch/recover 基因。
- 下一阶段应继续优化 GA 的 service_mode chromosome，或转向 ALNS 的 TW-aware/Dron-aware repair 算子。

## 2026-07-28 Change - GA service-mode and multi-vehicle decoder

Changed files:
- `TruckDrone_EVRPTW_NL/route_simulator.py`
- `TruckDrone_EVRPTW_NL/solution_schema.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/visualization.py`
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`

Reason:
- 继续只优化 GA 方法，使 GA 不再局限于单车单路线。
- 引入 `service_mode chromosome`，让 GA 同时表达客户顺序、服务方式、充电策略和最大车辆数。
- 引入 `truck_routes` 多车辆 schema，使算法可以在单车不可行时自动扩展车辆数。
- 保留旧字段 `truck_route` 作为兼容入口，避免旧的单路线调用立即失效。

Modeling impact:
- 新标准解结构支持：
  - `truck_routes: [[0, ..., 0], ...]`
  - `drone_tasks` 中的 `route_index`
  - `charging_plan` 中的 `route_index`
- 每条卡车路线独立传播时间、电量、等待和充电状态。
- 每条路线内无人机任务只允许绑定本路线的 launch/recover 节点。
- 第一版仍假设每条路线有独立无人机，不考虑跨路线共享无人机。
- 第一版无人机任务仍为单客户 sortie：`launch -> customer -> recover`。

Algorithm impact:
- `ga_tools.py` 新增或强化：
  - `make_ga_individual()`
  - `decode_ga_individual()`
  - `candidate_individuals()`
  - `mutate_individual()`
  - `default_max_vehicle_count()`
  - `select_best_drone_task_multi()`
  - `_insert_customer_into_best_route()`
  - `_build_solution_for_vehicle_count()`
- GA decoder 现在按以下流程生成解：
  - 生成 `customer_order + service_mode + charging_policy + max_vehicle_count`
  - 从 1 辆车开始尝试
  - 对 truck 客户做多路线插入
  - 对 drone 客户枚举同路线 launch/recover
  - 无人机不可行或更差时 fallback 为 truck
  - 每条路线独立插入充电站
  - 用统一 evaluator 严格检查
- 车辆数选择采用可行性优先：
  - 先最小化 `total_violation`
  - 若可行，则优先保留较少车辆
  - 再比较 completion time、距离、充电和等待

Validation:
- 已通过编译检查：
  - `python -m compileall TruckDrone_EVRPTW_NL`
- 已通过 R101-5 GA + NPC 单算例诊断：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC --diagnose`
- 关键结果：
  - `feasible = True`
  - `vehicle_count = 2`
  - `total_violation = 0`
  - `time_window_feasibility_rate = 100.00%`
  - `truck_battery_feasibility_rate = 100.00%`
  - `drone_battery_feasibility_rate = 100.00%`
  - `sync_feasibility_rate = 100.00%`
- 已通过批量回归：
  - `python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
- 已验证路线图保存：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC --save-plot`
  - 输出图片：`TruckDrone_EVRPTW_NL/figures/R101_5_seed1987_td_ga_td_NPC.png`

R101-5 GA comparison:
- Before this stage:
  - `time_window_feasibility_rate = 40.00%`
  - `total_violation ≈ 3.086`
  - `vehicle_count = 1`
- After this stage:
  - `time_window_feasibility_rate = 100.00%`
  - `total_violation = 0`
  - `vehicle_count = 2`
- Interpretation:
  - 本阶段通过增加车辆数和服务方式 fallback，把小规模 R101-5 从边界不可行推进到完全可行。
  - 成本增加来自车辆数增加、充电绕行和等待时间，这是为了满足硬约束付出的代价。

Batch observation:
- `R101/C101/RC101` 的 5 客户实例中，GA 在四种充电策略下均能找到可行解。
- 10 客户实例仍存在不可行结果，说明后续需要继续优化：
  - service_mode 更精细初始化；
  - 更强的 time-window-aware 插入；
  - 更强的 route split / route rebalance；
  - 对 10/25 客户逐步扩大实验。

Remaining issues:
- 当前 GA 仍是候选构造式 GA，不是完整的标准种群进化 GA。
- `service_mode` mutation 已有基础版本，但仍较简单。
- 当前 decoder 可显著提升小规模可行性，但不能保证所有 10/25 客户实例可行。
- 每条路线内无人机任务暂不允许复杂并行调度，也不考虑多无人机共享。
- ALNS 和 Hybrid 尚未针对多路线 truck-drone schema 做独立增强。

## 2026-07-28 Change - GA multi-customer and charging-capable drone sortie Stage 1-3

Changed files:
- `TruckDrone_EVRPTW_NL/route_simulator.py`
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/visualization.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`

Reason:
- 进一步提升 GA 的问题表达能力，使其不再局限于单客户无人机任务。
- 参考 ETRD-NL 中机器人可连续服务多个客户、可访问充电站的机制，将其迁移为 Truck-Drone EVRPTW-NL 中更真实的无人机 sortie。
- 本阶段只增强 GA 相关构造能力；ALNS、OR-Tools、PyVRP baseline 不做修改。

Modeling impact:
- 当前版本以本条记录为准，覆盖早期“无人机一次只服务一个客户”和“无人机不访问地面充电站”的简化假设。
- 无人机任务支持：
  - 同车发射；
  - 同车回收；
  - `drone_route = [launch, customer_1, customer_2, station, ..., recover]`；
  - 多客户连续服务；
  - 访问已有充电站；
  - 无人机充电时间进入同步传播。
- 仍不支持：
  - 跨车发射/回收；
  - 生成新的充电站；
  - 无人机脱离任务后在路线外自由移动。
- `charging_plan` 现在可用 `vehicle = "truck" | "drone"` 区分卡车和无人机充电记录。

Algorithm impact:
- GA individual 扩展为：
  - `customer_order`
  - `service_mode`
  - `drone_priority`
  - `charging_policy`
  - `max_vehicle_count`
  - `route_split_bias`
  - `drone_charging_preference`
- GA decoder 新流程：
  - 先构造多车辆 truck base routes；
  - 再把适合的 drone-mode 客户组合为多客户 `drone_route`；
  - 若无人机电量不足，允许在 `drone_route` 中插入已有充电站；
  - 若无人机任务不可行或收益不足，则客户 fallback 为 truck；
  - 最终由统一 evaluator 严格检查。

Validation:
- 已通过编译：
  - `python -m compileall TruckDrone_EVRPTW_NL`
- 已通过 R101-5 GA + NPC 诊断：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC --diagnose`
- R101-5 GA + NPC 关键结果：
  - `feasible = True`
  - `vehicle_count = 2`
  - `total_violation = 0`
  - 出现多客户无人机任务：`52 ---> 76 ---> 77 ---> 0`
- 已通过手工无人机充电传播测试：
  - 手工构造 `drone_route = [52, 76, 1000, 0]`
  - `charging_count = 1`
  - `charging_time = 12.625`
  - 说明无人机访问充电站时，充电时间已进入 simulator。
- 已通过批量实验：
  - `python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
- 已通过路线图保存：
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 5 --method ga --charging-policy NPC --save-plot`

Observed results:
- 5 customers:
  - GA 在 `R101/C101/RC101` 多个充电策略下保持可行。
  - R101-5 的 GA + NPC 距离从上一阶段约 `205.69` 降到约 `189.01`，并出现多客户无人机任务。
- 10 customers:
  - C101-10 中 GA 多个策略已可行。
  - R101-10 和 RC101-10 仍存在不可行，说明 Stage 1-3 提升了表达能力，但还不足以稳定解决更复杂时间窗实例。
- Runtime:
  - `debug_small.yaml` 批量运行约 208 秒，明显慢于上一阶段。
  - 主要原因是多客户 `drone_route` 和 launch/recover 枚举扩大了搜索空间。
- 25-customer pressure test:
  - `python -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 25 --method ga --charging-policy NPC`
  - 300 秒内未完成。
  - 结论：Stage 1-3 已提升模型表达能力，但还不能直接支撑 25/50 客户规模；进入 Stage 4-8 前必须增加候选剪枝、时间预算、route rebalance 和更强 mutation/crossover。

Remaining issues:
- 当前 Stage 1-3 是增强 decoder，不是完整成熟 GA。
- 多客户无人机任务搜索已有剪枝，但 10/25/50 客户规模下仍需要更强的 route split、merge、rebalance 和专用 mutation。
- 无人机充电曲线暂时复用卡车 LFC/LPC/NFC/NPC，后续可单独校准无人机电池曲线。
- 25/50 客户要达到较优秀水平，需要进入 Stage 4-8。

Next stage recommendation:
- 若继续推进，应进入 Stage 4-8：
  - Truck-Drone 专用 mutation；
  - route split / merge / rebalance；
  - route-preserving crossover；
  - 多样性控制；
  - GA 作为 Hybrid 初始解来源。
- 同时需要控制运行时间，建议为 GA decoder 增加候选数量、launch/recover 数量、单算例时间预算等配置。

## 2026-07-28 Change - GA Stage 4: Hierarchical pruning for drone sortie search

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`

Reason:
- Stage 1-3 允许多客户无人机任务和无人机访问充电站后，`launch/recover` 与客户组枚举空间急剧扩大。
- `R101-25 + GA + NPC` 曾在 300 秒内无法完成，说明不能继续全量枚举。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的数学问题定义。
- 无人机仍可服务多个客户，仍可访问充电站。
- 本阶段只限制 decoder 每次运行中优先检查的候选数量，不设置模型层面的无人机客户数上限。

Algorithm impact:
- 新增候选控制参数：
  - `MAX_DRONE_CANDIDATES_PER_ROUTE`
  - `MAX_DRONE_EXTENSION_ROUNDS`
  - `MAX_LAUNCH_RECOVER_PAIRS`
- 新增 `_rank_drone_candidate_pool()`，按无人机优先级、空间距离和 due time 选择候选客户。
- 新增 `_rank_launch_recover_pairs()`，优先测试与无人机客户组空间更匹配的发射/回收节点。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL` 通过。
- `R101-5 + GA + NPC + --diagnose` 通过。

Observed results:
- R101-5 保持可行，运行约 `0.165s`。
- R101-25 从 Stage 1-3 的 300 秒超时变为可在几十秒内完成。

Remaining issues:
- 剪枝会牺牲一部分搜索完整性，因此后续需要通过多样性候选、mutation 和 crossover 弥补。

## 2026-07-28 Change - GA Stage 5: Evaluation cache and light route rebalance

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`

Reason:
- GA decoder 内部会反复对相同或相近的 `solution` 调用统一 evaluator。
- 多路线构造后，部分客户被过早放入不合适路线，会造成时间窗违反。

Modeling impact:
- 不改变解结构。
- 不引入统一 repair；rebalance 只是 GA decoder 自己构造解时的候选移动。

Algorithm impact:
- 新增 `_evaluate_cached()` 与 `_solution_cache_key()`。
- 新增 `_rebalance_routes()`，在无人机任务转换前做有限次数跨路线客户移动。
- `_insert_customer_into_best_route()` 支持 `route_split_bias`，使 GA 染色体可以影响客户分配到哪条卡车路线。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL` 通过。
- R101-25 可完成运行，不再出现 Stage 1-3 的 300 秒超时。

Observed results:
- R101-25 首轮优化后可在约 `17s` 完成，但因车辆上限偏小，时间窗仍不可行。

Remaining issues:
- 轻量 rebalance 只移动少量客户，不等价于完整 route merge/split 局部搜索。

## 2026-07-28 Change - GA Stage 6: Truck-Drone specialized mutation

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`

Reason:
- 普通 GA mutation 只交换客户顺序，无法充分探索 truck/drone 服务方式、充电偏好和路线分配。

Modeling impact:
- 不改变约束。
- 强化 GA 对完整解结构的搜索能力：客户顺序、服务方式、车辆分配倾向、无人机优先级和充电偏好都可以变化。

Algorithm impact:
- `mutate_individual()` 增加：
  - 多个客户的 `truck <-> drone` 服务方式翻转；
  - 客户顺序交换；
  - 客户顺序片段反转；
  - `drone_priority` 扰动；
  - `route_split_bias` 扰动；
  - `drone_charging_preference` 切换；
  - `max_vehicle_count` 小范围调整。

Validation:
- R101-5 保持可行。
- R101-25 可在约一分钟内完成。

Observed results:
- mutation 能产生更多无人机任务组合，但单独依靠 mutation 不足以保证 R101-25/R101-50 可行，仍需要车辆扩展和结构保留候选。

Remaining issues:
- 当前 mutation 仍是启发式扰动，尚未形成基于失败节点的 targeted mutation。

## 2026-07-28 Change - GA Stage 7: Incremental vehicle expansion and route split strategy

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`

Reason:
- R101 类实例时间窗紧，过少车辆会导致即使电量、容量和同步均满足，仍然出现迟到。
- 本阶段目标是先保证硬约束可行，再由后续 ALNS/Hybrid 压缩车辆数和总距离。

Modeling impact:
- 不改变“车辆数应尽量少”的研究目标。
- 但求解优先级明确调整为：
  1. 约束违反为 0；
  2. 在可行解中减少车辆数；
  3. 再减少距离、充电、等待和同步成本。

Algorithm impact:
- `default_max_vehicle_count()` 从偏保守的 4/10 上限逐步放宽为按客户规模自适应。
- GA 仍从 1 辆车开始尝试，只有不可行时才递增车辆数。
- 对 25/50 客户规模，允许更多路线分散紧时间窗压力。

Validation:
- `R101-25 + GA + NPC`：
  - `feasible = True`
  - `vehicle_count = 8`
  - `total_violation = 0`
  - `runtime_seconds ≈ 54.7s`
- `R101-50 + GA + NPC`：
  - `feasible = True`
  - `vehicle_count = 16`
  - `total_violation = 0`
  - `runtime_seconds ≈ 260.4s`

Observed results:
- 25 客户和 50 客户均能得到硬约束可行解。
- 代价是车辆数偏多、等待时间和充电次数偏高。

Remaining issues:
- 当前 GA 已达到“可行性优先”的实验基础，但尚未达到“车辆数和距离优秀”的最终论文水平。
- 后续应由 ALNS 的 route merge、relocate、2-opt* 和 energy-aware repair 来压缩车辆数与距离。

## 2026-07-28 Change - GA Stage 8: Route-preserving crossover, diversity anchor and time budget

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`

Reason:
- TW 排序有利于时间窗，但可能丢掉原先可行的服务方式组合。
- 只依赖单一顺序或单一 seed 不稳定。
- 50 客户必须有时间预算，避免单方法无限运行。

Modeling impact:
- 不改变问题模型。
- 增强 GA 搜索的工程可控性和实验可复现性。

Algorithm impact:
- 新增 `crossover_individual()`：
  - 保留一段父代客户顺序；
  - 由另一个父代补齐剩余客户；
  - 同时继承 `service_mode`、`drone_priority`、`route_split_bias` 和无人机充电偏好。
- 新增 `_mode_shifted_individual()`：
  - 生成 truck-heavy 与 drone-heavy 候选，用于保留搜索多样性。
- 新增 `_deduplicate_individuals()`：
  - 去除重复候选，控制运行成本。
- `default_ga_orders()` 新增：
  - 按 ready time / due time 排序；
  - 按 due time / ready time 排序；
  - 原始 id 顺序；
  - 随机顺序。
- `solve_ga.py` 新增默认时间预算：
  - 5 customers: 15s
  - 10 customers: 45s
  - 25 customers: 120s
  - 50 customers: 240s
  - 更大规模: 360s

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL` 通过。
- `R101-5 + GA + NPC + --diagnose`：
  - `feasible = True`
  - `vehicle_count = 2`
  - `total_violation = 0`
  - `runtime_seconds ≈ 0.165s`
- `R101-25 + GA + NPC`：
  - `feasible = True`
  - `vehicle_count = 8`
  - `total_violation = 0`
  - `runtime_seconds ≈ 54.7s`
- `R101-50 + GA + NPC`：
  - `feasible = True`
  - `vehicle_count = 16`
  - `total_violation = 0`
  - `runtime_seconds ≈ 260.4s`
- `debug_small.yaml` 批量回归：
  - 命令：`python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
  - 运行约 `74.5s`
  - `summary.csv` 和 `raw_results.jsonl` 正常更新
  - GA 在 R101/C101/RC101 的 5/10 客户、四种充电策略下均返回可行解
  - 当前 Hybrid 继承 GA 可行解，也均返回可行解
  - ALNS baseline 仍不可行，本轮未修改 ALNS，属于预期遗留问题

Observed results:
- Stage 4-8 解决了 Stage 1-3 的核心运行问题：25 客户不再超时。
- GA 已能在 25/50 客户规模下输出硬约束可行解。
- 当前解偏保守，适合作为后续 ALNS/Hybrid 的可行初始解。

Remaining issues:
- 50 客户运行时间仍偏长，约 4 分钟级别。
- 当前 GA 的主要价值是“构造可行解”，不是最终压缩成本。
- 下一步应转向 ALNS：
  - route merge；
  - relocate；
  - 2-opt*；
  - time-window critical removal；
  - energy-aware insertion；
  - drone sortie re-optimization。

### Future Change Template

```text
## YYYY-MM-DD Change

Changed files:
- ...

Reason:
- ...

Modeling impact:
- ...

Algorithm impact:
- ...

Validation:
- ...

Remaining issues:
- ...
```

---

## 9. Update Rule for Future Changes

后续每次改动必须同步更新本文档：

- 新增字段时，更新 `Entities and Data` 或 `Solution Schema`；
- 新增约束时，更新 `Constraint Rules`；
- 修改充电逻辑时，更新 `Charging Model`；
- 修改 GA/ALNS/Hybrid 时，更新 `Method Mapping`；
- 每次实验或代码阶段结束后，更新 `Today's Work Log` 或 `Change Log`。

建议执行规则：

```text
每次代码修改完成后，先运行最小验证，再追加 Change Log。
如果没有更新本文档，则该次修改视为未完整完成。
```

---

## 10. Test Plan

文档层面检查：

- 文件存在于 `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`；
- 中文显示正常；
- 包含问题定义、实体、解结构、约束、充电策略、方法映射、今日记录、后续变更日志；
- 后续每次代码修改前后都能明确找到需要同步更新的章节。

后续代码层面检查：

- `charging.py` 能区分 LFC/LPC/NFC/NPC；
- `route_simulator.py` 不修改输入 solution；
- `evaluator.py` 能输出所有 violation；
- 可手算验证 `truck_route = [0, 1, 3, S, 4, 0]` 与 `drone_task = (1, 2, 3)`；
- OR-Tools 和 PyVRP truck-only baseline 不受新模块影响。

---

## 11. Assumptions

- 文档使用中文 Markdown。
- 文档作为项目长期说明文件，不是一次性周报。
- 今日只记录建模和初步扩展成果，不记录尚未实现的算法效果。
- 后续所有 Truck-Drone EVRPTW-NL 相关代码改动都必须同步维护该文档。
- 当前使用 Solomon 数据构造 paper-like instances，不声称完全复现两篇论文的原始 benchmark。
