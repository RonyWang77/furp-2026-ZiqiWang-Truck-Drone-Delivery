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

## 2026-07-29 Change - Independent ALNS Phase 1

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/solve_alns.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/__init__.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/state.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/docs/alns_development_report.md`

Reason:
- 原 `solve_alns.py` 只是最近邻构造加固定无人机 stride 的 scaffold，不是真正 ALNS。
- 本阶段目标是让 ALNS 成为不依赖 GA 初始解的独立 Truck-Drone EVRPTW-NL 方法。

Modeling impact:
- 新增 ALNS 内部状态 `ALNSState`。
- `clean_truck_routes` 不含充电站，评价前再 materialize 成完整 solution。
- `drone_tasks` 支持 `route_index`、`launch`、`recover`、`customers`、`drone_route` 和无人机充电计划。
- 继续使用已有 route simulator 和 evaluator 做硬约束检查，不放松容量、时间窗、电量、充电和同步约束。

Algorithm impact:
- 新增独立初始解构造：按时间窗排序客户，用 regret insertion 构造 truck-only 初始解，再尝试无人机任务重建。
- 新增 destroy operators：`D-Random`、`D-WorstTime`、`D-RouteRemoval`、`D-DroneTask`。
- 新增 repair operators：`R-Regret2`、`R-TWAware`、`R-EnergyAware`、`R-DroneAware`。
- 新增 local search operators：`LS-RouteMerge`、`LS-Relocate`、`LS-DroneRebuild`。
- 新增 feasibility-first simulated annealing 接受准则和简单自适应算子权重。
- 新增 ALNS 诊断输出：`alns_diagnostics.csv`、`alns_operator_summary.csv`、`alns_ablation_summary.csv`。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL` 通过。
- `R101-5 + ALNS + NPC`：
  - `feasible = True`
  - `vehicle_count = 3`
  - `total_distance = 161.151`
  - `charging_count = 0`
  - `runtime_seconds ≈ 0.845s`
- `R101-10 + ALNS + NPC`：
  - `feasible = True`
  - `vehicle_count = 3`
  - `total_distance = 240.500`
  - `charging_count = 3`
  - `runtime_seconds ≈ 5.497s`
- `C101-5 + ALNS + NPC`：
  - `feasible = True`
  - `vehicle_count = 2`
  - `total_distance = 258.629`
  - `charging_count = 3`
  - 出现无人机任务 `84 -> 85 -> 0`
- `RC101-5 + ALNS + NPC`：
  - `feasible = True`
  - `vehicle_count = 2`
  - `total_distance = 249.188`
  - `charging_count = 3`

Observed results:
- ALNS 已经从不可行 scaffold 转为能独立构造可行解的方法。
- 5/10 客户小规模验证中，硬约束可行性明显改善。
- 当前 ALNS 可输出卡车充电计划，也能在部分实例中输出无人机任务。
- 当前解仍偏保守，route merge 成功率较低，说明后续需要继续强化车辆数和距离优化。

Remaining issues:
- `R-TWAware` 和 `R-EnergyAware` 当前仍主要依赖完整 evaluator 评分，不是高效增量传播。
- `LS-DroneRebuild` 已能生成无人机任务，但在当前目标函数下不一定经常被接受。
- 25/50 customers 尚未完成批量验证。
- `D-Cluster`、`D-SyncCritical`、`D-ChargingCritical`、`LS-ChargingCleanup` 尚未实现。

Next stage recommendation:
- Phase 2 应优先做 25 customers 可行性与车辆数压缩。
- Phase 3 再强化无人机任务、同步等待和 launch/recover 调整。
- Phase 4/5 进入路线合并、距离优化和非线性充电策略优化。

## 2026-07-29 Validation - ALNS Debug Batch Regression

Changed files:
- `TruckDrone_EVRPTW_NL/results/summary.csv`
- `TruckDrone_EVRPTW_NL/results/raw_results.jsonl`
- `TruckDrone_EVRPTW_NL/results/alns_diagnostics.csv`
- `TruckDrone_EVRPTW_NL/results/alns_operator_summary.csv`
- `TruckDrone_EVRPTW_NL/results/alns_ablation_summary.csv`

Reason:
- 验证 ALNS 独立框架是否能在 `debug_small.yaml` 批量实验中保持统一输出格式。

Modeling impact:
- 无新增建模假设。
- 本次仅验证已有 Truck-Drone EVRPTW-NL 解结构、充电策略和可行性检查的兼容性。

Algorithm impact:
- 无额外算法修改。
- 批量实验使用当前默认 ALNS 算子组合：
  - Destroy: `D-Random`, `D-WorstTime`, `D-RouteRemoval`, `D-DroneTask`
  - Repair: `R-Regret2`, `R-TWAware`, `R-EnergyAware`, `R-DroneAware`
  - Local search: `LS-RouteMerge`, `LS-Relocate`, `LS-DroneRebuild`

Validation:
- 命令：
  - `python -m TruckDrone_EVRPTW_NL.run_experiments --config configs/debug_small.yaml`
- 结果：
  - `R101/C101/RC101`
  - `5/10 customers`
  - `LFC/LPC/NFC/NPC`
  - `GA/ALNS/Hybrid`
  - 全部正常输出到 `summary.csv` 和 `raw_results.jsonl`。
- ALNS 在该批量测试中均返回 `feasible=True`。

Observed results:
- ALNS 相比旧 scaffold 的最大变化是可行性显著提升。
- 在部分实例中，ALNS 距离优于 GA；在部分 C 类实例中，GA 距离仍明显更短。
- 当前 ALNS 的 `route_merge_successes` 多数为 0，说明它还没有充分发挥 ALNS 压缩车辆数和重构路线的优势。
- `drone_rebuild_successes` 在部分 C 类实例中较高，说明无人机任务重建算子能够被触发，但并不总是带来最终距离优势。

Remaining issues:
- 需要继续做 25 customers 和 50 customers 的规模验证。
- 需要做算子消融，不能只看 Full ALNS。
- 需要强化 `LS-RouteMerge`、`LS-Relocate`、`R-VehicleReduction`，否则 ALNS 会偏向“可行但保守”。

## 2026-07-29 Change - Petal-Shaped Spatial Guidance for GA and ALNS

