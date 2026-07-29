# Truck-Drone EVRPTW-NL 最小融合模型设计

> 生成目标：基于 Schneider E-VRPTW 与 ETRD-NL 两份精读报告，提出一个自洽、可逐步实现的最小 Truck-Drone EVRPTW-NL 模型。  
> 主要来源文档：  
> - `D:\学习\FURP\VRP_project\docs\evrptw_modeling_deep_reading.md`，对应 Schneider, Stenger, Goeke (2014) E-VRPTW。用户请求中的 `docs/schneider2014_modeling_deep_reading.md` 当前目录中未找到，因此本报告使用实际存在的 `evrptw_modeling_deep_reading.md`。  
> - `D:\学习\FURP\VRP_project\docs\etrd_nl_modeling_deep_reading.md`，对应 ETRD-NL paper。  
>
> 来源标签说明：  
> - **[Schneider E-VRPTW]**：来自 Schneider et al. (2014) E-VRPTW 模型思想。  
> - **[ETRD-NL paper]**：来自 Electric truck-based robot delivery problem with nonlinear charging。  
> - **[New assumption introduced in this study]**：为形成 Truck-Drone EVRPTW-NL 最小模型，本研究新增的假设。  
> - **[Future extension]**：当前最小模型暂不实现，但后续可扩展。

---

## 1. Modeling Goal

本模型研究的问题是：

```text
一辆电动卡车携带一架无人机，从单一仓库出发。
卡车和无人机协同服务一组带时间窗的客户。
卡车可访问充电站并按非线性充电函数补能。
无人机从卡车访问的节点起飞，服务客户后在卡车后续访问节点回收。
目标是在满足客户覆盖、容量、时间窗、电量、充电和同步约束的前提下，最小化综合成本。
```

这个模型不是直接复制两篇论文中的任何一个问题，而是融合：

- Schneider E-VRPTW 的 **电动卡车、时间窗、充电站、电池约束**；
- ETRD-NL 的 **卡车-辅助配送设备协同、释放/回收、同步、非线性充电策略**；
- 本研究新增的 **无人机飞行网络、无人机续航、起降服务时间、无人机客户可服务性**。

---

## 2. Source Conflict Analysis

两篇论文不能直接合并，因为核心假设存在冲突。

| 冲突点 | Schneider E-VRPTW | ETRD-NL paper | 推荐选择 | 理由 |
|---|---|---|---|---|
| 是否有时间窗 | 有客户时间窗 `[e_i, l_i]` | 明确不包含 time window constraints | 保留时间窗 | 本研究目标是 EVRPTW-NL，必须保留 TW |
| 辅助设备 | 无无人机/机器人 | 有车载机器人 | 引入无人机 | 研究目标是 truck-drone |
| 车辆数量 | 多辆同质电动车，优先车辆数 | 单辆电动卡车 + 单机器人 | 最小模型先用单卡车单无人机 | 降低建模难度，先保证协同逻辑正确 |
| 目标函数 | 车辆数优先，其次距离；代码中还有惩罚项 | 最小化完成时间 `w^T_{0'}` | 采用词典序 + 总成本双记录 | 便于公平比较和实验分析 |
| 充电模型 | 线性充电，满充 | 非线性充电，支持满充/部分充电 | 支持 LFC/LPC/NFC/NPC | 本研究重点是 NL |
| 充电主体 | 电动车访问充电站 | 卡车和机器人都可充电 | 最小模型仅卡车充电；无人机电池不在站点充电 | 无人机充电/换电机制复杂，先作为后续扩展 |
| 距离网络 | 卡车道路距离 | 卡车/机器人可有不同弧 | 卡车用道路/Manhattan，无人机用欧氏直线 | 无人机不能直接使用地面机器人道路假设 |
| 服务方式 | 客户只由车辆访问 | 客户可由卡车或机器人服务 | 客户可由卡车或无人机服务一次 | 融合协同服务 |
| 充电站重复访问 | Schneider 用 dummy station 支持重复访问 | ETRD-NL 对同一类型车辆访问同一站点有限制 | 最小模型允许物理站多次访问，但在解中用 visit id 区分 | 便于实现和避免状态混乱 |

**关键结论。** 最小融合模型必须优先保证逻辑自洽，而不是强行同时保留两篇论文的所有假设。最推荐的核心取舍是：

1. 保留 Schneider 的时间窗和 EV 充电站框架。
2. 保留 ETRD-NL 的释放、回收、同步和非线性充电策略。
3. 将机器人改成无人机时，重新定义无人机距离、速度、续航和任务可行性。
4. 第一阶段只让卡车在地面充电站充电，无人机只消耗电量并在卡车上恢复或更换电池。

---

## 3. Minimum Assumptions