Changed files:
- `TruckDrone_EVRPTW_NL/spatial_metrics.py`
- `TruckDrone_EVRPTW_NL/evaluator.py`
- `TruckDrone_EVRPTW_NL/solution_schema.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/configs/petal_25.yaml`
- `TruckDrone_EVRPTW_NL/configs/petal_50.yaml`
- `TruckDrone_EVRPTW_NL/docs/petal_route_design_report.md`

Reason:
- 指导老师提出优秀 VRP 路线通常呈现“花瓣状”空间结构。
- 当前 GA/ALNS 只优化可行性、距离和时间，缺少路线分区、路线交叉和空间紧凑度评价。

Modeling impact:
- 新增花瓣状软约束，不改变硬约束。
- 新增指标：
  - `route_compactness`
  - `sector_coherence`
  - `crossing_count`
  - `depot_radial_consistency`
  - `petal_score`
- 无人机客户计入其所属卡车路线的服务区域。

Algorithm impact:
- GA:
  - 新增 sweep order、reverse sweep order、cluster order、cluster-then-TW order。
  - `route_split_bias` 支持角度聚类。
  - GA scoring 加入低权重 `petal_score`。
  - mutation 加入轻量 sweep-aware 调整。
- ALNS:
  - 新增 destroy: `D-Cluster`, `D-AngleSector`, `D-Crossing`, `D-RouteOverlap`, `D-SyncCritical`, `D-ChargingCritical`。
  - 新增 repair: `R-ClusterInsertion`, `R-SweepInsertion`, `R-PetalAware`, `R-VehicleReduction`, `R-DroneAwareV2`, `R-SyncAwareV2`, `R-ChargingAwareV2`。
  - 新增 local search: `LS-RouteMergeV2`, `LS-RelocateV2`, `LS-2OptStar`, `LS-CrossingRemoval`, `LS-RouteRecluster`, `LS-DroneRebuildV2`, `LS-ChargingCleanup`, `LS-PetalPolish`。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL` 通过。
- `R101-10 + GA + NPC`：
  - `feasible=True`
  - `vehicle_count=3`
  - `total_distance=240.500`
  - `petal_score=211.529`
  - `crossing_count=4`
- `R101-10 + ALNS + NPC`：
  - `feasible=True`
  - `vehicle_count=3`
  - `total_distance=240.500`
  - `petal_score=211.529`
  - `crossing_count=4`
- `RC101-10 + GA + NFC`：
  - 初始空间候选过强时曾出现不可行；
  - 已修正为旧 GA 稳健候选优先、花瓣候选补充；
  - 复测后 `feasible=True`。
- `R101-25 + ALNS + NPC`：
  - `feasible=True`
  - `vehicle_count=9`
  - `total_distance=710.524`
  - `petal_score=967.846`
  - `crossing_count=19`
- `debug_small.yaml` 批量回归完成并输出：
  - `summary.csv`
  - `raw_results.jsonl`
  - `petal_comparison_summary.csv`

Observed results:
- 花瓣状指标已能正常输出和比较。
- GA 的空间引导必须作为补充，而不能替代原时间窗稳健候选。
- ALNS 在 25 客户下仍可行，但 V2 算子计算较重，候选数偏低。
- `R101-25` 仍存在较多路线交叉，说明花瓣状优化已接入但还未充分发挥。

Remaining issues:
- 需要继续增强 `LS-CrossingRemoval`，当前还不是强 2-opt / 2-opt* 几何优化。
- 25/50 客户下需要减少完整 evaluator 调用，增加增量评分。
- `petal_score` 权重需要通过消融实验调参。
- `petal_50.yaml` 尚未完整运行。

---

## 2026-07-29 Change - Targeted ALNS Operator Simplification and Repair

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/configs/alns_ablation_debug.yaml`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/alns_development_report.md`
- `TruckDrone_EVRPTW_NL/docs/petal_route_design_report.md`

Reason:
- 当前 ALNS 的问题不是算子不够，而是默认算子组合过大、部分算子行为重复、完整 evaluator 调用过多。
- 本次修复目标是收敛默认组合，强化少数关键算子，并为消融实验保留 profile 切换能力。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的问题定义。
- 不改变硬约束：客户覆盖、容量、时间窗、电量、充电和同步仍由统一 evaluator 严格检查。
- 花瓣状指标仍为软约束，不允许为了路线形态破坏可行性。

Algorithm impact:
- 默认 ALNS profile 改为 `alns_core`。
- 默认 destroy 收敛为：`D-Random`, `D-WorstTime`, `D-RouteRemoval`, `D-DroneTask`, `D-Crossing`。
- 默认 repair 收敛为：`R-Regret2`, `R-TWAware`, `R-EnergyAware`, `R-DroneAware`, `R-VehicleReduction`。
- 默认 local search 收敛为：`LS-RouteMergeV2`, `LS-RelocateV2`, `LS-CrossingRemoval`, `LS-DroneRebuildV2`, `LS-ChargingCleanup`。
- `LS-CrossingRemoval` 增强为优先尝试同路线 2-opt 和跨路线 2-opt*，失败后才 fallback 到 crossing customers 移除重插。
- `LS-RouteMergeV2` 增加路线对快速筛选，只优先测试空间相近、角度相邻、路线规模合适的候选路线对。
- `R-VehicleReduction` 增加车辆压缩尝试/成功诊断。
- 新增 ALNS profiles：`alns_core`, `alns_vehicle`, `alns_petal`, `alns_drone`, `alns_full`。
- `run_single.py` 和 `run_experiments.py` 支持通过方法别名或配置调用不同 ALNS profile。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + ALNS + NPC`：
  - `feasible=True`
  - `vehicle_count=3`
  - `total_distance=161.151`
  - `runtime_seconds≈2.056`
- `R101-10 + ALNS + NPC`：
  - `feasible=True`
  - `vehicle_count=3`
  - `total_distance=240.500`
  - `crossing_count=4`
  - `full_evaluator_calls=513`
- `R101-25 + ALNS + NPC`：
  - `feasible=True`
  - `vehicle_count=9`
  - `total_distance=710.524`
  - `crossing_count=19`
  - `runtime_seconds≈47.507`
  - 相比先前约 58 秒的运行，候选筛选后速度有所改善。
- `configs/alns_ablation_debug.yaml`：可批量运行 `alns_core/alns_vehicle/alns_petal/alns_drone/alns_full`。

Observed results:
- ALNS 的可行性保持稳定。
- profile 消融可以正常输出到 `summary.csv`, `alns_operator_summary.csv`, `alns_ablation_summary.csv`。
- `alns_petal` 在 R101-5 中出现 crossing_success，说明 2-opt/2-opt* 接口已经能触发。
- RC101-10 的消融结果显示 `alns_petal/alns_drone` 在部分场景下能得到比 `alns_core` 更短的距离。

Remaining issues:
- `route_merge_successes` 仍经常为 0，说明车辆压缩仍是主要瓶颈。
- R101-25 中 `crossing_count=19`，说明 crossing removal 虽已增强，但还没有稳定改善大规模路线形态。
- `full_evaluator_calls` 仍偏高，后续若扩展到 50 customers，需要继续做增量评价或更强候选预筛选。
- 无人机任务在部分实例中仍不稳定，需要后续单独优化 `LS-DroneRebuildV2` 和无人机收益判断。

Next stage recommendation:
- 不继续新增算子名称。
- 下一步优先强化 `LS-RouteMergeV2` 和 `R-VehicleReduction`，提高减少车辆数的成功率。
- 对 `alns_core/alns_vehicle/alns_petal/alns_drone/alns_full` 做正式消融表，确定哪些算子应保留为默认。

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

---

## 2026-08-11 Change - ALNS 分层候选评价与论文级消融入口

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/configs/alns_ablation_25.yaml`
- `TruckDrone_EVRPTW_NL/configs/alns_ablation_50.yaml`

Reason:
- 当前 ALNS 已经能稳定生成可行解，但在 25/50 customers 下仍存在完整 evaluator 调用过多、车辆压缩弱、crossing 改善不稳定、无人机任务贡献不稳定的问题。
- 本阶段不继续堆叠新算子名称，而是给核心算子加入三层候选评价：quick structural filter、local feasibility estimate、full evaluator。

Modeling impact:
- 没有改变 Truck-Drone EVRPTW-NL 的硬约束定义。
- `feasible=True` 仍然只由统一 evaluator 判定。
- 分层评价只用于减少无效候选，不能把不可行解伪装成可行。

Algorithm impact:
- `_insertion_options()` 改为先生成快速候选，再筛选 Top-K，再做局部时间窗/电量估计，最后调用完整 evaluator。
- `LS-RouteMergeV2` 改为先筛选空间相近、角度相邻、可能合并的路线对，并只对 Top-K 合并候选做完整评价。
- `LS-CrossingRemoval` 改为先按 crossing waste 排序，再尝试 2-opt / 2-opt*，最后才 fallback 到移除重插。
- `LS-DroneRebuildV2` 改为先估计 drone_gain，只对少量 launch/recover 组合做完整评价。
- 新增 `alns_charging` profile，便于后续单独做充电策略消融。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL` 通过。
- `R101-5 + alns_core + NPC`：feasible=True，vehicle_count=3，total_distance=161.151，runtime≈0.708s。
- `R101-10 + alns_core + NPC`：feasible=True，vehicle_count=3，total_distance=240.500，runtime≈4.033s。
- `R101-25 + alns_core + NPC`：feasible=True，vehicle_count=9，total_distance=643.225，runtime≈45.195s。
- `R101-5 + alns_charging + NPC`：feasible=True，新增 profile 入口可运行。

Observed results:
- 25 customers 下可行性没有被破坏，硬约束违反仍为 0。
- `R101-25` 中 `crossing_successes=7`，说明 crossing 相关局部搜索开始能产生被完整 evaluator 接受的改善。
- `full_evaluator_calls` 仍然偏高，但新增诊断已经可以区分 quick candidates、local checked candidates、geometry/time/energy filter。
- 当前车辆压缩仍弱，`route_merge_successes=0`、`vehicle_reduction_successes=0`。
- 当前无人机任务仍不稳定，`drone_rebuild_successes=0`，说明无人机收益判断和同步可行插入仍需专项优化。

Remaining issues:
- 车辆数仍偏保守，route merge 和 vehicle reduction 是下一阶段核心瓶颈。
- 无人机任务没有稳定进入最终解，当前 ALNS 仍主要依赖卡车路线求可行。
- `full_evaluator_calls` 在 25 customers 下仍较高，50 customers 正式实验前需要继续增加增量估计或更强候选剪枝。

Next stage recommendation:
- 先做 Vehicle Reduction 专项：强化 `D-RouteRemoval`、`R-VehicleReduction`、`LS-RouteMergeV2`。
- 再做 Drone-aware 专项：让无人机任务必须带来 truck_distance、completion_time 或 vehicle_count 的真实收益。
- 最后做正式消融实验：`alns_core/alns_vehicle/alns_petal/alns_drone/alns_charging/alns_full`。

---