| 假设 | 内容 | 来源 | 说明 |
|---|---|---|---|
| 单仓库 | 所有路线从 depot 0 出发并返回 depot 0 | [Schneider E-VRPTW] | Schneider 用 0 和 N+1 表示同一物理仓库，代码实现可先统一为 0 |
| 单卡车 | 最小模型先使用 1 辆电动卡车 | [New assumption introduced in this study] | ETRD-NL 是单卡车；Schneider 可多车。为研究 truck-drone 同步，先单车 |
| 单无人机 | 卡车携带 1 架无人机 | [New assumption introduced in this study] | 简化资源约束，避免多无人机并行调度 |
| 客户唯一服务 | 每个客户必须由卡车或无人机服务一次 | [Schneider E-VRPTW] + [ETRD-NL paper] | 两篇论文都要求客户不能遗漏或重复 |
| 不允许拆分配送 | 一个客户不能部分由卡车、部分由无人机服务 | [Schneider E-VRPTW] + [New assumption introduced in this study] | 最小模型保持离散客户服务 |
| 客户时间窗 | 每个客户有 ready time 和 due time | [Schneider E-VRPTW] | 与 ETRD-NL 冲突，推荐保留 |
| 早到等待 | 卡车或无人机早到客户可等待到 ready time | [Schneider E-VRPTW] | 等待进入时间传播和成本记录 |
| 不允许迟到 | 服务开始时间不能晚于 due time | [Schneider E-VRPTW] | 若迟到，解不可行 |
| 卡车容量 | 卡车有货物容量限制 | [Schneider E-VRPTW] | 无人机服务客户的需求也应占用卡车初始载货 |
| 无人机容量 | 无人机每次任务服务的客户总需求不能超过无人机容量 | [New assumption introduced in this study] | 机器人容量在 ETRD-NL 需核实，无人机必须显式建模 |
| 卡车电池 | 卡车有电池容量，能耗与地面距离线性相关 | [Schneider E-VRPTW] | 后续可扩展载重相关能耗 |
| 无人机电池 | 无人机有独立电池或续航上限 | [New assumption introduced in this study] | 来自无人机问题需求，不直接来自两篇论文 |
| 卡车充电站 | 卡车可访问固定充电站 | [Schneider E-VRPTW] | 充电站来自实例数据或生成规则 |
| 非线性充电 | 卡车充电时间由 SOC 决定，可线性或非线性 | [ETRD-NL paper] | 最小模型先只对卡车实现 NL |
| 部分充电 | 卡车可选择部分充电或满充 | [ETRD-NL paper] | 支持 LFC/LPC/NFC/NPC |
| 无人机起飞/回收 | 无人机只能在卡车访问的节点起飞和回收 | [ETRD-NL paper] + [New assumption introduced in this study] | 机器人释放/回收逻辑迁移到无人机 |
| 卡车可继续行驶 | 无人机执行任务时，卡车可继续前往回收节点 | [ETRD-NL paper] | 形成并行 segment |
| 同步 | 卡车和无人机必须在回收节点同时完成汇合后才能继续 | [ETRD-NL paper] | 早到方等待 |
| 无人机客户资格 | 只有满足需求、服务时间、飞行距离、禁飞条件的客户可由无人机服务 | [New assumption introduced in this study] | 避免把所有机器人客户假设直接套到无人机 |
| 禁飞区、天气、动态需求 | 暂不考虑 | [Future extension] | 后续再加入 |

---

## 4. Sets and Node Types

| 符号 | 含义 | 来源 |
|---|---|---|
| `0` | 仓库节点 | [Schneider E-VRPTW] |
| `C` | 客户集合 | [Schneider E-VRPTW] |
| `F` | 物理充电站集合 | [Schneider E-VRPTW] |
| `F'` | 充电站访问副本集合，用于允许同一物理站多次访问 | [Schneider E-VRPTW] |
| `N = {0} ∪ C ∪ F'` | 卡车可访问节点集合 | [Schneider E-VRPTW] |
| `D ⊆ C` | 无人机可服务客户集合 | [New assumption introduced in this study] |
| `L ⊆ N` | 无人机可起飞节点集合 | [ETRD-NL paper] + [New assumption introduced in this study] |
| `R ⊆ N` | 无人机可回收节点集合 | [ETRD-NL paper] + [New assumption introduced in this study] |
| `A^T` | 卡车地面有向弧集合 | [Schneider E-VRPTW] |
| `A^D` | 无人机飞行有向弧集合 | [New assumption introduced in this study] |
| `M` | 可行无人机任务集合 | [ETRD-NL paper] + [New assumption introduced in this study] |
| `P` | 充电策略集合 `{LFC, LPC, NFC, NPC}` | [ETRD-NL paper] |

### 推荐的最小无人机任务集合

最小模型建议先使用单客户无人机任务：

```text
m = (i, k, j)
```

其中：

- `i ∈ L`：起飞节点；
- `k ∈ D`：无人机服务客户；
- `j ∈ R`：回收节点；
- 卡车路线中必须先访问 `i`，后访问 `j`；
- 无人机飞行路径为 `i -> k -> j`。

来源判断：

- 释放/回收结构来自 **[ETRD-NL paper]**；
- 单客户 sortie 是 **[New assumption introduced in this study]**，因为 ETRD-NL 中机器人可以一次服务多个客户，但无人机因续航和载重更适合先从单客户任务开始；
- 多客户无人机任务作为 **[Future extension]**。

---

## 5. Parameters