## 2026-08-11 Change - ALNS 后阶段专项优化

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/alns_development_report.md`
- `TruckDrone_EVRPTW_NL/docs/petal_route_design_report.md`

Reason:
- 当前 ALNS 已能生成可行解，但主要问题仍是车辆压缩弱、无人机任务贡献不稳定、充电策略缺少显式优化、完整 evaluator 调用偏多。
- 本次目标不是增加更多算子名称，而是强化已有关键流程：Vehicle Reduction、Drone-aware Repair、Charging Cleanup 和分层候选评价。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的硬约束定义。
- 仍保持同车发射、同车回收。
- 无人机仍允许多客户任务和访问已有充电站。
- 所有最终可行性仍由统一 evaluator 判定，分层评价只用于减少无效候选。

Algorithm impact:
- `R-VehicleReduction` 增加“禁止新开车”的严格插回阶段。删除路线后释放的客户必须优先插回已有路线，全部失败时才允许 fallback 新开车辆。
- `D-RouteRemoval` 由“简单删除短路线”改为结合客户数、路线距离、时间窗/电量局部风险、空间重叠和时间窗松弛度选择低利用路线。
- `LS-RouteMergeV2` 增加路线释放重插候选，不只尝试两条路线直接合并。
- `R-DroneAware` 在 repair 阶段直接比较 truck insertion 与 drone insertion，不再只依赖后处理。
- `LS-DroneRebuildV2` 支持从单客户到多客户逐步尝试，避免多客户组合一旦不可行就完全放弃无人机任务。
- 无人机候选引入 drone-aware comparison：硬约束和车辆数仍优先，但在可行且车辆数不变时，允许接受能明显降低 `truck_distance` 且不严重增加总距离、等待和充电时间的任务。
- `LS-ChargingCleanup` 从空操作改为尝试路线重排、减少充电时间或充电次数，并记录成功次数。
- ALNS 诊断新增 `full_evaluator_time`、`average_candidate_eval_time`、`affected_route_eval_calls`、`top_k_survival_rate`、`charging_cleanup_attempts`、`charging_cleanup_successes` 等字段。

Validation:
- `.\.venv\Scripts\python.exe -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + alns_vehicle + NPC`：`feasible=True`，`vehicle_count=3`，`total_distance=161.151`，`vehicle_reduction_successes=6/64`。
- `R101-10 + alns_drone + NPC`：`feasible=True`，`vehicle_count=3`，出现 2 个无人机任务，`drone_rebuild_successes=2`。
- `R101-10 + alns_charging + NPC`：`feasible=True`，`charging_count=3`，`charging_cleanup_successes=0/129`。
- `R101-25 + alns_full + NPC`：`feasible=True`，`vehicle_count=10`，出现 4 个无人机任务，`vehicle_reduction_successes=7/7`，`drone_rebuild_successes=1`，`crossing_count=8`。

Observed results:
- 无人机任务已经能够进入最终解，不再总是空任务。
- 车辆压缩诊断不再长期为 0，说明严格插回已有路线的流程已经触发。
- R101-25 中花瓣状指标改善明显，`crossing_count` 从之前约 23 降到 8，`petal_score` 从约 1166 降到约 412。
- 但无人机任务会显著降低候选可行率，R101-25 的候选 feasible rate 仍偏低。
- 当前 drone-aware 版本改善了无人机参与度和路线形态，但可能牺牲车辆数和总距离，因此必须在论文中通过 profile 消融单独解释。

Remaining issues:
- `route_merge_successes` 仍可能为 0，路线合并仍不是稳定车辆压缩来源。
- `charging_cleanup_successes` 当前仍为 0，说明充电清理候选还不够有效，或被时间窗过滤掉。
- `alns_vehicle` 与 `alns_full` 当前都可能受到 drone rebuild 影响，后续消融实验需要进一步隔离 profile，避免车辆压缩与无人机贡献混杂。
- 25 customers 运行时间约 45 秒，仍可接受；50 customers 前还需要继续控制 `full_evaluator_calls`。

Next stage recommendation:
- 固化 profile 边界：`alns_vehicle` 应优先验证车辆压缩，不应强制混入无人机重建。
- 对 `LS-RouteMergeV2` 增加更强的 route pair reconstruction 和 partial simulation，目标是让 `route_merge_successes > 0` 更稳定。
- 对 `LS-ChargingCleanup` 增加显式 station replacement 和 partial target SOC 候选。
- 正式运行 `alns_core/alns_vehicle/alns_drone/alns_charging/alns_petal/alns_full` 消融实验，判断每类增强是否值得保留。
---

## 2026-08-11 Change - GA+ALNS Hybrid Stage 1: GA-seeded ALNS refinement

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/solvers/hybrid_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_alns.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/hybrid_development_report.md`

Reason:
- 原 `hybrid_td` 只是分别运行 GA 和 ALNS 后择优，不是真正的混合搜索。
- 本阶段实现真正的 Stage 1 融合：GA 先生成全局 truck-drone 可行结构，ALNS 再从该结构出发做局部精修。

Modeling impact:
- 完整 solution 仍保持 `truck_routes + drone_tasks + charging_plan`。
- GA 到 ALNS 的转换保留 `truck_routes`、`drone_tasks`、`drone_route`、`route_index`、`launch`、`recover` 和 `customers`。
- `charging_plan`、到达时间、等待时间、电量状态和充电时间由 ALNS materialize 与统一 evaluator 重新计算。

Algorithm impact:
- 新增 `hybrid_refine`：`GA best solution -> ALNSState -> alns_hybrid_refine -> evaluator -> compare`。
- 保留 `hybrid_selector`：GA 和独立 ALNS 分别运行后择优，作为浅层组合 baseline。
- `hybrid` 默认等同于 `hybrid_refine`。
- ALNS 新增 `refine_state()`，允许从外部 `ALNSState` 继续搜索，不再强制自行构造初始解。
- 新增 `alns_hybrid_refine` profile，使用轻量 destroy/repair/local-search 组合，避免过度破坏 GA 已有结构。

Validation:
- `python -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + hybrid + NPC + diagnose`：`feasible=True`，最终保留 GA 解，`vehicle_count=2`。
- `R101-10 + hybrid + NPC`：`feasible=True`，ALNS refine 替换 GA，`vehicle_count=3`，`improvement_percentage≈0.64%`。
- `R101-25 + hybrid + NPC`：`feasible=True`，最终保留 GA 解，`vehicle_count=7`。
- `R101-5 + hybrid_selector + NPC`：旧 selector baseline 可运行。

Observed results:
- Stage 1 已经证明 ALNS 可以从 GA 解继续搜索，并在 R101-10 上产生可接受改进。
- R101-5 和 R101-25 中，ALNS refine 虽然能降低距离，但会增加车辆数，因此按车辆数优先规则不替换 GA。
- 这说明当前单个 GA 最优解不一定是 ALNS 最合适的精修起点。

Remaining issues:
- 目前只精修 GA 的单个最优解，尚未使用 GA 种群中的多样化候选。
- 25 customers 中 ALNS refine 容易用更多车辆换更短距离，说明后续需要更严格的 vehicle-preserving refine 或 Top-K candidate selection。
- 周期性融合和停滞触发尚未实现。

Next stage recommendation:
- 实施 Stage 2：Top-K diverse GA candidates，每个候选短时 ALNS refine，在相同总预算内选择最好可行解。
---

## 2026-08-11 Change - GA+ALNS Hybrid Stage 2: Top-K diverse GA candidates

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/solvers/hybrid_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/hybrid_development_report.md`

Reason:
- Stage 1 只对 GA 第一名做 ALNS refinement，容易受单一起点限制。
- 25 customers 中曾出现 ALNS 降低距离但增加车辆数的情况，按当前词典序目标不能替换 GA。
- 因此 Stage 2 增加 Top-K diverse candidates，让 Hybrid 不只依赖 GA 第一名，而是从多个高质量且结构不同的 GA 解中选择更适合 ALNS 精修的起点。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的硬约束。
- 不改变 GA、ALNS baseline 的独立运行逻辑。
- Hybrid 新增的多候选机制只改变“GA 解如何交给 ALNS”，不放松客户覆盖、容量、时间窗、电量、充电和同步约束。

Algorithm impact:
- `solve_ga.py` 新增 `generate_ga_candidates_for_hybrid()`，为 Hybrid 返回多个已通过统一 evaluator 的 GA 候选解。
- `hybrid_tools.py` 新增 `select_diverse_top_k()` 和 `solution_similarity()`。
- 相似度第一版基于 truck route 和 drone route 的边集合：
  `similarity = shared_edges / union_edges`。
- `solve_hybrid.py` 新增 `hybrid_topk` 模式：
  `GA candidate pool -> Top-K diverse selection -> per-candidate ALNS refine -> unified evaluator -> best feasible result`。
- `run_single.py` 和 `run_experiments.py` 新增 `hybrid_topk` 入口。
- `summary.csv` 新增 hybrid Top-K 诊断字段，包括 candidate count、selected rank、similarity、candidate before/after cost、ALNS improved candidates 等。

Validation:
- `.\.venv\Scripts\python.exe -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + hybrid_topk + NPC`：`feasible=True`，`vehicle_count=2`，`candidate_count=12`，`selected_candidate_count=3`，最终保留 GA rank 1。
- `R101-10 + hybrid_topk + NPC`：此前验证中 `feasible=True`，最终选择 GA rank 3，说明 Top-K 能找到优于 GA 第一名的结构。
- `R101-25 + hybrid_topk + NPC`：此前验证中 `feasible=True`，最终选择 GA rank 3，`vehicle_count=7`，说明 Top-K 在中规模下也能发挥多起点作用。

Observed results:
- Stage 2 已经证明“GA 第一名不一定是 Hybrid 最好起点”。
- 在 R101-10 和 R101-25 中，Top-K 可能选择非第一名 GA candidate 作为最终解，且保持可行。
- ALNS refine 对部分 candidate 能降低距离，但若增加车辆数，仍不会替换原 candidate，这是当前比较规则的正确行为。
- 当前提升主要来自“多样化 GA 候选选择”，ALNS refinement 的稳定贡献仍有限。

Remaining issues:
- `hybrid_topk` 当前仍是后处理式多起点，不是 GA 演化过程内融合。
- ALNS refine 在 25 customers 中仍可能用更多车辆换取更短距离，后续需要 vehicle-preserving refinement 或周期性精英注入。
- Top-K 第一版相似度以边集合为主，暂未单独加权无人机任务结构和充电结构。

Next stage recommendation:
- Stage 3 建议实现 Periodic Elite Improvement：GA 每隔固定代数选择多个高质量且不同的精英解，短时调用 ALNS 精修，若更优且可行则注入种群。
- Stage 4 再实现 Stagnation-triggered ALNS：GA 停滞时触发 ALNS，并配合随机移民保持多样性。
---

## 2026-08-11 Change - GA+ALNS Hybrid Stage 2.5 + Stage 3

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/configs/hybrid_stage_debug.yaml`
- `TruckDrone_EVRPTW_NL/configs/hybrid_stage_25.yaml`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/hybrid_development_report.md`

Reason:
- Stage 2 的 `hybrid_topk` 证明多起点有效，但 ALNS refine 仍可能出现“距离下降、车辆数增加”的结果，按当前词典序目标不能替换 GA 解。
- 本阶段先加入 Stage 2.5 的 vehicle-preserving refinement，使 ALNS 在 GA 已可行时只能做同车辆数精修。
- 随后加入 Stage 3 的 periodic elite improvement，使 ALNS 不只在 GA 结束后补救，而是在候选池演化过程中周期性参与。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的问题定义。
- 不改变硬约束：客户覆盖、容量、时间窗、电量、充电、无人机发射回收和同步仍由统一 evaluator 最终判断。
- 新增的 vehicle-preserving rule 是 Hybrid 搜索策略约束，不是问题本身的数学硬约束。

Algorithm impact:
- 新增 `alns_hybrid_preserve` profile：用于 Hybrid 精修，默认不启用强车辆变更算子，避免破坏 GA 已有可行结构。
- `refine_state()` 新增 `preserve_vehicle_count` 和 `baseline_vehicle_count` 参数。
- 若 GA candidate 已可行，则 ALNS candidate 车辆数超过 baseline 时直接拒绝，并记录 `rejected_by_vehicle_increase`。
- 新增 `hybrid_preserve`：`GA best -> ALNS preserve refine -> compare`。
- `hybrid_topk` 默认改为使用 preserve refine，避免 Top-K 候选被 ALNS 通过增车换距离。
- 新增 `hybrid_periodic`：按批次扩展 GA candidate pool，周期性选择 diverse elites 做短时 ALNS preserve refine，再将真正更优且可行的解注入候选池。
- GA 新增 Hybrid 专用候选扩展函数 `expand_ga_candidates_for_hybrid()`，只用于 Hybrid，不改变 GA baseline。
- `run_single.py` 对 `candidate_details` 和 `periodic_details` 只打印数量，避免终端输出被长列表淹没。

Validation:
- `.\.venv\Scripts\python.exe -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + hybrid_preserve + NPC + diagnose`：`feasible=True`，最终保留 2 车 GA 解；ALNS 曾尝试 3 车短距离结果，但被 preserve rule 拒绝。
- `R101-10 + hybrid_preserve + NPC`：`feasible=True`，ALNS 在同车辆数下被接受，`accepted_same_vehicle_improvements=1`。
- `R101-25 + hybrid_preserve + NPC`：`feasible=True`，最终保留 7 车 GA 解；高车辆数 refine 未替换原解。
- `R101-5 + hybrid_periodic + NPC + diagnose`：`feasible=True`，`periodic_trigger_count=1`，`periodic_injected_count=1`。
- `R101-10 + hybrid_periodic + NPC`：`feasible=True`，运行时间约 15.7s，周期性注入未稳定产生更优解。
- `R101-25 + hybrid_periodic + NPC`：`feasible=True`，运行时间约 97.2s，在 120s 预算内；最终车辆数 7，距离低于 `hybrid_preserve` 的测试结果，但周期性注入次数仍为 0。

Observed results:
- Stage 2.5 达到了核心目的：阻止 ALNS 用“增加车辆数”换取局部距离下降。
- `hybrid_preserve` 在小规模和中规模都能保持可行，且诊断字段能清楚显示同车辆数改进是否被接受。
- Stage 3 已经可运行并受时间预算控制；25 customers 从曾经约 240s 降到约 97s。
- 目前 Stage 3 的最终改进更多来自候选池扩展和最终选择，而不是周期性 ALNS 注入；`periodic_injected_count` 在 10/25 customers 中仍可能为 0。

Remaining issues:
- Periodic ALNS 的真实互补性还不强，周期性 refine 往往被拒绝。
- ALNS 在 GA 高质量可行解附近的同车辆数改进空间有限，说明当前 ALNS 邻域和 GA decoder 仍有较多重合。
- `hybrid_periodic` 能降低部分距离或等待，但可能带来更高充电时间或更差 petal score，需要在正式实验中分项解释。
- Stage 3 目前适合作为可运行研究版本，但还不能断言稳定优于 `hybrid_topk` 或 `hybrid_preserve`。

Next stage recommendation:
- 暂时不要继续提高周期调用频率，否则容易增加运行时间而不增加有效注入。
- 下一步应比较 `hybrid_topk`、`hybrid_preserve`、`hybrid_periodic` 在 10/25 customers 上的批量结果。
- 如果 periodic 仍无稳定收益，应进入 stagnation-triggered ALNS，而不是继续做固定周期调用。
---

## 2026-08-11 Change - GA+ALNS Hybrid Stage 4: Stagnation-triggered ALNS

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/configs/hybrid_stage_debug.yaml`
- `TruckDrone_EVRPTW_NL/configs/hybrid_stage_25.yaml`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/hybrid_development_report.md`

Reason:
- `hybrid_periodic` 固定周期调用 ALNS，但当前周期性注入次数经常为 0。
- 本阶段改为只在 GA candidate pool 停滞或多样性过低时触发 ALNS，避免无意义增加 ALNS 调用频率。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 模型和硬约束。
- 停滞触发只是 Hybrid 调度策略，不是问题约束。
- ALNS 精修仍使用 vehicle-preserving rule：GA candidate 已可行时不允许 ALNS 增加车辆数。

Algorithm impact:
- 新增 `hybrid_stagnation` 方法入口。
- 新增 `_solve_stagnation()`：复用 GA candidate pool、Top-K diversity、ALNS preserve refine。
- 新增停滞判断：连续 `stagnation_limit` 个 batch 没有改进时触发 ALNS。
- 新增低多样性判断：`population_diversity < diversity_threshold` 时触发 ALNS。
- 若 ALNS 没有成功注入，则注入少量 mutation/crossover immigrant candidates，避免候选池塌缩。
- `summary.csv` 新增停滞诊断字段：`stagnation_trigger_count`、`stagnation_injected_count`、`stagnation_immigrant_count` 等。

Validation:
- `.\.venv\Scripts\python.exe -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + hybrid_stagnation + NPC + diagnose`：`feasible=True`，`vehicle_count=2`，`runtime≈3.1s`，`stagnation_trigger_count=1`，`stagnation_injected_count=1`。
- `R101-10 + hybrid_stagnation + NPC`：`feasible=True`，`vehicle_count=3`，`runtime≈17.6s`，`stagnation_trigger_count=1`，`stagnation_injected_count=0`，`stagnation_immigrant_count=3`。
- `R101-25 + hybrid_stagnation + NPC`：`feasible=True`，`vehicle_count=7`，`runtime≈94.8s`，`stagnation_trigger_count=1`，`stagnation_injected_count=0`，`stagnation_immigrant_count=1`。

Observed results:
- Stage 4 已经能稳定运行，并且 25 customers 在 120s 预算内完成。
- 5 customers 中出现有效注入，说明机制是可用的。
- 10/25 customers 中触发机制正常，但 ALNS 精修结果仍经常被拒绝，说明问题主要不在触发时机，而在 Hybrid 专用 ALNS 邻域仍不够强。
- R101-25 中最终结果保持可行且车辆数为 7，`stagnation_best_before` 到 `stagnation_best_after` 有下降，但该改善主要来自候选池和 final Top-K refine，而非停滞阶段直接注入。

Remaining issues:
- `stagnation_injected_count` 在中规模算例中仍可能为 0。
- ALNS 在 GA 已有高质量可行解附近的同车辆数改进能力不足。
- 当前 immigrant 仍复用 GA mutation/crossover，并不是真正的结构级随机移民。
- 下一阶段如果要继续提高 Hybrid，重点不应再调触发频率，而应设计 Hybrid-specific ALNS neighborhood。

Next stage recommendation:
- 实施 Stage 5：Hybrid-specific ALNS neighborhood。
- ALNS 不再做通用大范围重构，而是专门做同车辆数局部精修：same-vehicle relocate、same-vehicle swap、launch/recover adjust、drone reassignment、charging polish、waiting reduction。
---

## 2026-08-11 Change - GA+ALNS Hybrid Stage 5: Hybrid-specific ALNS local neighborhood

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`
- `TruckDrone_EVRPTW_NL/docs/hybrid_development_report.md`