| 符号 | 含义 | 来源 | 推荐取值/生成方式 |
|---|---|---|---|
| `d^T_{ij}` | 卡车从 i 到 j 的地面距离 | [Schneider E-VRPTW] | Solomon 坐标下可先用 Manhattan 或 Euclidean；若贴近 Schneider，使用原项目当前距离规则 |
| `t^T_{ij}` | 卡车从 i 到 j 的行驶时间 | [Schneider E-VRPTW] | `d^T_{ij} / v_T` |
| `e^T_{ij}` | 卡车从 i 到 j 的电量消耗 | [Schneider E-VRPTW] | `h_T * d^T_{ij}` |
| `d^D_{ij}` | 无人机从 i 到 j 的飞行距离 | [New assumption introduced in this study] | 欧氏直线距离 |
| `t^D_{ij}` | 无人机飞行时间 | [New assumption introduced in this study] | `d^D_{ij} / v_D` |
| `e^D_{ij}` | 无人机电量消耗 | [New assumption introduced in this study] | `h_D * d^D_{ij}`，后续可改为载重相关 |
| `q_i` | 客户 i 的需求量 | [Schneider E-VRPTW] | Solomon demand |
| `s_i` | 客户 i 的服务时间 | [Schneider E-VRPTW] | Solomon service_time |
| `a_i` | 客户 i 的最早服务时间 | [Schneider E-VRPTW] | Solomon ready_time |
| `b_i` | 客户 i 的最晚服务时间 | [Schneider E-VRPTW] | Solomon due_time |
| `Q_T` | 卡车载货容量 | [Schneider E-VRPTW] | Solomon vehicle capacity |
| `B_T` | 卡车电池容量 | [Schneider E-VRPTW] | 当前 EVRPTW 生成方式，后续校准 |
| `B_D` | 无人机电池容量 | [New assumption introduced in this study] | 按最大 sortie 距离设置 |
| `Q_D` | 无人机载货容量 | [New assumption introduced in this study] | 小于卡车容量，例如 1 个小包裹容量 |
| `v_T` | 卡车速度 | [Schneider E-VRPTW] + [New assumption introduced in this study] | 若数据无速度，设为 1 |
| `v_D` | 无人机速度 | [New assumption introduced in this study] | 通常大于卡车速度 |
| `tau_launch` | 无人机起飞准备时间 | [New assumption introduced in this study] | 初始可设为 0 或固定小值 |
| `tau_recover` | 无人机回收时间 | [New assumption introduced in this study] | 初始可设为 0 或固定小值 |
| `g_linear` | 线性充电速率 | [Schneider E-VRPTW] + [ETRD-NL paper] | 用当前 charging.py 的线性参数或按论文校准 |
| `F_T(E)` | 卡车累计非线性充电时间函数 | [ETRD-NL paper] | 分段线性函数 |
| `SOC_T` | 卡车电池荷电状态 | [ETRD-NL paper] | `energy / B_T` |
| `M_big` | Big-M 常数 | [Schneider E-VRPTW] + [ETRD-NL paper] | 用于 MILP；启发式中可不显式使用 |
| `lambda_v` | 使用卡车数/车辆固定成本权重 | [Schneider E-VRPTW] | 单卡车模型中可不使用 |
| `lambda_d` | 距离成本权重 | [Schneider E-VRPTW] | 用于统一 evaluator |
| `lambda_w` | 等待成本权重 | [New assumption introduced in this study] | 用于分析同步效率 |
| `lambda_c` | 充电时间成本权重 | [ETRD-NL paper] + [New assumption introduced in this study] | 用于总成本 |

---

## 6. Decision Variables

### 6.1 Route Variables

| 变量 | 含义 | 类型 | 来源 |
|---|---|---|---|
| `x_{ij}` | 卡车是否直接从节点 i 行驶到节点 j | binary | [Schneider E-VRPTW] |
| `u_i` | 卡车访问顺序或子回路消除辅助变量 | continuous/integer | [Schneider E-VRPTW] |
| `z_k^T` | 客户 k 是否由卡车服务 | binary | [ETRD-NL paper] + [New assumption introduced in this study] |
| `z_k^D` | 客户 k 是否由无人机服务 | binary | [New assumption introduced in this study] |
| `m_{ikj}` | 是否执行无人机任务 `(i,k,j)` | binary | [ETRD-NL paper] + [New assumption introduced in this study] |

### 6.2 Time Variables

| 变量 | 含义 | 类型 | 来源 |
|---|---|---|---|
| `T_i^arr` | 卡车到达节点 i 的时间 | continuous | [Schneider E-VRPTW] |
| `T_i^dep` | 卡车离开节点 i 的时间 | continuous | [Schneider E-VRPTW] |
| `D_{ikj}^launch` | 无人机任务 `(i,k,j)` 起飞时间 | continuous | [New assumption introduced in this study] |
| `D_{ikj}^cust` | 无人机到达客户 k 的时间 | continuous | [New assumption introduced in this study] |
| `D_{ikj}^recover` | 无人机到达回收节点 j 的时间 | continuous | [ETRD-NL paper] + [New assumption introduced in this study] |
| `W_j^T` | 卡车在回收节点 j 等待无人机的时间 | continuous | [ETRD-NL paper] |
| `W_j^D` | 无人机在回收节点 j 等待卡车的时间 | continuous | [ETRD-NL paper] |

### 6.3 Capacity and Battery Variables