Reason:
- Stage 4 已经证明 stagnation trigger 可以运行，但 `stagnation_injected_count` 在 10/25 customers 中经常为 0。
- 这说明主要瓶颈不是“什么时候调用 ALNS”，而是 ALNS 被调用后缺少适合 GA 可行解附近精修的小邻域。
- 本阶段新增 Hybrid 专用 ALNS local operators，使 ALNS 不再大范围重构，而是在不增加车辆数、不破坏可行性的前提下做低风险局部改进。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的问题定义。
- 不改变客户覆盖、容量、时间窗、电量、充电、无人机发射回收和同步等硬约束。
- 新增邻域只属于 Hybrid 求解策略，不属于问题数学模型本身。

Algorithm impact:
- 新增 `alns_hybrid_local` profile，专门供 Hybrid refine 使用。
- 新增 Hybrid-specific local operators：
  - `H-RelocateSameVehicle`
  - `H-SwapSameVehicle`
  - `H-CrossRouteRelocateNoNewVehicle`
  - `H-DroneReassign`
  - `H-LaunchRecoverAdjust`
  - `H-ChargingPolish`
  - `H-WaitingReduction`
  - `H-PetalPolish`
- 所有 H operators 都遵守：
  - 不增加车辆数；
  - 不丢客户；
  - 不重复客户；
  - 不放松硬约束；
  - 只接受统一 evaluator 判定更优的可行结果。