| 变量 | 含义 | 类型 | 来源 |
|---|---|---|---|
| `L_i` | 卡车到达/离开节点 i 后的剩余载重或已服务需求状态 | continuous | [Schneider E-VRPTW] |
| `E_i^T` | 卡车到达节点 i 时电量 | continuous | [Schneider E-VRPTW] |
| `Y_i^T` | 卡车离开节点 i 时电量 | continuous | [Schneider E-VRPTW] |
| `E_{ikj}^D` | 无人机执行任务 `(i,k,j)` 的任务电量消耗 | continuous | [New assumption introduced in this study] |
| `r_i^T` | 卡车在充电站 i 的充电量 | continuous | [Schneider E-VRPTW] + [ETRD-NL paper] |
| `c_i^T` | 卡车在充电站 i 的充电时间 | continuous | [Schneider E-VRPTW] + [ETRD-NL paper] |
| `p_{i,l}` | 卡车充电状态落入第 l 个非线性充电分段 | binary | [ETRD-NL paper] |

### 6.4 为什么最小模型暂不设无人机充电变量

无人机是否能在地面充电站充电，与实际设备、充电接口、无人机能否自主降落到充电站有关。ETRD-NL 中机器人可访问地面充电站，但这不能直接替换为无人机。因此最小模型建议：

```text
无人机每次从卡车起飞时电量为满电或可用电池状态；
每个 sortie 必须满足总飞行电量 <= B_D；
无人机不访问地面充电站。
```

来源：**[New assumption introduced in this study]**。  
后续可扩展无人机换电或车载充电，标记为 **[Future extension]**。

---

## 7. Objective Function

为了兼容两篇论文，本研究建议同时记录两类目标：

### 7.1 主研究目标：词典序目标

```text
Priority 1: feasible = True
Priority 2: minimize vehicle_count
Priority 3: minimize completion_time
Priority 4: minimize total_distance
Priority 5: minimize waiting_time + charging_time
```

来源：

- 可行性优先：**[New assumption introduced in this study]**，来自当前实验中可行性不足的实际问题；
- 车辆数优先：**[Schneider E-VRPTW]**；
- 完成时间：**[ETRD-NL paper]**；
- 距离：**[Schneider E-VRPTW]**；
- 等待/充电时间：**[ETRD-NL paper]** + **[New assumption introduced in this study]**。

### 7.2 统一数值成本

用于 GA、ALNS、Hybrid 比较时，可定义：

```text
total_cost =
  alpha_infeasible * total_violation
+ alpha_vehicle * vehicle_count
+ alpha_time * completion_time
+ alpha_distance * total_distance
+ alpha_wait * waiting_time
+ alpha_charge * charging_time
```

推荐不要只看一个总成本，必须同时输出分项：

```text
feasible
vehicle_count
completion_time
total_distance
truck_distance
drone_distance
waiting_time
charging_time
charging_count
battery_violation
time_window_violation
capacity_violation
customer_coverage_violation
```

---

## 8. Core Constraints

### 8.1 Customer Coverage

```text
z_k^T + z_k^D = 1,    for all k in C
```

含义：每个客户必须且只能由卡车或无人机服务一次。

来源：**[Schneider E-VRPTW]** + **[ETRD-NL paper]**。

推荐实现：

- GA/ALNS 搜索阶段就保持客户唯一性；
- evaluator 最终检查 missing 和 duplicated；
- 不允许通过 repair 静默删除客户。

### 8.2 Truck Route Start and End

```text
Truck route starts at depot 0 and ends at depot 0'
```

来源：**[Schneider E-VRPTW]**。

最小代码表示可继续使用：

```python
truck_route = [0, ..., 0]
```

但报告和数学模型中应区分起点 `0` 与终点 `0'`。

### 8.3 Truck Flow Conservation

若卡车进入一个被访问节点，就必须离开该节点。

```text
sum_i x_{ij} = sum_h x_{jh}
```

来源：**[Schneider E-VRPTW]**。

启发式实现中体现为 truck_route 是一条连续序列。

### 8.4 Truck Customer Service

若客户 k 由卡车服务，则 k 必须出现在 truck_route 中。

```text
z_k^T = 1 => k in truck_route
```

来源：**[Schneider E-VRPTW]** + **[New assumption introduced in this study]**。

### 8.5 Drone Mission Validity

如果执行无人机任务 `(i,k,j)`，则：

```text
i and j must be visited by truck
i appears before j in truck_route
k not in truck_route as truck-served customer
k in D
```

来源：

- release/recovery：**[ETRD-NL paper]**；
- drone eligible set：**[New assumption introduced in this study]**。

### 8.6 Drone Single-Task Resource Constraint

最小模型中同一时间只能有一个无人机任务执行。

```text
No overlapping drone sorties
```

来源：**[New assumption introduced in this study]**。

原因：单卡车单无人机。若无人机未回收，不能再次起飞。

### 8.7 Time Window for Truck-Served Customers

若客户 k 由卡车服务：

```text
a_k <= service_start_k^T <= b_k
```

来源：**[Schneider E-VRPTW]**。

服务开始时间：

```text
service_start_k^T = max(T_k^arr, a_k)
```

### 8.8 Time Window for Drone-Served Customers

若客户 k 由无人机服务：

```text
a_k <= service_start_k^D <= b_k
```

来源：**[Schneider E-VRPTW]** + **[New assumption introduced in this study]**。

说明：Schneider 的时间窗本来用于车辆服务客户；本研究扩展为无人机服务也必须满足客户时间窗。

### 8.9 Truck Time Propagation

若卡车从 i 到 j：

```text
T_j^arr >= T_i^dep + t^T_{ij}
```

若 i 是客户且由卡车服务：

```text
T_i^dep >= max(T_i^arr, a_i) + s_i
```

若 i 是充电站：

```text
T_i^dep >= T_i^arr + c_i^T
```

来源：**[Schneider E-VRPTW]** + **[ETRD-NL paper]**。

### 8.10 Drone Time Propagation

对无人机任务 `(i,k,j)`：

```text
D_{ikj}^launch = T_i^dep + tau_launch
D_{ikj}^cust >= D_{ikj}^launch + t^D_{ik}
service_start_k^D = max(D_{ikj}^cust, a_k)
D_{ikj}^recover >= service_start_k^D + s_k + t^D_{kj}
```

来源：

- release/recovery/sync：**[ETRD-NL paper]**；
- drone flight time and launch/recovery time：**[New assumption introduced in this study]**。

### 8.11 Synchronization at Recovery Node

若执行任务 `(i,k,j)`：

```text
joint_departure_j >= T_j^arr
joint_departure_j >= D_{ikj}^recover + tau_recover

W_j^T = max(0, D_{ikj}^recover + tau_recover - T_j^arr)
W_j^D = max(0, T_j^arr - (D_{ikj}^recover + tau_recover))
```

来源：**[ETRD-NL paper]**。

含义：卡车和无人机谁先到都要等，二者同步后卡车才能带着无人机继续。

### 8.12 Truck Capacity

卡车出发时携带所有需要由本卡车系统服务的货物，包括卡车客户和无人机客户。沿途服务客户后载重减少。

```text
load_after <= Q_T
load never negative
```

来源：**[Schneider E-VRPTW]** + **[New assumption introduced in this study]**。

说明：如果无人机从卡车取货配送，则无人机客户的需求也来自卡车载货。

### 8.13 Drone Capacity

对无人机任务 `(i,k,j)`：

```text
q_k <= Q_D
```

来源：**[New assumption introduced in this study]**。

若后续允许多客户无人机任务：

```text
sum_{k in sortie} q_k <= Q_D
```

来源：**[Future extension]**。

### 8.14 Truck Battery Propagation

若卡车从 i 到 j：

```text
E_j^T <= Y_i^T - e^T_{ij}
0 <= E_j^T <= B_T
0 <= Y_i^T <= B_T
```

若 i 为非充电节点：

```text
Y_i^T = E_i^T
```

若 i 为充电站：

```text
Y_i^T = E_i^T + r_i^T
Y_i^T <= B_T
```

来源：**[Schneider E-VRPTW]**。

### 8.15 Nonlinear Truck Charging

如果采用非线性充电：

```text
c_i^T = F_T(Y_i^T) - F_T(E_i^T)
```

其中 `F_T(E)` 是从 0 充到电量 E 的累计时间函数，通常分段线性、递增、凸。

来源：**[ETRD-NL paper]**。

如果采用线性充电：

```text
c_i^T = (Y_i^T - E_i^T) / g_linear
```

来源：**[Schneider E-VRPTW]** + **[ETRD-NL paper]**。

### 8.16 Charging Strategy Constraints

四种策略：

| 策略 | 约束 |
|---|---|
| LFC | 线性充电，若充电则 `Y_i^T = B_T` |
| LPC | 线性充电，`E_i^T <= Y_i^T <= B_T` |
| NFC | 非线性充电，若充电则 `Y_i^T = B_T` |
| NPC | 非线性充电，`E_i^T <= Y_i^T <= B_T` |

来源：**[ETRD-NL paper]**。

### 8.17 Drone Battery Constraint

最小模型中，无人机每次 sortie 必须满足：

```text
e^D_{ik} + e^D_{kj} <= B_D
```

来源：**[New assumption introduced in this study]**。

后续如果建无人机连续电池状态或车载充电：

```text
drone_energy_after_recovery = drone_energy_before_launch - sortie_energy
```

来源：**[Future extension]**。

### 8.18 Charging Station Access

卡车可以访问充电站，充电站可插入 truck_route。

来源：**[Schneider E-VRPTW]**。

推荐最小实现：

```text
charging station is a normal truck node
truck can visit it between customers
no customer service at station
time window of station follows depot horizon
```

### 8.19 No Drone Charging at Ground Stations in Minimum Model

```text
Drone cannot independently visit charging stations.
```

来源：**[New assumption introduced in this study]**。

原因：ETRD-NL 的机器人可以去地面充电站，但无人机能否使用同一充电站不是论文事实，不能直接迁移。

### 8.20 Feasibility Definition

一个解 feasible=True 当且仅当：

```text
customer_coverage_violation = 0
truck_route_start_end_valid = True
truck_capacity_violation = 0
drone_capacity_violation = 0
truck_time_window_violation = 0
drone_time_window_violation = 0
truck_battery_violation = 0
drone_battery_violation = 0
sync_violation = 0
charging_policy_violation = 0
```

来源：三方融合，主要为 **[New assumption introduced in this study]** 的统一 evaluator 定义。

---

## 9. Complete Solution Structure

建议统一解格式：

```python
solution = {
    "truck_route": [0, 12, 1001, 8, 21, 0],
    "drone_tasks": [
        {
            "launch": 12,
            "customer": 5,
            "recover": 8,
            "drone_route": [12, 5, 8],
        }
    ],
    "charging_plan": [
        {
            "vehicle": "truck",
            "node": 1001,
            "arrival_energy": 22.5,
            "departure_energy": 80.0,
            "charging_time": 18.2,
            "policy": "NPC",
        }
    ],
    "timing": {
        "truck_arrivals": {},
        "truck_departures": {},
        "drone_arrivals": {},
        "sync_records": [],
    },
    "battery": {
        "truck_arrival_energy": {},
        "truck_departure_energy": {},
        "drone_sortie_energy": {},
    }
}
```