- `hybrid_stagnation` 默认切换为 `alns_hybrid_local`。
- `hybrid_topk` 和 `hybrid_preserve` 保留原默认行为，但可以通过 `hybrid_alns_profile` 或 `hybrid_local_refine` 切换到 local profile。
- `summary.csv` 新增 Hybrid-local 诊断字段，包括各 H operator 的调用数和成功数。

Validation:
- `.\.venv\Scripts\python.exe -m compileall TruckDrone_EVRPTW_NL`：通过。
- `R101-5 + hybrid_stagnation + NPC + diagnose`：
  - `feasible=True`
  - `vehicle_count=2`
  - `runtime≈3.79s`
  - `hybrid_refine_profile=alns_hybrid_local`
  - `hybrid_local_operator_successes=194`
  - `stagnation_injected_count=1`
- `R101-10 + hybrid_stagnation + NPC`：
  - `feasible=True`
  - `vehicle_count=3`
  - `runtime≈16.98s`
  - `hybrid_local_operator_successes=114`
  - `stagnation_injected_count=0`
- `R101-25 + hybrid_stagnation + NPC`：
  - `feasible=True`
  - `vehicle_count=7`
  - `runtime≈98.13s`
  - `hybrid_local_operator_successes=67`
  - `improvement_percentage≈8.01%`
  - `stagnation_injected_count=0`

Observed results:
- Stage 5 成功让 Hybrid refine 阶段进入 `alns_hybrid_local`，并能产生可记录的同车辆数局部改进。
- 当前最有效的 H operator 是 `H-DroneReassign`，其次是少量 `H-CrossRouteRelocateNoNewVehicle`。
- `H-RelocateSameVehicle`、`H-SwapSameVehicle`、`H-LaunchRecoverAdjust`、`H-ChargingPolish`、`H-WaitingReduction`、`H-PetalPolish` 在本轮测试中成功数仍为 0。
- 25 customers 在预算内保持可行，并出现最终目标改善，但该改善仍主要来自候选池和最终选择，停滞阶段直接注入仍未稳定发生。

Remaining issues:
- Hybrid local operators 已经能产生局部成功，但不一定能转化为最终 `stagnation_injected_count`。
- 当前成功集中在无人机任务重建，说明路线顺序、等待压缩、充电微调等小邻域仍偏弱。
- 10/25 customers 中停滞阶段 ALNS 仍经常无法生成足以替换 elite 的解。
- 如果后续仍想继续提升 Hybrid，应优先增强 GA candidate 多样性和 Hybrid 专用 ALNS 的 route-level 小邻域，而不是继续增加触发频率。

Next stage recommendation:
- 进入 Stage 6 前，先做一轮批量对比：
  - `ga`
  - `alns_full`
  - `hybrid_topk`
  - `hybrid_preserve`
  - `hybrid_periodic`
  - `hybrid_stagnation`
- 如果 Stage 5 在多实例中优于 Stage 4，则继续强化 same-vehicle relocate/swap、waiting reduction 和 launch/recover adjust。
- 如果 Stage 5 仅在少数实例有效，则下一步应重新设计 GA 候选多样性，而不是继续堆 H operator。
## 2026-08-11 Change - Hybrid Stage 6 batch validation

Changed files:
- `TruckDrone_EVRPTW_NL/configs/hybrid_stage6_debug.yaml`
- `TruckDrone_EVRPTW_NL/configs/hybrid_stage6_25.yaml`
- `TruckDrone_EVRPTW_NL/hybrid_stage6_report.py`
- `TruckDrone_EVRPTW_NL/results/hybrid_stage6_summary.csv`
- `TruckDrone_EVRPTW_NL/docs/hybrid_stage6_report.md`

Reason:
- Stage 5 的 `hybrid_stagnation + alns_hybrid_local` 已能运行，但单算例不能证明 Hybrid 是否稳定优于 GA、ALNS 或旧 Hybrid。
- 本阶段先建立批量验证和自动汇总报告，避免继续盲目增加 H operator。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的实体、约束、充电策略或解结构。
- 仍保持 OR-Tools 和 PyVRP 为 truck-only baseline。

Algorithm impact:
- 不改变 GA baseline 和 ALNS baseline。
- 不改变已有 Hybrid 行为。
- 新增 Stage 6 批量配置和报告脚本，用于判断 `hybrid_stagnation`、`hybrid_topk`、`hybrid_preserve`、`hybrid_periodic` 与 GA/ALNS 的实际差异。