关键原则：

1. `truck_route` 是主路线。
2. `drone_tasks` 是挂在 truck_route 两个节点之间的并行任务。
3. `charging_plan` 必须是解的一部分，而不是 evaluator 自动隐藏生成。
4. `timing` 和 `battery` 可由 simulator 重新计算，但最好保存用于诊断和画图。

---

## 10. Route Simulation Logic

最小 route simulator 应按以下顺序传播：

```text
1. 初始化：
   time = 0
   truck_battery = B_T
   truck_load = sum(customer demand)

2. 遍历 truck_route 的每一段 (i, j)：
   2.1 检查是否有 drone task 从 i 起飞并在 j 回收
   2.2 卡车从 i 出发，可能服务 i，可能充电
   2.3 若有 drone task：
       drone_launch_time = truck_depart_i + tau_launch
       drone flies i -> k -> j
       drone customer k must satisfy time window
       drone energy must be enough
   2.4 卡车行驶 i -> j
   2.5 到达 j 后与无人机同步
   2.6 更新 waiting_time
   2.7 更新 truck time, battery, load

3. 返回 depot：
   检查最终电量和时间 horizon

4. 汇总：
   feasible
   completion_time
   total_distance
   charging_time
   waiting_time
   violations
```

这个 simulator 是 GA、ALNS、Hybrid、OR-Tools/PyVRP 后处理必须共享的核心模块。

---

## 11. Recommended Minimal Mathematical Model

### 11.1 Sets

```text
C: customers
F: charging stations
N: truck nodes = {0} ∪ C ∪ F'
D: drone-eligible customers, D ⊆ C
M: feasible drone missions (i,k,j)
P: charging policies {LFC,LPC,NFC,NPC}
```

### 11.2 Variables

```text
x_ij ∈ {0,1}: truck travels from i to j
z_k^T ∈ {0,1}: customer k served by truck
z_k^D ∈ {0,1}: customer k served by drone
m_ikj ∈ {0,1}: drone mission (i,k,j) is used
T_i^arr, T_i^dep ≥ 0: truck arrival/departure time
E_i^T, Y_i^T ∈ [0,B_T]: truck arrival/departure energy
r_i^T ≥ 0: truck charged energy at station i
c_i^T ≥ 0: truck charging time at station i
W_j^T, W_j^D ≥ 0: synchronization waiting times
```

### 11.3 Objective

推荐写为词典序：

```text
min lexicographic(
    total_violation,
    vehicle_count,
    completion_time,
    total_distance,
    waiting_time + charging_time
)
```

若必须给 GA/ALNS 一个标量：

```text
min total_cost =
  alpha_0 * total_violation
+ alpha_1 * vehicle_count
+ alpha_2 * completion_time
+ alpha_3 * total_distance
+ alpha_4 * waiting_time
+ alpha_5 * charging_time
```

### 11.4 Core Constraints

```text
z_k^T + z_k^D = 1                         for all k in C
z_k^D <= 1[k in D]                         for all k in C
sum_{(i,k,j) in M} m_ikj = z_k^D           for all k in C
z_k^T = 1 => k appears in truck route
m_ikj = 1 => i and j appear in truck route and i precedes j
a_k <= service_start_k^T <= b_k            if z_k^T = 1
a_k <= service_start_k^D <= b_k            if z_k^D = 1
truck load never exceeds Q_T
q_k <= Q_D                                 if z_k^D = 1
truck battery never below 0
truck battery never above B_T
drone sortie energy <= B_D
truck and drone synchronize at recovery node
charging time follows selected policy
```

---

## 12. Why This Is the Minimum Self-Consistent Model

这个模型称为“最小”，因为它有意识地暂时排除了以下复杂机制：

| 暂不实现内容 | 原因 | 来源 |
|---|---|---|
| 多卡车 | 会引入车辆分配和多路线同步 | [Future extension] |
| 多无人机 | 会引入无人机资源冲突和并行任务 | [Future extension] |
| 无人机地面充电 | 无法直接从机器人充电假设迁移 | [Future extension] |
| 无人机多客户任务 | 对续航、载重、时间窗更复杂 | [Future extension] |
| 天气/禁飞区 | 数据缺失 | [Future extension] |
| 载重相关能耗 | 两篇源模型当前复现均以固定能耗率为主 | [Future extension] |
| 动态客户 | 两篇论文均为静态规划问题 | [Future extension] |

但它保留了研究主题必须有的内容：

1. EVRPTW：时间窗、电量、充电站；
2. NL：非线性充电；
3. Truck-Drone：释放、服务、回收、同步；
4. 可比较：统一 evaluator 输出分项指标。

---

## 13. Algorithm Implications

### 13.1 GA

GA 的染色体不能只是一串客户排列。最小可用编码：

```text
customer_order: [k1, k2, ...]
service_mode:  [T, D, T, ...]
launch_recover_policy: rule-based or encoded
charging_policy: LFC/LPC/NFC/NPC
```

推荐先采用半显式编码：