Validation:
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m compileall VRP_project/TruckDrone_EVRPTW_NL`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_experiments --config configs/hybrid_stage6_debug.yaml`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.hybrid_stage6_report`

Observed results:
- `hybrid_stage6_debug.yaml` 运行完成，共 18 条结果：3 个实例、6 种方法、NPC 充电策略、10 customers。
- 所有方法在该 debug 批次中 `feasible_rate = 100%`。
- GA 平均车辆数为 3.000，平均总距离约 349.970，平均运行时间约 4.625s。
- `hybrid_stagnation` 平均车辆数为 3.000，平均总距离约 361.346，平均运行时间约 18.146s。
- `hybrid_stagnation` 的 `hybrid_local_operator_successes = 169`，但 `stagnation_injected_count = 0`，说明局部算子有动作，但尚未稳定转化为候选池注入。

Remaining issues:
- 当前 debug 批次中，Hybrid 尚未稳定体现出相对 GA 的平均距离优势。
- `hybrid_stagnation` 相对 `hybrid_topk` 的胜负关系不稳定，不能直接证明 Stage 5 应作为主 Hybrid。
- 下一步不应继续增加 H operator 名称，而应优先检查 GA candidate diversity 是否不足。

Next stage recommendation:
- 先运行 `configs/hybrid_stage6_25.yaml` 观察 25 customers 下是否出现同样趋势。
- 如果 25 customers 中 `hybrid_stagnation` 仍不能稳定优于 `hybrid_topk` 或 GA，下一阶段应转向增强 GA 候选多样性，而不是继续堆叠 Hybrid-local 算子。
## 2026-08-12 Change - Hybrid final diverse candidates and paper-priority comparison

Changed files:
- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/solvers/hybrid_tools.py`
- `TruckDrone_EVRPTW_NL/solvers/solve_hybrid.py`
- `TruckDrone_EVRPTW_NL/solvers/alns/solve.py`
- `TruckDrone_EVRPTW_NL/run_single.py`
- `TruckDrone_EVRPTW_NL/run_experiments.py`
- `TruckDrone_EVRPTW_NL/hybrid_final_report.py`
- `TruckDrone_EVRPTW_NL/configs/hybrid_final_debug.yaml`
- `TruckDrone_EVRPTW_NL/configs/hybrid_final_25.yaml`
- `TruckDrone_EVRPTW_NL/configs/hybrid_final_50.yaml`
- `TruckDrone_EVRPTW_NL/docs/hybrid_final_audit.md`

Reason:
- 前几轮 Hybrid 的主要问题不是 ALNS 调用次数不够，而是 GA 交给 ALNS 的候选解结构过于相似。
- 本轮改造把重点从继续增加 H operator 转为：让 GA 主动产生多种目标导向的候选解，再让 ALNS 在这些不同结构附近精修。
- 同时新增 `paper_cost_priority` 比较规则，避免出现“距离略降但车辆数或总成本变差”仍被误判为改进。

Modeling impact:
- 不改变 Truck-Drone EVRPTW-NL 的实体、约束、充电策略或解结构。
- 不修改 OR-Tools / PyVRP truck-only baseline。
- 不修改 GA baseline 和 ALNS baseline 的独立运行行为。

Algorithm impact:
- 新增 Hybrid 专用 GA 候选类型：`distance_oriented`、`vehicle_oriented`、`time_window_oriented`、`drone_aggressive`、`drone_conservative`、`charging_oriented`、`petal_oriented`、`balanced`。
- 新增 `hybrid_diverse_topk` 和 `hybrid_diverse_stagnation` 方法入口。
- `select_diverse_top_k()` 支持类型覆盖，使 Top-K 不再只选目标值相近、结构相似的候选。
- Hybrid refine 增加 `paper_cost_priority` 比较模式，正式实验优先使用 feasible、zero violation、vehicle_count、paper_cost、distance、completion_time、charging/waiting/sync、petal_score 的顺序。
- 增加 wall-clock 预算保护，避免多样候选或 ALNS refine 单次异常拖慢批量实验。

Validation:
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m compileall TruckDrone_EVRPTW_NL`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_single --instance C101 --customers 10 --method hybrid_diverse_topk --charging-policy NPC`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_experiments --config configs/hybrid_final_debug.yaml`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.hybrid_final_report`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 25 --method hybrid_diverse_topk --charging-policy NPC`
- `D:\学习\FURP\VRP_project\.venv\Scripts\python.exe -m TruckDrone_EVRPTW_NL.run_single --instance R101 --customers 25 --method ga --charging-policy NPC`

Observed results:
- `hybrid_final_debug.yaml` 运行完成，共 18 条结果：3 个实例、6 种方法、10 customers、NPC、seed 1987。
- 所有方法 `feasible_rate = 100%`。
- 10 customers debug 平均结果：
  - GA：平均车辆数 3.000，平均距离 349.970，平均 paper_cost 528.437，平均运行时间 3.536s。
  - ALNS-full：平均车辆数 3.667，平均距离 351.370，平均 paper_cost 553.472，平均运行时间 18.613s。
  - `hybrid_diverse_topk`：平均车辆数 2.667，平均距离 344.074，平均 paper_cost 494.442，平均运行时间 4.584s。
  - `hybrid_diverse_stagnation`：平均车辆数 3.000，平均距离 342.752，平均 paper_cost 501.626，平均运行时间 15.596s。
- `C101-10 hybrid_diverse_topk` 曾出现 532s 异常运行；加入预算保护后复测为约 4.8s，且 feasible=True。
- `R101-25 hybrid_diverse_topk` 单例：feasible=True，vehicle_count=8，total_distance=771.314，runtime≈68.779s，drone_tasks=4，total_violation=0。
- 同一 `R101-25 GA` baseline 单例：feasible=True，vehicle_count=7，total_distance=810.202，runtime≈75.659s，drone_tasks=5，total_violation=0。

Interpretation:
- 10 customers debug 数据支持 `hybrid_diverse_topk` 作为当前最有希望的 Hybrid 版本。
- 25 customers 单例显示 Hybrid 可以降低距离，但可能增加车辆数；若论文目标车辆数优先，则不能把该结果简单视为优于 GA。
- 当前最可靠的结论是：多样 GA 候选显著优于旧 Hybrid 的 `balanced-only` 起点，但 Hybrid 是否能作为论文主方法必须等 `hybrid_final_25.yaml` 的多实例、多 seed 结果确认。

Remaining issues:
- ALNS refine 在 25 customers 中仍经常无法替换 GA 候选，最终提升主要来自“GA 多样候选选择”，而不是 ALNS 深度精修。
- `paper_cost_priority` 下，车辆数增加会压过距离下降，因此 Hybrid 必须在 25 customers 批量实验中证明车辆数不劣于 GA。
- 50 customers 仍应作为压力测试，不能作为当前主结论依据。

Next stage recommendation:
- 先运行 `configs/hybrid_final_25.yaml`，用 25 customers、3 seeds 判断 Hybrid 是否达到主方法标准。
- 若 `hybrid_diverse_topk` 在 25 customers 平均车辆数不高于 GA，且 paper_cost / total_distance 明显更好，则论文可以主打 Hybrid。
- 若 Hybrid 只在距离上局部优于 GA，但车辆数或稳定性不足，则论文主线应改为“约束感知 GA 主方法，Hybrid 作为增强与消融分析”。