1. GA 负责客户顺序和服务方式；
2. decoder 根据 truck_route 相邻节点生成可行 drone task；
3. charging_plan 由充电感知插入器生成；
4. evaluator 严格判定，不隐藏不可行。

新增关键算子：

- truck-to-drone service mode mutation；
- drone-to-truck repair；
- launch/recover relocation；
- charging station insertion/removal；
- target SOC mutation。

### 13.2 ALNS

ALNS 更适合这个问题，因为它的 destroy/repair 可以直接操作结构：

| 算子 | 操作对象 | 目标 |
|---|---|---|
| Truck customer removal | truck-served customer | 重排卡车主路线 |
| Drone customer removal | drone-served customer | 重分配无人机任务 |
| Mission removal | 整个 `(launch, customer, recover)` | 改变同步结构 |
| Charging station removal | truck charging visit | 减少绕行和充电 |
| Regret insertion | 未服务客户 | 避免困难客户拖到最后 |
| Mission insertion | 无人机任务 | 寻找节省时间的 sortie |
| Energy-aware insertion | 客户/站点 | 保证电量可行 |
| Sync-aware insertion | launch/recover | 减少等待时间 |

### 13.3 Hybrid

推荐分工：

```text
GA:
  global customer order
  truck/drone service mode
  coarse route structure

ALNS:
  mission structure
  launch/recover optimization
  charging station placement
  target SOC and nonlinear charging refinement
  local route improvement

Shared:
  route simulator
  feasibility checker
  evaluator
  result schema
```

避免的问题：

```text
不要让 GA 和 ALNS 都只是生成路线，然后交给同一个 full repair。
否则二者行为重复，Hybrid 很难体现创新。
```

---

## 14. Recommended Implementation Order

| 阶段 | 目标 | 修改对象 | 完成标准 |
|---|---|---|---|
| Stage 1 | 建立 truck-only EVRPTW-NL simulator | evaluator / charging | LFC/LPC/NFC/NPC 对同一路线输出不同充电时间 |
| Stage 2 | 加入无人机单客户 sortie | solution schema / evaluator | 能手算验证 `(i,k,j)` 同步 |
| Stage 3 | 加入无人机时间窗 | evaluator | drone-served customer 满足 ready/due |
| Stage 4 | 加入无人机续航和容量 | evaluator | 超续航/超载判 infeasible |
| Stage 5 | 让 GA decoder 生成 truck/drone 服务方式 | GA module | 不靠强 repair 也能产生合法覆盖 |
| Stage 6 | 让 ALNS 操作 mission 和 charging_plan | ALNS module | destroy/repair 能改变无人机任务和充电站 |
| Stage 7 | 统一实验四策略 | run_experiments | 同一实例比较 LFC/LPC/NFC/NPC |
| Stage 8 | 对比 GA/ALNS/Hybrid | results/report | 多 seed 输出均值、标准差、可行率 |

---

## 15. Data Strategy

为了延续当前项目资源，建议仍使用 Solomon 数据，但要明确这不是原始论文 benchmark。

| 数据项 | 推荐做法 | 来源 |
|---|---|---|
| 客户坐标 | Solomon R/C/RC | [Schneider E-VRPTW] |
| 客户需求 | Solomon demand | [Schneider E-VRPTW] |
| 客户时间窗 | Solomon ready/due | [Schneider E-VRPTW] |
| 服务时间 | Solomon service_time | [Schneider E-VRPTW] |
| 充电站 | 沿用当前 EVRPTW_Schneider2014 生成方式 | [Schneider E-VRPTW] + 当前项目实现 |
| 卡车电池 | 当前 Schneider 模块估计方法 | [Schneider E-VRPTW] |
| 非线性充电曲线 | 使用 ETRD_NL 当前分段曲线，后续替换为论文 Fig. 7 | [ETRD-NL paper] + 当前项目实现 |
| 无人机可服务客户 | 按需求、距离、时间窗筛选 | [New assumption introduced in this study] |
| 无人机速度/续航 | 配置文件设定 | [New assumption introduced in this study] |

---

## 16. Evaluation Metrics

统一输出至少应包含：

| 指标 | 含义 |
|---|---|
| `feasible` | 是否所有硬约束均为 0 违反 |
| `vehicle_count` | 最小模型中为 1；多车扩展后记录实际车辆数 |
| `completion_time` | 卡车最终返回仓库时间 |
| `total_cost` | 加权总成本 |
| `truck_distance` | 卡车行驶距离 |
| `drone_distance` | 无人机飞行距离 |
| `total_distance` | 二者距离总和或按成本折算 |
| `charging_count` | 卡车充电次数 |
| `charging_time` | 卡车总充电时间 |
| `waiting_time` | 卡车/无人机同步等待总时间 |
| `truck_battery_violation` | 卡车电量违反 |
| `drone_battery_violation` | 无人机续航违反 |
| `time_window_violation` | 时间窗违反 |
| `capacity_violation` | 卡车/无人机容量违反 |
| `customer_coverage_violation` | 客户遗漏或重复 |
| `drone_task_count` | 无人机任务数量 |
| `charging_policy` | LFC/LPC/NFC/NPC |

---

## 17. Recommended Choice for Conflicting Assumptions

| 建模问题 | 推荐选择 | 不选另一方的原因 |
|---|---|---|
| 是否保留时间窗 | 保留 Schneider 时间窗 | EVRPTW 的 TW 是研究目标之一 |
| 目标函数 | 同时记录词典序和加权成本 | Schneider 与 ETRD-NL 目标不同，单一目标会丢信息 |
| 车辆数量 | 先单卡车，后续多车 | 先解决无人机协同和非线性充电 |
| 无人机是否能多客户 | 第一版单客户 sortie | 无人机不同于地面机器人，不能直接继承多客户机器人假设 |
| 无人机是否能去充电站 | 第一版不能 | 机器人地面充电不能直接迁移到无人机 |
| 卡车充电方式 | 支持四策略 | ETRD-NL 的核心贡献 |
| 距离方式 | 卡车地面距离，无人机欧氏距离 | 反映 truck-drone 物理差异 |
| 充电站重复访问 | 用 station visit copy 表示 | 兼容 Schneider dummy station 思路 |

---

## 18. Minimum Model Summary

最终推荐的最小 Truck-Drone EVRPTW-NL 模型为：

```text
Single depot
Single electric truck
Single onboard drone
Customers with demand, service time and time windows
Truck can serve customers and visit charging stations
Drone can serve eligible customers through single-customer sorties
Drone sortie = launch node -> customer -> recovery node
Launch and recovery nodes must be on truck route
Truck and drone synchronize at recovery node
Truck has capacity and nonlinear charging battery constraints
Drone has capacity and endurance constraints
Charging policies include LFC, LPC, NFC and NPC for truck
Objective records feasibility, vehicle count, completion time, distance, waiting and charging
```

这个模型足够小，可以逐步写入当前项目；同时又足够完整，能体现“Truck-Drone + EVRPTW + Nonlinear Charging”的核心研究价值。

---

## 19. What Must Not Be Claimed

后续写报告或论文时，应避免以下说法：

1. 不能说当前模型完全复现 Schneider E-VRPTW，因为它加入了无人机和非线性充电。
2. 不能说当前模型完全复现 ETRD-NL，因为它加入了时间窗，并把机器人换成无人机。
3. 不能说机器人假设可以直接替换为无人机假设。
4. 不能说 Solomon 数据就是 ETRD-NL 原始数据。
5. 不能只报告 total_cost，而不报告 feasibility 和分项违反。
6. 不能把 repair 后的可行解说成算法原生满足全部约束，除非搜索阶段确实使用了这些约束。

---

## 20. Final Checklist Before Coding

开始实现前必须先回答：

1. 无人机客户集合 `D` 如何筛选？
2. 无人机 sortie 是否只服务一个客户？
3. 无人机起飞和回收时间是否设为 0？
4. 无人机电池每次起飞是否满电？
5. 无人机能否在卡车充电期间飞行？
6. 卡车在等待无人机时能否同时充电？
7. 卡车充电站是否可作为无人机起飞/回收点？
8. 充电策略是全局统一，还是每次充电可单独选择？
9. NPC 中目标 SOC 如何决定？
10. evaluator 是否保存 charging_plan，而不是隐藏插站？
11. GA 染色体是否显式编码服务方式？
12. ALNS state 是否显式保存 drone_tasks？
13. Hybrid 中 GA 和 ALNS 的职责是否互补？
14. 输出路线图如何同时显示卡车路线、无人机 sortie 和充电站？
15. 批量实验如何保证四种策略使用同一实例和随机种子？

---

## 21. Implementation Recommendation

最小工程实现建议新建独立模块，而不是直接改 `ETRD_NL` 或 `EVRPTW_Schneider2014`：

```text
TruckDrone_EVRPTW_NL/
  README.md
  config.py
  data_loader.py
  instance_builder.py
  charging.py
  solution_schema.py
  route_simulator.py
  evaluator.py
  drone_mission.py
  solvers/
    solve_ga.py
    solve_alns.py
    solve_hybrid.py
  run_single.py
  run_experiments.py
  results/
  figures/
```

理由：

- Schneider 模块是 truck-only EVRPTW；
- ETRD_NL 模块是 truck-robot NL；
- 新问题是 truck-drone EVRPTW-NL，实体和约束都不同；
- 独立模块可以避免把旧复现代码改乱。

---

## 22. Source Attribution Table

| 模型组成 | Schneider E-VRPTW | ETRD-NL paper | New assumption introduced in this study | Future extension |
|---|---|---|---|---|
| 单仓库 | yes | yes | - | 多仓库 |
| 客户时间窗 | yes | no | 保留 Schneider TW | 软时间窗 |
| 电动卡车 | yes | yes | - | 异构电动车 |
| 充电站 | yes | yes | - | 容量受限充电站 |
| 线性充电 | yes | yes, as LFC/LPC baseline | - | - |
| 非线性充电 | no | yes | 引入 EVRPTW | 更真实电池模型 |
| 部分充电 | no | yes | 引入 EVRPTW | 动态 SOC 策略 |
| 机器人/无人机协同 | no | robot yes | drone substitution | 多无人机 |
| 起飞/回收 | no | release/recovery | drone launch/recovery | 动态回收 |
| 同步等待 | no | yes | drone sync | 异步回收 |
| 无人机直线距离 | no | no | yes | 风场/禁飞区 |
| 无人机续航 | no | robot battery idea | yes | 载重相关能耗 |
| 无人机充电 | no | robot charging yes | no in minimum model | drone charging/swapping |

