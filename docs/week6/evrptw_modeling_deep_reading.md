# E-VRPTW Modeling Deep Reading: Paper-to-Code Report

本文档针对 Schneider, Stenger, and Goeke (2014) 的 E-VRPTW 论文进行精读，并与当前项目 `EVRPTW_Schneider2014/` 的代码实现逐项对应。

重要声明：

- **论文事实**：来自 PDF 页面、章节、公式、表格或算法描述。
- **代码事实**：来自当前项目文件和函数。
- **推断/建议**：基于论文和代码差异提出，不代表论文原文。
- PDF 中部分公式文字提取有噪声，因此关键公式以页面截图人工核对为准。若仍无法完全确认，会标注“需要进一步核实”。

---

# 1. Paper Identification

| 项目 | 内容 |
|---|---|
| 论文完整标题 | *The Electric Vehicle-Routing Problem with Time Windows and Recharging Stations* |
| 作者 | Michael Schneider, Andreas Stenger, Dominik Goeke |
| 年份 | 2014 |
| 期刊 | *Transportation Science*, Vol. 48, No. 4, pp. 500-520 |
| DOI | 10.1287/trsc.2013.0490 |
| 研究问题名称 | Electric Vehicle-Routing Problem with Time Windows and Recharging Stations |
| 论文简称 | E-VRPTW |
| 数据集来源 | 基于 Solomon (1987) VRPTW benchmark 构造新的 E-VRPTW benchmark；另与 MDVRPI、G-VRP、VRPTW benchmark 比较 |
| 主要贡献 | 提出带时间窗、容量、充电站和电池约束的 E-VRPTW；给出 MILP；构造 benchmark；提出 VNS/TS 混合启发式 |
| 求解方法 | 小规模用 CPLEX 求解 MILP；大规模用 hybrid VNS/TS heuristic |

## 论文到底解决什么问题

**论文事实。** 第 1 节和第 3 节说明，论文研究的是使用电动商用车进行配送时的路径规划问题。车辆从仓库出发，服务有需求和时间窗的客户，并可在固定充电站补电。由于电池容量有限，路线必须同时满足载重、时间窗、电量和充电可达性。论文把这个问题命名为 E-VRPTW。

**问题创新。** 相比传统 VRPTW，论文额外引入了电池容量、能耗、充电站访问和充电时间。充电时间不是固定值，而取决于车辆到达充电站时的剩余电量。论文第 3 节明确采用线性充电假设。

**算法创新。** 论文第 4 节提出 VNS/TS 混合启发式：VNS 负责扰动和扩大搜索邻域，TS 负责局部改进，搜索过程中允许不可行解，并用广义惩罚成本函数评价容量、时间窗和电池违反。

**实验贡献。** 论文第 5.2.1 节构造两套 E-VRPTW benchmark：56 个大规模 100-customer 实例，以及 36 个小规模 5/10/15-customer 实例。表 5 比较 CPLEX 和 VNS/TS，小规模结果显示 VNS/TS 可达到或接近最优；表 6 分析 VNS、TS、SA 接受准则的组件效果。

---

# 2. Problem Scope and Assumptions

| 假设 | 论文原文含义 | 原文位置 | 当前项目实现 | 是否一致 |
|---|---|---|---|---|
| 仓库数量 | 一个仓库；用 0 和 N+1 表示同一仓库的出发和返回实例 | p.504, Section 3 | `depot["id"] = 0`，路线默认从 0 出发并返回 0 | 部分一致：代码没有显式使用 N+1 返回仓库副本 |
| 车辆类型 | 同质车辆 | p.504, Section 3 | 所有方法使用同一 `vehicle_capacity`、`battery_capacity` | 一致 |
| 车辆数量 | 论文目标层级中首先最小化车辆数；算法中可增加车辆 | p.504, p.506 Figure 1 | 当前 `priority_objective()` 强烈惩罚车辆数；repair 允许新增车辆 | 部分一致 |
| 客户服务 | 每个客户必须被服务一次 | p.504 formula (2) | `evaluate_solution()` 用 `customer_coverage` 检查遗漏和重复 | 一致，但主要在 evaluator 检查 |
| 拆分配送 | 论文模型中客户被一次访问，不支持拆分配送 | p.504 formula (2) | route 中每个客户最多/必须一次；不拆分 demand | 一致 |
| 客户需求 | 客户有正需求，非客户需求为 0 | p.504, Table 1 | Solomon `demand` 读入客户，depot/station demand 为 0 | 一致 |
| 时间窗 | 节点有 `[e_i, l_i]`，服务必须在窗口内开始 | p.504, Table 1, formula (7) | 客户使用 Solomon `ready_time/due_time`；station 使用 depot 时间窗 | 部分一致 |
| 早到等待 | 服务不能早于 `e_i`，早到会等待 | p.504 Section 3 | `evaluator.py` 中若 `time < ready_time` 则 `time = ready_time` | 一致 |
| 迟到 | 服务不允许晚于 `l_i` 开始；但服务可在 `l_i` 之后结束 | p.504 Section 3 | `time > due_time` 记 violation；服务结束可晚于 due | 部分一致：当前允许产生 violation 后继续传播 |
| 服务时间 | 每个节点有服务时间，depot 服务时间为 0 | p.504, Table 1 | 客户读取 `service_time`；depot/station 为 0 | 一致 |
| 满电出发 | 从 depot/charging station 离开时相当于满电 Q | p.505 formula (11) | evaluator 每条路线开始 `battery = battery_capacity`；到 station/depot 后充满 | 一致 |
| 能耗 | 每条弧消耗 `h * d_ij` | p.504 Section 3, formula (10)-(11) | `energy = leg * consumption_rate` | 一致 |
| 固定充电站 | 有固定充电站集合 F | p.504 Section 3 | 代码从 Solomon 坐标范围随机生成 station，默认 21 个 | 部分一致：位置生成方式不同 |
| 重复访问充电站 | 通过 dummy vertices `F'` 允许多次访问充电站 | p.504 Section 3, Table 1 | 代码允许 station id 出现在路线中，但没有复制为多个 dummy 节点 | 部分一致 |
| 部分充电 | 到站后补到满电 Q | p.504 Section 3 | 代码到 station 后充满 | 一致 |
| 充电函数 | 线性充电；论文说明真实世界末段充电更慢，但为简化采用线性 | p.504 Section 3 | `charging_time = recharge_amount / recharge_rate` | 一致 |
| 车辆固定成本 | 文本层级目标首先最小化车辆数；MILP 公式 (1) 是距离目标 | p.504 formula (1) and paragraph before it | `priority_objective()` 用 `1_000_000 * vehicle_count` | 实现方式不同 |
| 等待/充电/总工时成本 | 论文 MILP 目标主要是车辆数和距离；充电时间影响时间传播 | p.504-p.505 | 当前 `priority_objective()` 在车辆数和距离后加入 waiting+charging cost | 当前代码扩展 |
| 中途回仓库 | 论文每条路线从 0 到 N+1；未说明中途回仓再继续同一路线 | p.504 | 代码路线以 0 隐式出发返回；中途 depot 若作为 node 不常规使用 | 未明确说明/部分一致 |
| 客户节点充电 | 只在 recharging station 充电 | p.504 Section 3 | 只有 station 或 depot 触发充电 | 一致 |
| 载重影响能耗 | 论文讨论真实能耗受载重影响，但模型为常数耗电率 h | p.504 左栏与右栏 | 代码常数 `consumption_rate` | 一致于论文简化模型 |

---

# 3. Sets, Nodes and Network

## 论文集合与代码字段

| 符号 | 类型 | 含义 | 当前代码中的对应字段 |
|---|---|---|---|
| `0, N+1` | depot instances | 出发仓库和返回仓库，表示同一物理仓库 | `instance["depot"]`，代码只用 id `0` |
| `F'` | dummy station visits | 充电站访问的 dummy vertex 集，允许多次访问同一物理站 | `instance["stations"]`，未复制 dummy |
| `F'_0` | station visits plus depot 0 | 含出发仓库的充电访问集合 | depot + stations |
| `V` | customers | 客户集合 `{1,...,N}` | `instance["customers"]` |
| `V_0` | customers plus depot 0 | 客户加出发仓库 | depot + customers |
| `V'` | customers plus station visits | `V ∪ F'` | customers + stations |
| `V'_0` | customers/stations plus depot 0 | `V' ∪ {0}` | nodes without return-depot copy |
| `V'_{N+1}` | customers/stations plus depot N+1 | `V' ∪ {N+1}` | nodes plus implicit return to depot id 0 |
| `V'_{0,N+1}` | all including depot start and end | `V' ∪ {0} ∪ {N+1}` | `instance["nodes"]` plus implicit depot return |
| `A` | directed arcs | 完全有向图中的可行或候选弧 | 代码没有显式 arc 集，按欧氏距离即时计算 |

## 关键说明

1. **仓库是否同时作为出发点和返回点。** 论文用 `0` 和 `N+1` 表示同一仓库的两个实例，便于时间和流约束建模。当前代码只用 `id=0`，每条 route 计算时自动在末尾加 `[depot_id]`。

2. **客户和充电站是否允许重复访问。** 论文客户通过公式 (2) 强制一次访问；充电站通过公式 (3) 对 dummy visit 限制最多一次，但物理充电站可通过多个 dummy vertex 多次访问。当前代码客户通过 evaluator 检查一次服务；充电站可以作为同一个 id 多次出现在不同路线或同一路线中，但不是论文的 dummy 复制方式。

3. **充电站是否复制成多个虚拟节点。** 论文明确使用 `F'` dummy vertices。当前项目未复制，只生成 `station_count` 个 station 节点。

4. **网络是有向还是无向。** 论文定义 complete directed graph `G=(V'_{0,N+1}, A)`。当前距离为欧氏距离，数值上对称，但路线方向仍按顺序计算。

5. **距离和行驶时间是否相同。** 论文区分 `d_ij` 和 `t_ij`。当前项目没有速度字段，`evaluator.py` 中 `time += leg`，即 `t_ij = d_ij`，等价于速度为 1。这是**代码中的实现假设**。

6. **节点编号对应。** 论文客户编号为 `1,...,N`，充电站 dummy 另成集合；当前代码沿用 Solomon 客户原始 id，station id 从 `1000` 开始，depot 为 `0`。

---

# 4. Parameters

| 论文符号 | 含义 | 单位 | 数据来源 | 当前代码字段 | 当前取值/生成方式 | 是否一致 |
|---|---|---|---|---|---|---|
| `d_ij` | 节点 i 到 j 的距离 | 距离单位 | Solomon 坐标计算 | `distance_matrix`, `_distance()` | 欧氏距离 `hypot(dx,dy)` | 一致 |
| `t_ij` | 节点 i 到 j 的行驶时间 | 时间单位 | 论文区分距离和时间 | 无独立字段 | 当前 `travel_time = distance` | 部分一致 |
| `q_i` | 节点 i 的需求，非客户为 0 | 货物单位 | Solomon demand | `customer["demand"]` | 原始 Solomon；station/depot 为 0 | 一致 |
| `e_i` | 最早开始服务时间 | 时间 | Solomon/生成时间窗 | `ready_time` | 客户 Solomon，station 用 depot 时间窗 | 部分一致 |
| `l_i` | 最晚开始服务时间 | 时间 | Solomon/生成时间窗 | `due_time` | 客户 Solomon，station 用 depot 时间窗 | 部分一致 |
| `s_i` | 服务时间 | 时间 | Solomon service time | `service_time` | 客户 Solomon，depot/station 为 0 | 一致 |
| `C` | 车辆载重容量 | 货物单位 | Solomon vehicle capacity | `vehicle_capacity` | `raw["vehicle_capacity"]` | 一致 |
| `Q` | 电池容量 | 电量 | 论文按 benchmark 构造规则设置 | `battery_capacity` | `_estimate_battery_capacity()` | 部分一致 |
| `h` | 电量消耗率 | 电量/距离 | 论文 benchmark 设为 1.0 | `consumption_rate` | 配置文件默认 1.0 | 一致 |
| `g` | 充电速率 | 电量/时间 | 论文设定满充需要 3 倍平均服务时间 | `recharge_rate` | `Q / (3 * avg_service_time)` | 一致于原则 |
| 车辆固定成本 | 车辆数优先 | 目标层级 | 论文文本说明层级目标 | `priority_objective()` 权重 | `1_000_000 * vehicle_count` | 实现方式不同 |
| 距离成本 | 总行驶距离 | 距离 | 论文公式 (1) | `distance`, `route_distance()` | 欧氏距离求和 | 一致 |
| 等待成本 | 论文非主要目标，等待影响时间传播 | 时间 | 论文约束 | `waiting_and_charging_cost` | priority 中低优先级加入 | 代码扩展 |
| 充电时间成本 | 论文通过时间约束体现 | 时间 | 论文约束 (6) | `charging_time` | priority 中低优先级加入 | 代码扩展 |
| 最大路线时长 | depot 时间窗 `l_0` 间接限制 | 时间 | Solomon depot due time | depot `due_time` | evaluator 当前只在访问 depot/station 充电，不显式检查 depot return due | 部分实现 |
| station_count | 充电站数量 | 个数 | 论文大实例 21 个 | `station_count` | 配置默认 21 | 一致于数量 |
| customer selection | 小实例客户抽样 | 个数 | 论文从大实例随机抽 5/10/15 | `_select_customers()` | fixed seed random sample 或 first_n | 部分一致 |

## 当前项目参数来源判断

- `vehicle_capacity`：来自 Solomon 原始 JSON，不是当前代码生成。
- `battery_capacity`：当前代码根据论文第 5.2.1 节思想近似生成，但不是论文公开 benchmark 的原始 Q。
- `consumption_rate`：配置默认 `1.0`，与论文第 5.2.1 节一致。
- `recharge_rate`：代码按 `Q / (3 * 平均客户服务时间)`，与论文第 5.2.1 节原则一致。
- `station_count`：默认 21，与论文大实例一致。
- `customer selection`：当前代码固定 seed 抽样；论文也随机抽小规模客户，但具体随机结果若无 benchmark 文件无法确认一致。
- `battery capacity estimation`：代码 `_estimate_battery_capacity()` 与论文文字规则相近：取 60% 平均 route length 和两倍 customer-station longest arc 的最大值。但由于“best-known VRPTW solution route length”当前用最近邻估计替代，所以不是严格复现。

---

# 5. Decision Variables

| 变量 | 数学含义 | 类型 | 当前代码对应 | 是否显式存储 |
|---|---|---|---|---|
| `x_ij` | 是否行驶弧 `(i,j)` | binary | route 中相邻节点隐式表示弧 | 否，隐式 |
| `τ_i` | 到达节点 i 的时间 | continuous | `evaluator.py` 局部变量 `time` | 否，临时计算 |
| `u_i` | 到达节点 i 时剩余货物/载重状态 | continuous | `evaluator.py` 局部变量 `load`，但含义为累计需求 | 否，临时计算且方向不同 |
| `y_i` | 到达节点 i 时剩余电量 | continuous | `evaluator.py` 局部变量 `battery` | 否，临时计算 |
| 使用车辆 | 是否启用某条 route | implicit | `vehicle_count = len(nonempty routes)` | 否，隐式 |
| 充电量 | 到站后补到 Q 的电量差 | continuous | `recharge_amount = Q - battery` | 否，临时计算 |

## 当前 routes 是否足以完整表达论文解

**结论：不完全足够。**

当前统一解格式是：

```python
routes = [[customer_or_station_id, ...], ...]
```

它能表达：

- 客户访问顺序；
- 车辆路线划分；
- 充电站插入位置；
- 隐式行驶弧。

它不能显式保存：

- 每个节点到达时间 `τ_i`；
- 每个节点离开时间；
- 每个节点到达电量 `y_i`；
- 充电前电量；
- 充电量；
- 充电时间；
- 等待时间；
- 论文中的 dummy station visit 编号；
- depot start `0` 和 depot end `N+1` 的区分。

因此当前 routes 是一个“路径骨架”，完整状态需要 evaluator 或 route simulator 重新传播。

---

# 6. Objective Function

## 论文目标函数

**论文事实。** 第 3 节文字说明 E-VRPTW 的目标是层级式的：首先最小化车辆数，其次最小化总行驶距离。紧接着给出的 MILP 目标函数 (1) 为：

```text
min sum_{i in V'_0} sum_{j in V'_{N+1}, i != j} d_ij x_ij
```

也就是最小化总行驶距离。

**需要进一步核实。** 论文公式 (1) 本身没有显式车辆固定成本项。结合第 3 节文字和第 5 节实验表格 `m`、`f`，可以判断论文以车辆数作为第一目标、距离作为第二目标；但 MILP 公式展示的直接目标是距离，车辆数的处理方式需要结合求解流程或固定车辆数策略理解。

## 当前项目目标函数

当前核心目标在 `route_repair.py:priority_objective()`：

```text
priority_objective =
1e9 * total_violation
+ 1e6 * vehicle_count
+ 100 * distance
+ waiting_and_charging_cost
```

其中 `total_violation` 包括客户覆盖、容量、电量、时间窗违反。

| 目标项 | 论文公式 | 自然语言含义 | 当前代码实现 | 是否一致 |
|---|---|---|---|---|
| 车辆数 | 文本层级目标 | 少用车优先 | `1e6 * vehicle_count` | 部分一致 |
| 距离 | formula (1) | 路线总距离最小 | `100 * evaluation["distance"]` | 部分一致 |
| 容量违反 | generalized cost formula (17) 中 `P_cap(S)` | 搜索中惩罚不可行 | `1e9 * capacity_violation` | 思想一致，权重不同 |
| 时间窗违反 | formula (17) 中 `P_tw(S)` | 搜索中惩罚不可行 | `1e9 * time_window_violation` | 思想一致，计算不同 |
| 电池违反 | formula (17) 中 `P_batt(S)` | 搜索中惩罚不可行 | `1e9 * battery_violation` | 思想一致，计算不同 |
| 多样化惩罚 | formula (17) 中 `P_div(S)` | 防止搜索循环/增强多样性 | baseline GA/ALNS priority 未实现 | 未实现 |
| 等待和充电成本 | 论文约束中影响时间，不是主要目标项 | 时间传播影响可行性 | `waiting_and_charging_cost` 低优先级加入 | 代码扩展 |

## 明确结论

**论文真正优化的目标：**

```text
第一层：最小化车辆数。
第二层：在车辆数确定或优先级满足后，最小化总行驶距离。
```

**当前项目真正优化的目标：**

```text
第一层：约束违反必须尽量为 0。
第二层：减少车辆数。
第三层：减少距离。
第四层：减少等待和充电时间。
```

**影响。** 当前项目比论文更“可行性优先”，会倾向于先避免违反，再减少车辆数。这有利于产生 feasible=True，但也可能让算法过度依赖 repair，并产生比论文更多的车辆或更保守的路线。

---

# 7. Constraint-by-Constraint Explanation

## Constraint (1)

### 1. Original Formula

```text
min sum_i sum_j d_ij x_ij
```

### 2. Natural-language Meaning

在给定车辆数或层级目标背景下，最小化所有被选择弧的总距离。

### 3. Small Example

如果路线 `0 -> 1 -> S -> 2 -> 0` 的距离分别为 `10, 5, 6, 12`，则距离目标为 `33`。

### 4. State Propagation

影响距离成本，不直接改变载重、时间、电量，但距离又会间接影响时间和电量。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()` 中 `distance += leg`
- `evaluator.py:route_distance()`
- `route_repair.py:priority_objective()`

处理阶段：搜索、repair 和 evaluator 都会使用距离，但算法内部目标不完全一致。

### 6. Consistency Assessment

部分一致。

### 7. Risks

当前 OR-Tools/PyVRP 内部使用的距离尺度可能与 evaluator 原始欧氏距离不完全一致；GA/ALNS 通过 repair 后的路线评价，可能不是对原始候选解直接评价。

## Constraint (2)

### 1. Original Formula

```text
sum_{j in V'_{N+1}, i != j} x_ij = 1, for all i in V
```

### 2. Natural-language Meaning

每个客户必须有且只有一条离开弧，即每个客户被访问一次。

### 3. Small Example

客户 1 若出现在路线中一次，满足；若没有出现，遗漏；若同时出现在两条路线，重复。

### 4. State Propagation

影响客户访问、路线连通性、客户覆盖。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()` 中 `served`、`missing`、`duplicate_count`
- `route_repair.py:repair_routes()` 会去重并保留首次出现客户

处理阶段：主要是 repair 和最终 evaluator；GA permutation 天然不重复客户。

### 6. Consistency Assessment

部分一致。

### 7. Risks

repair 会去除重复并按首次出现重构客户序列，可能改变算法原始解结构；搜索阶段不一定显式知道修复后的结构变化。

## Constraint (3)

### 1. Original Formula

```text
sum_{j in V'_{N+1}, i != j} x_ij <= 1, for all i in F'
```

### 2. Natural-language Meaning

每个充电站 dummy visit 最多被访问一次；物理充电站可通过多个 dummy 节点实现多次访问。

### 3. Small Example

若物理站 S 有 dummy 节点 S1、S2，则两辆车可分别访问 S1、S2；同一个 dummy S1 不应被重复使用。

### 4. State Propagation

影响充电站访问、路线连通性、电量补给。

### 5. Current Code Location

- `instance_builder.py:_generate_stations()` 生成 station id
- `route_repair.py:_repair_energy()` 插入 station

处理阶段：repair 处理；没有 dummy station 复制。

### 6. Consistency Assessment

实现方式不同。

### 7. Risks

当前同一 station id 可多次出现，无法区分论文中的多个 station visit；如果未来做严格 MILP 或状态记录，需要引入 station visit copy。

## Constraint (4)

### 1. Original Formula

```text
incoming arcs = outgoing arcs, for each node j in V'
```

### 2. Natural-language Meaning

如果车辆进入一个客户或充电站，就必须从它离开，保证路线不断裂。

### 3. Small Example

`0 -> 1 -> 2 -> 0` 连通；如果只有 `0 -> 1` 而没有离开 1，则违反。

### 4. State Propagation

影响路线连通性和客户访问顺序。

### 5. Current Code Location

当前统一 route list 天然表示连续路径；没有显式流守恒约束。

处理阶段：解表示隐式保证。

### 6. Consistency Assessment

部分一致。

### 7. Risks

只要 route list 合法，该约束成立；但如果 station/depot 特殊节点被错误插入，代码没有独立检查“入度=出度”。

## Constraint (5)

### 1. Original Formula

```text
τ_i + (t_ij + s_i)x_ij - l_0(1 - x_ij) <= τ_j
for arcs leaving customers/depot
```

### 2. Natural-language Meaning

如果车辆从 i 到 j，那么到达 j 的时间至少等于到达 i 的时间 + i 的服务时间 + i 到 j 的行驶时间。

### 3. Small Example

到达客户 1 时间为 20，服务 10，去客户 2 行驶 5，则到达客户 2 不能早于 35。

### 4. State Propagation

影响时间、服务时间、等待、时间窗。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()` 中 `time += leg`、等待、`time += service_time`
- `route_repair.py:_repair_energy()` 中相同传播逻辑

处理阶段：repair 和 evaluator；OR-Tools/PyVRP 对客户时间窗也有内部建模。

### 6. Consistency Assessment

部分一致。

### 7. Risks

当前 `t_ij = distance`，没有独立行驶时间矩阵；route_repair 的 `_repair_energy()` 在插入阶段没有显式检查 due_time，只在 `_is_route_feasible()` 中借 evaluator 检查。

## Constraint (6)

### 1. Original Formula

```text
τ_i + t_ij x_ij + g(Q - y_i) - (l_0 + gQ)(1 - x_ij) <= τ_j
for arcs leaving recharging visits
```

### 2. Natural-language Meaning

如果车辆从充电站 i 离开去 j，则离开前需要先充电到满电。充电时间取决于到站时剩余电量 `y_i`，补电量为 `Q - y_i`。

### 3. Small Example

车辆到站剩余 30，电池容量 100，充电速率 10，则充电 70 需要 7 时间单位，再加行驶时间到下一点。

### 4. State Propagation

影响充电、电量、时间、后续时间窗。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()`：station/depot 触发 `recharge_amount = Q - battery`
- `route_repair.py:_repair_energy()`：插入 station 后补电到满
- `route_repair.py:_waiting_and_charging_cost()`

处理阶段：主要 repair 和 evaluator。

### 6. Consistency Assessment

部分一致。

### 7. Risks

当前所有 station 的 `service_time=0`，充电时间单独加；搜索算法多半不知道充电站插入会如何影响后续时间窗，除非通过 repair 后目标间接感知。

## Constraint (7)

### 1. Original Formula

```text
e_i <= τ_i <= l_i
```

### 2. Natural-language Meaning

必须在每个节点的时间窗内开始服务。

### 3. Small Example

客户 1 时间窗 `[20, 50]`。车辆 15 到达则等到 20；车辆 55 到达则违反 5。

### 4. State Propagation

影响时间、等待、可行性。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()` 中 `ready_time/due_time`
- `route_repair.py:_is_route_feasible()` 调用 evaluator 检查
- `solve_ortools.py` Time Dimension
- `solve_pyvrp.py` client time windows

处理阶段：OR-Tools/PyVRP 搜索内部部分知道；GA/ALNS 主要通过 repair/evaluator 知道。

### 6. Consistency Assessment

部分一致。

### 7. Risks

当前 evaluator 不显式检查返回 depot 的 due_time；station 时间窗用 depot 时间窗，和论文 dummy station 时间窗细节可能不完全一致。

## Constraint (8)-(9)

### 1. Original Formula

```text
0 <= u_j <= u_i - q_i x_ij + C(1 - x_ij)
0 <= u_0 <= C
```

### 2. Natural-language Meaning

车辆载重状态不能为负，也不能超过容量。服务客户会消耗/减少车上待配送货物。

### 3. Small Example

车辆容量 100，客户需求分别 40、70。同一路线服务二者需求总和 110，违反容量 10。

### 4. State Propagation

影响载重、车辆数量、客户分配。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()` 中 `load += demand`，路线结束后检查 `load > vehicle_capacity`
- `route_repair.py:_pack_customers()` 插入时调用 `_is_route_feasible()`
- `solvers/common.py:split_by_capacity()` 和 `nearest_neighbor_routes()`

处理阶段：部分搜索阶段知道，repair 和 evaluator 都知道。

### 6. Consistency Assessment

部分一致。

### 7. Risks

论文变量 `u_i` 是剩余 cargo，代码 `load` 是累计需求，数学方向不同但容量判断等价。代码没有逐节点保存载重状态。

## Constraint (10)-(11)

### 1. Original Formula

```text
0 <= y_j <= y_i - h d_ij x_ij + Q(1 - x_ij)
0 <= y_j <= Q - h d_ij x_ij
```

第 (10) 组处理从客户离开的电量传播；第 (11) 组处理从 depot 或充电站离开时满电出发后的电量传播。

### 2. Natural-language Meaning

车辆走一段路就消耗 `h*d_ij` 电量。电量不能低于 0。从仓库或充电站出发时，车辆电量为满电 Q。

### 3. Small Example

Q=100，h=1，当前电量 30，下一段距离 40，则违反 10；如果先到充电站补满到 100，再走 40，剩余 60。

### 4. State Propagation

影响电量、充电站插入、路线可行性。

### 5. Current Code Location

- `evaluator.py:evaluate_solution()`：`energy = leg * consumption_rate`，`battery_violation`
- `route_repair.py:_repair_energy()`：电量不足时找 reachable station
- `route_repair.py:_best_reachable_station()`
- `enhanced_repair.py:_repair_route_energy()` 等增强模块

处理阶段：repair 和 evaluator；baseline GA/ALNS 搜索本体不直接保存 y_i。

### 6. Consistency Assessment

部分一致。

### 7. Risks

没有显式 `y_i` 状态数组，导致 destroy/repair/局部搜索难以高效判断局部电量影响；每次只能重算或依赖 full repair。

## Constraint (12)

### 1. Original Formula

```text
x_ij in {0,1}
```

### 2. Natural-language Meaning

每条弧要么被走，要么不被走。

### 3. Small Example

`0 -> 1` 被选择则 `x_01=1`；没走则为 0。

### 4. State Propagation

影响路线结构和所有后续状态传播。

### 5. Current Code Location

route 中相邻节点隐式表示被选择弧；没有显式二进制变量。

### 6. Consistency Assessment

实现方式不同。

### 7. Risks

启发式代码无法像 MILP 一样直接添加 arc-level 约束；新增复杂约束通常要放进 route simulator、repair 或 solver-specific model。

---

# 8. Complete Route Simulation Example

以下是演示例子。**演示参数不是论文原始数据**，只用于说明公式传播。

## 设定

| 节点 | 类型 | 坐标 | demand | time window | service |
|---|---|---|---|---|---|
| 0 | depot | (0,0) | 0 | [0,100] | 0 |
| 1 | customer | (3,4) | 20 | [4,30] | 5 |
| S | station | (6,4) | 0 | [0,100] | 0 |
| 2 | customer | (6,8) | 30 | [15,60] | 5 |

车辆参数：

```text
C = 100
Q = 20
h = 1
g = 5
t_ij = d_ij
```

路线：

```text
0 -> 1 -> S -> 2 -> 0
```

## 逐段计算

| 步骤 | 计算 | 结果 |
|---|---|---|
| 出发 | time=0, battery=20, load=0 | 满电出发 |
| 0->1 距离 | sqrt(3^2+4^2) | 5 |
| 到达 1 时间 | 0+5 | 5 |
| 到达 1 电量 | 20-5 | 15 |
| 客户 1 时间窗 | 5 在 [4,30] 内 | 无等待、无迟到 |
| 服务客户 1 | time=5+5 | 10 |
| 载重累计 | load=20 | 不超 C |
| 1->S 距离 | 3 | 3 |
| 到达 S 时间 | 10+3 | 13 |
| 到达 S 电量 | 15-3 | 12 |
| 充电量 | Q-battery = 20-12 | 8 |
| 充电时间 | 8/g = 8/5 | 1.6 |
| 离开 S 时间 | 13+1.6 | 14.6 |
| 离开 S 电量 | Q | 20 |
| S->2 距离 | 4 | 4 |
| 到达 2 时间 | 14.6+4 | 18.6 |
| 到达 2 电量 | 20-4 | 16 |
| 客户 2 时间窗 | 18.6 在 [15,60] 内 | 无等待、无迟到 |
| 服务客户 2 | time=18.6+5 | 23.6 |
| 载重累计 | load=50 | 不超 C |
| 2->0 距离 | 10 | 10 |
| 返回仓库时间 | 23.6+10 | 33.6 |
| 返回仓库电量 | 16-10 | 6 |
| 总距离 | 5+3+4+10 | 22 |
| 总充电时间 | 1.6 | 1.6 |
| 总等待时间 | 0 | 0 |

## 目标值

论文距离目标部分：

```text
f = 22
```

当前项目 priority 示例：

```text
violation = 0
vehicle_count = 1
distance = 22
waiting+charging = 1.6
priority_objective = 0 + 1,000,000 + 2,200 + 1.6 = 1,002,201.6
```

## 与 evaluator.py 对照

| 手算步骤 | evaluator.py 行为 | 是否一致 |
|---|---|---|
| 距离 | `_distance()` 欧氏距离 | 一致 |
| 行驶时间 | `time += leg` | 一致于当前假设 |
| 能耗 | `energy = leg * consumption_rate` | 一致 |
| 早到等待 | `if time < ready_time: time = ready_time` | 一致 |
| 迟到 | 累加 `time_window_violation` | 部分一致：论文不允许，代码先记录违反 |
| 服务时间 | `time += service_time` | 一致 |
| 到站充电 | `recharge_amount = Q - battery` | 一致 |
| 充电时间 | `time += recharge_amount / recharge_rate` | 一致 |
| 路线末尾回仓 | route 后自动加 depot | 部分一致：论文用 N+1 |

---

# 9. Data and Benchmark Construction

| 数据项 | 论文做法 | 当前项目做法 | 是否可复现 | 差异影响 |
|---|---|---|---|---|
| 基础数据 | Solomon VRPTW benchmark | 本地 Solomon JSON | 可复现基础坐标/需求/时间窗 | 一致基础 |
| 大实例 | 56 个 100-customer，21 charging stations | 配置 `solomon_56.yaml` 可跑 56 组 | 部分可复现 | station 位置未必一致 |
| 小实例 | 36 个 5/10/15-customer，从大实例随机抽取，并选用充电站使用多的实例 | 当前可配置 R101/C101/RC101 等，10/25/50 | 部分可复现 | 不等于论文表 5 的 36 组 |
| 充电站 | 一个站在 depot，其余 20 个随机生成；限制位置保证每个客户可通过最多两个不同充电站从 depot 到达 | 一个 depot station，其余在客户坐标 bbox 内随机生成 | 部分可复现 | 可行性和路线结构会明显不同 |
| 电池容量 Q | max(60% of average route length of BKS VRPTW, 2 * longest customer-station arc energy) | max(0.6 * nearest-neighbor avg route length, 2 * longest customer-station distance, 1.0) | 部分可复现 | 当前用最近邻估计替代 BKS |
| 能耗率 h | 1.0 | config 默认 1.0 | 可复现 | 一致 |
| 充电速率 g | 满充需要 3 倍平均客户服务时间 | `Q/(3*avg_service_time)` | 可复现 | 一致于原则 |
| 时间窗 | 原 Solomon 时间窗可能导致不可行，论文重新生成可行时间窗 | 当前配置写有 `fallback_mode`，但代码主要使用 Solomon 原始时间窗 | 部分可复现 | 当前可能比论文更容易不可行 |
| 随机种子 | 论文未在 PDF 该页明确给出具体 seed | 当前 `seed=1987` | 代码可复现 | 与论文随机实例不保证一致 |
| benchmark 是否公开 | 论文给出 URL：evrptw.wiwi.uni-frankfurt.de | 当前没有论文原始 benchmark 文件 | 需要人工核对 | 当前不是原始 benchmark 复现 |

## 当前项目性质判断

当前项目属于：

```text
基于 Solomon 的扩展实例 / 自定义实验实例
```

不是严格的：

```text
论文原始 benchmark 复现
```

---

# 10. Paper Algorithm

## 论文 VNS/TS 如何处理约束

**论文事实。** 第 4 节提出 hybrid VNS/TS。Figure 1 给出主流程。算法先 preprocess infeasible arcs，再生成初始解。搜索允许不可行解，通过 generalized cost function (17) 惩罚容量、时间窗、电池违反和多样化惩罚。

广义成本：

```text
f_gen(S) = f(S) + α P_cap(S) + β P_tw(S) + γ P_batt(S) + P_div(S)
```

其中 `α, β, γ` 动态调整。论文第 4.2 节还说明容量违反、电池违反、时间窗违反可以高效增量计算。

| 算法环节 | 论文方法 | 当前 GA | 当前 ALNS | 差异 |
|---|---|---|---|---|
| 解表示 | route set `S={r_k}`，含客户和充电站访问 | customer permutation，经 repair 变 routes | `EVRPTWState(instance,routes,unassigned)` | 当前 GA 原始 individual 不含 station/time/battery |
| 初始解 | 角度排序插入，逐步开路线 | 随机排列 population | 最近邻 + repair | 与论文不同 |
| 时间窗处理 | 插入时用规则和 penalty slack 高效计算 | 主要由 repair/evaluator 判断 | objective 中调用 repair/evaluator | 当前更依赖 full repair |
| 电量处理 | preprocessing + battery violation 计算 + charging station 逻辑 | route_repair 插入 station | route_repair 插入 station | 当前搜索 state 不保存 y_i |
| 充电站插入 | 论文解中包含 dummy station visits | repair_energy 自动插入 station | repair_energy 自动插入 station | 充电站不是搜索变量主体 |
| 不可行解 | 允许，用 generalized cost 惩罚 | 可通过 priority penalty 评价，但 repair 先强修 | ALNS state 可有 unassigned，objective 惩罚 | 思想部分一致 |
| 邻域算子 | VNS cyclic-exchange；TS intensification | PMX crossover, mutation | random/worst/segment removal, greedy/regret repair | 当前算子与论文不同 |
| 候选评价 | `f_gen`，动态 penalty | `priority_objective` 固定权重 | `priority_objective` 固定权重 | 当前无动态 penalty 和 P_div baseline |
| 停止条件 | feasibility phase + distance phase 参数 | 固定 generations | fixed iterations | 不同 |

## 为什么论文方法能直接处理 E-VRPTW

论文方法把容量、时间窗、电池违反都作为候选解评价的一部分，并针对 route 维护前后向 penalty 信息，使局部变动后能快速判断影响。换句话说，约束不是“最后才检查”，而是参与搜索方向。

## 当前 GA/ALNS 为什么依赖公共 repair

当前 GA individual 只是客户排列；ALNS state 主要是 routes 和 unassigned。二者没有显式 `τ_i`、`u_i`、`y_i`、充电记录。因此它们无法直接知道某个 crossover、mutation、destroy 或 insertion 对时间窗和电量的细粒度影响，只能把结果交给 `repair_routes()` 和 `evaluate_solution()` 重算。

---

# 11. Paper-to-Code Mapping

| 论文概念 | 论文符号/编号 | 当前文件 | 当前函数 | 实现状态 | 需要修改 |
|---|---|---|---|---|---|
| Solomon 数据读取 | Section 5.2.1 | `data_loader.py` | `load_solomon_instance`, `solomon_customers` | 已正确实现基础字段 | 若严格复现需导入论文 benchmark |
| 客户集合 | `V` | `data_loader.py` | `solomon_customers` | 已实现 | 无 |
| depot start/end | `0,N+1` | `data_loader.py`, `evaluator.py` | `solomon_depot`, route append depot | 部分实现 | 区分 start depot 和 end depot |
| station dummy visits | `F'` | `instance_builder.py` | `_generate_stations` | 部分实现 | 增加 dummy station copy |
| 距离 | `d_ij` | `instance_builder.py`, `evaluator.py` | `_euclidean`, `_distance` | 已实现 | 若使用论文 benchmark，需一致距离精度 |
| 行驶时间 | `t_ij` | `evaluator.py` | `time += leg` | 当前简化 | 增加 travel_time_matrix 或 speed |
| 车辆容量 | `C` | `instance_builder.py` | `vehicle_capacity = raw[...]` | 已实现 | 无 |
| 电池容量 | `Q` | `instance_builder.py` | `_estimate_battery_capacity` | 部分实现 | 用论文 BKS route length 或原始 benchmark Q |
| 耗电率 | `h` | config + `instance_builder.py` | `consumption_rate` | 已实现 | 无 |
| 充电速率 | `g` | `instance_builder.py` | `recharge_rate` | 部分实现 | 校准与论文实例完全一致 |
| 目标距离 | formula (1) | `evaluator.py`, `route_repair.py` | `route_distance`, `priority_objective` | 部分实现 | 统一内部 objective 与论文目标 |
| 客户一次服务 | formula (2) | `evaluator.py` | `evaluate_solution` | 最终 evaluator 检查 | 搜索阶段也应维护 |
| station visit 限制 | formula (3) | `route_repair.py` | `_repair_energy` | 实现方式不同 | 引入 dummy visits |
| 流守恒 | formula (4) | route list | 隐式 | 部分实现 | 对异常 route 加显式 validator |
| 时间传播 | formula (5)-(6) | `evaluator.py`, `route_repair.py` | `evaluate_solution`, `_repair_energy` | 部分实现 | 建立统一 route simulator |
| 时间窗 | formula (7) | `evaluator.py` | `evaluate_solution` | 部分实现 | 搜索插入时直接检查 |
| 载重传播 | formula (8)-(9) | `evaluator.py` | `load` | 部分实现 | 保存每节点 load 或 remaining cargo |
| 电量传播 | formula (10)-(11) | `evaluator.py`, `route_repair.py` | `battery`, `_repair_energy` | 部分实现 | 保存 per-node battery state |
| binary arc | formula (12) | route list | 隐式 | 实现方式不同 | 如做 MILP/OR-Tools 严格建模需显式 arcs |
| infeasible arc preprocessing | formula (13)-(16) | 暂无专门模块 | 无 | 未实现 | 新增 arc_preprocessor |
| generalized cost | formula (17) | `route_repair.py` | `priority_objective` | 部分实现 | 动态 penalty 和 diversification |
| VNS/TS | Figure 1, Section 4 | `solve_alns.py`, hybrid modules | ALNS operators | 算法不同 | 若复现论文需实现 VNS/TS 或说明替代 |
| benchmark construction | Section 5.2.1 | `instance_builder.py` | `build_instance` | 部分实现 | 导入原始 benchmark 或严格重建规则 |

---

# 12. Gap Analysis

## Critical Gaps

| 差异 | 论文要求 | 当前代码 | 影响 | 建议 | 优先级 |
|---|---|---|---|---|---|
| 原始 benchmark 缺失 | 使用论文构造并公开的 E-VRPTW instances | 当前自行基于 Solomon 生成 | 结果不能与表 5/6 数值严格比较 | 尝试获取 benchmark；否则明确为 paper-like instance | 高 |
| 搜索阶段不保存时间/电量状态 | 论文算法能计算 `P_tw`, `P_batt` 并指导搜索 | GA/ALNS 多依赖 full repair/evaluator | 搜索方向不够约束感知 | 建统一 route simulator 并接入 decoder/insertion | 高 |
| station dummy visits 未实现 | `F'` 允许多次访问同一站 | 同一个 station id 可重复使用 | 与 MILP 结构不一致 | 增加 station visit copy 或在文档中声明简化 | 高 |
| 时间窗生成不同 | 论文为可行实例重新生成时间窗 | 当前主要沿用 Solomon 原时间窗 | 可行性/车辆数不同 | 实现 paper-like feasible time-window regeneration | 高 |

## Important Simplifications

| 差异 | 论文要求 | 当前代码 | 影响 | 建议 | 优先级 |
|---|---|---|---|---|---|
| `t_ij = d_ij` | 论文区分距离和行驶时间 | 代码默认速度 1 | 若未来加入速度/无人机会受限 | 增加 travel_time_matrix | 中 |
| Q 估计用最近邻替代 BKS | 论文用对应 VRPTW BKS 平均路线长度 | 当前用 nearest-neighbor estimate | Q 可能偏大或偏小 | 用已知 Solomon BKS 或先固定公开 Q | 中 |
| objective 权重化 | 论文层级目标 + generalized penalty | 当前大权重标量 | 可能掩盖距离/等待差异 | 同时记录 lexicographic metrics | 中 |
| depot end 时间窗 | 论文有 N+1 | 当前未严格单独建模 | 可能漏检最大路线时长 | evaluator 增加 return depot due check | 中 |

## Acceptable Engineering Choices

| 差异 | 论文要求 | 当前代码 | 影响 | 建议 | 优先级 |
|---|---|---|---|---|---|
| route list 代替 `x_ij` | MILP binary arcs | 启发式用 routes | 工程上合理 | 加 route validator 即可 | 低 |
| 线性充电 | 论文简化为线性 | 当前线性充电 | 一致 | 后续 EVRPTW-NL 再扩展 | 低 |
| 固定 seed | 论文 PDF 未明确 seed | 当前固定 seed | 增强复现实验可重复性 | 文档记录 seed | 低 |

---

# 13. Recommendations for Constraint-Aware GA and ALNS

## GA

**需要修改的位置：**

| 部分 | 当前状态 | 建议 |
|---|---|---|
| individual representation | 客户排列 | 保留客户排列，但 decoder 必须输出 route + station + state trace |
| decoder | `repair_customer_order()` 强修 | 改为 constraint-aware split and insert decoder |
| fitness | `priority_objective()` 固定权重 | 使用论文式 `f + αP_cap + βP_tw + γP_batt`，并记录分项 |
| initialization | 随机排列 | 加入 Solomon/论文类似角度排序、最近邻、time-window seed |
| crossover | PMX，仅保证排列合法 | crossover 后立即 route simulator 评估，不直接 full repair 掩盖结构 |
| mutation | inversion/shuffle | 增加 relocate、station insertion/removal、route split/merge mutation |
| repair | 高强度 full repair | 改为 minimal repair：只修局部违反，不大幅重排所有客户 |
| elitism | 当前 baseline GA 没有强显式 elitism | 保留 feasible best，并按车辆数、距离、违约分项排序 |

**时间窗约束进入位置。**

- 初始化时优先生成早窗客户在前的顺序。
- decoder 中插入客户时传播 `arrival/start/departure`。
- fitness 中计算 `P_tw`。
- mutation/crossover 后不满足时局部修复，而不是整条路线重建。

**电量约束进入位置。**

- decoder 中每段行驶计算 `battery -= h*d_ij`。
- 若不足，尝试插入 station。
- 若插入 station 会导致时间窗恶化，fitness 同时反映 `P_tw` 和 `P_batt`。

**必须由 route simulator 计算的状态。**

```text
arrival_time, waiting_time, service_start, departure_time,
load_or_remaining_cargo, battery_arrival, charge_amount,
charging_time, battery_departure
```

## ALNS

**需要修改的位置：**

| 部分 | 当前状态 | 建议 |
|---|---|---|
| state | routes + unassigned | 增加 route traces: time, battery, load, charging events |
| objective | priority_objective | 增加论文式动态 penalty 或至少分项 objective |
| destroy | 随机/距离/增强算子 | 加 time-critical, energy-critical, station-critical removal |
| insertion feasibility | 多处依赖 repair/evaluator | 插入每个位置时直接 route simulator 检查 |
| repair | 容易 full repair | 使用 regret + energy-aware + TW-aware minimal repair |
| acceptance | ALNS library SA | 接受准则基于分项 objective，不能只看一个总标量 |
| operator selection | RouletteWheel | 用 operator diagnostics 根据成功率动态调整 |

**论文依据。**

- Preprocessing 对应公式 (13)-(16)。
- Generalized cost 对应公式 (17)。
- 电量传播对应公式 (10)-(11)。
- 时间传播对应公式 (5)-(7)。

## Hybrid

当前 GA+ALNS 共享同一个强 `repair_routes()`，导致两者行为重复。建议分工：

- GA：负责全局客户顺序和路线大结构。
- ALNS：负责局部客户重插入、路线合并、充电站位置优化。
- Shared route simulator：负责统一传播时间、载重、电量，不负责随意重排路线。
- Minimal repair：只处理局部违反，避免 GA 和 ALNS 的差异被 full repair 抹平。

---

# 14. Recommended Implementation Order

| Stage | 修改目标 | 涉及文件 | 验证方式 | 完成标准 | 风险 |
|---|---|---|---|---|---|
| Stage 1 | 统一 route simulator | 新增 `route_simulator.py`，调用 `evaluator.py` | 手算例子对照 | 输出每节点 time/load/battery/charging trace | 与旧 evaluator 指标不一致 |
| Stage 2 | 校准 evaluator 与论文公式 | `evaluator.py`, `route_repair.py` | 3-customer 单元测试 | `P_cap/P_tw/P_batt` 分项明确 | 影响历史结果 |
| Stage 3 | raw vs repaired 诊断 | diagnostics 模块 | 同一解保存修复前后指标 | 能看出 repair 改动幅度 | 日志变多 |
| Stage 4 | constraint-aware GA decoder | `solve_ga.py` 或新 GA 模块 | 比较 repair 前 feasible rate | GA 原始解可行率提升 | 运行变慢 |
| Stage 5 | constraint-aware ALNS insertion | `solve_alns.py`, `enhanced_repair.py` | 插入位置可行性测试 | 插入时直接处理 TW/battery | 实现复杂 |
| Stage 6 | minimal repair | `route_repair.py` 或新模块 | 对比 full repair 改动客户顺序 | 修复不大幅重排 | 可行率下降 |
| Stage 7 | 重新测试 Hybrid | hybrid modules | GA vs ALNS vs Hybrid 多 seed | Hybrid 有明确互补性证据 | 不一定优于 GA |
| Stage 8 | 实验与报告 | benchmark runner | R/C/RC 10/25/50 多 seed | 平均值、标准差、路线图齐全 | 时间成本高 |

---

# 15. Final Learning Summary

## 15.1 一页问题模型概览

E-VRPTW 是在 VRPTW 上加入电动车电池和充电站约束的问题。车辆从仓库出发，服务每个客户一次，并最终返回仓库。每个客户有需求、服务时间和时间窗。车辆有载重容量 C 和电池容量 Q。每走一段距离 `d_ij` 消耗 `h*d_ij` 电量。若电量不足，车辆必须在充电站补电；论文假设充电是线性的，且到站后充到满电。目标层级为先减少车辆数，再减少总距离。论文用 MILP 精确定义问题，并用 VNS/TS 启发式求解大规模实例。

## 15.2 符号表

| 符号 | 含义 |
|---|---|
| `V` | 客户集合 |
| `F'` | 充电站访问 dummy 集合 |
| `0,N+1` | 出发和返回仓库实例 |
| `d_ij` | 距离 |
| `t_ij` | 行驶时间 |
| `C` | 车辆容量 |
| `Q` | 电池容量 |
| `h` | 耗电率 |
| `g` | 充电速率 |
| `q_i` | 需求 |
| `e_i,l_i` | 时间窗 |
| `s_i` | 服务时间 |
| `x_ij` | 是否走弧 |
| `τ_i` | 到达时间 |
| `u_i` | 到达时剩余 cargo |
| `y_i` | 到达时剩余电量 |

## 15.3 参数表

重点参数：`d_ij, t_ij, C, Q, h, g, q_i, e_i, l_i, s_i`。当前代码中 `C,q_i,e_i,l_i,s_i` 主要来自 Solomon；`Q,g,stations` 由项目按论文思想生成。

## 15.4 变量表

当前项目没有显式保存 `x_ij, τ_i, u_i, y_i`，而是用 routes 隐式表示 `x_ij`，并在 evaluator 中临时计算 `time/load/battery`。

## 15.5 目标函数表

| 来源 | 目标 |
|---|---|
| 论文 | 层级目标：车辆数优先，其次距离；MILP 公式 (1) 展示距离最小化 |
| 当前项目 | 约束违反优先，其次车辆数、距离、等待/充电 |

## 15.6 约束总表

| 编号 | 含义 | 当前实现 |
|---|---|---|
| (2) | 客户一次服务 | evaluator + repair |
| (3) | station dummy visit 最多一次 | 未按 dummy 实现 |
| (4) | 流守恒 | route list 隐式 |
| (5)-(6) | 时间传播含充电 | evaluator/repair 部分实现 |
| (7) | 时间窗 | evaluator/OR-Tools/PyVRP 部分处理 |
| (8)-(9) | 容量 | evaluator/repair/common |
| (10)-(11) | 电量 | evaluator/repair |
| (12) | 弧变量二进制 | route list 隐式 |
| (13)-(16) | infeasible arc preprocessing | 未专门实现 |
| (17) | generalized cost | priority_objective 部分近似 |

## 15.7 论文到代码映射图

```text
Solomon data
  -> data_loader.py
  -> instance_builder.py
       customers/depot/stations/Q/g/h
  -> solver wrappers
       OR-Tools / GA / PyVRP / ALNS / Hybrid
  -> route_repair.py
       capacity/time/battery repair and charging insertion
  -> evaluator.py
       final feasibility and distance
  -> result_schema.py / run_experiments.py / visualization.py
       output and plots
```

## 15.8 当前项目最大的 10 个差异

1. 没有论文原始 benchmark。
2. 充电站位置不保证与论文一致。
3. 小实例抽样不保证与论文 36 组一致。
4. 电池容量 Q 用最近邻估计替代 BKS route length。
5. 没有 dummy station visits。
6. 没有独立 `t_ij`，默认 `t_ij=d_ij`。
7. 搜索 state 不保存 `τ_i,u_i,y_i`。
8. GA/ALNS 依赖 full repair。
9. objective 与论文层级目标不同。
10. 未实现论文 VNS/TS 的 cyclic-exchange、tabu 和动态 penalty 体系。

## 15.9 必须真正理解的 10 条公式

1. 公式 (1)：距离目标。
2. 公式 (2)：客户一次服务。
3. 公式 (3)：充电站 dummy visit 限制。
4. 公式 (4)：流守恒。
5. 公式 (5)：客户/depot 离开后的时间传播。
6. 公式 (6)：充电站离开后的时间传播。
7. 公式 (7)：时间窗。
8. 公式 (8)-(9)：载重容量。
9. 公式 (10)-(11)：电量传播。
10. 公式 (17)：广义惩罚成本函数。

## 15.10 必须优先阅读的 10 个代码函数

1. `EVRPTW_Schneider2014/data_loader.py:load_solomon_instance`
2. `EVRPTW_Schneider2014/data_loader.py:solomon_customers`
3. `EVRPTW_Schneider2014/instance_builder.py:build_instance`
4. `EVRPTW_Schneider2014/instance_builder.py:_estimate_battery_capacity`
5. `EVRPTW_Schneider2014/evaluator.py:evaluate_solution`
6. `EVRPTW_Schneider2014/route_repair.py:repair_routes`
7. `EVRPTW_Schneider2014/route_repair.py:_repair_energy`
8. `EVRPTW_Schneider2014/route_repair.py:priority_objective`
9. `EVRPTW_Schneider2014/solvers/solve_ga.py:solve`
10. `EVRPTW_Schneider2014/solvers/solve_alns.py:solve`

## 15.11 修改代码前必须能独立回答的 20 个问题

1. E-VRPTW 与 VRPTW 的核心区别是什么？
2. 为什么论文要复制 depot 为 `0` 和 `N+1`？
3. 为什么论文要把充电站复制为 dummy visits？
4. `d_ij` 和 `t_ij` 是否一定相等？
5. 论文中的 `h*d_ij` 表示什么？
6. 到充电站后是部分充电还是满充？
7. 充电时间为什么是 `g(Q-y_i)` 或等价线性表达？
8. 当前代码中的 `recharge_rate` 和论文 `g` 是否方向一致？
9. 客户时间窗要求的是开始服务还是完成服务？
10. 早到等待是否违反约束？
11. 晚到如何计算 violation？
12. 当前 routes 是否保存到达时间？
13. 当前 routes 是否保存到达电量？
14. 为什么 full repair 会掩盖 GA 和 ALNS 的搜索差异？
15. 论文 generalized cost 与当前 priority_objective 有什么不同？
16. 当前 Q 是从哪里来的？
17. 当前 station 位置是从哪里来的？
18. 当前实验能否直接和论文表 5 比较？
19. 如果加入非线性充电，公式 (6) 应如何改变？
20. 如果加入无人机同步，需要新增哪些状态变量？

---

# 实际读取记录

## 实际读取的论文章节

- PDF p.500-501：标题、摘要、问题动机。
- PDF p.504-505：Section 3 problem formulation、Table 1、公式 (1)-(12)。
- PDF p.506-507：Figure 1、preprocessing 公式 (13)-(16)、generalized cost formula (17)、VNS/TS 约束违反计算说明。
- PDF p.510-513：Section 5.2.1 benchmark construction、Table 4、Table 5、Table 6。
- PDF p.512-520：相关 benchmark 对比和结论部分的主要文本。

## 实际读取的代码文件

- `EVRPTW_Schneider2014/data_loader.py`
- `EVRPTW_Schneider2014/instance_builder.py`
- `EVRPTW_Schneider2014/evaluator.py`
- `EVRPTW_Schneider2014/route_repair.py`
- `EVRPTW_Schneider2014/result_schema.py`
- `EVRPTW_Schneider2014/run_single.py`
- `EVRPTW_Schneider2014/run_experiments.py`
- `EVRPTW_Schneider2014/solvers/common.py`
- `EVRPTW_Schneider2014/solvers/solve_ga.py`
- `EVRPTW_Schneider2014/solvers/solve_alns.py`
- `EVRPTW_Schneider2014/solvers/solve_ortools.py`
- `EVRPTW_Schneider2014/solvers/solve_pyvrp.py`
- `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/solution_adapter.py`
- `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/hybrid_solver.py`
- `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/enhanced_destroy.py`
- `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/enhanced_repair.py`
- `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/local_search.py`
- `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/diagnostics.py`

## 无法确认的问题

1. 当前 PDF 中没有直接给出可下载 benchmark 文件的实际内容，因此无法确认当前随机生成 station 与论文 benchmark 一致。
2. PDF 第 5.2.1 节说明小实例随机抽取，但未在可读文本中给出具体随机种子。
3. 论文的 MILP 公式 (1) 展示距离目标，但文本说明目标层级先车辆数后距离；车辆数在精确求解中的具体固定/搜索方式需要进一步核对全文细节或补充材料。
4. 当前项目配置中写有 `fallback_mode: regenerated_feasible`，但已读代码中未看到完整时间窗重生成逻辑。

## 需要人工核对的内容

1. 是否能从论文 URL 或其他来源下载原始 E-VRPTW benchmark。
2. 论文中 `g` 的单位表达与当前代码 `recharge_rate = Q / charging_time` 是否完全同向；从代码看是“电量/时间”，从公式 (6) 的写法可能需要结合原文符号再次核对。
3. 表 5 的 36 个小规模实例是否需要作为下一步严格复现实验的固定实例列表。
4. 如果后续扩展 EVRPTW-NL，是否保留论文满充假设，还是引入部分充电和非线性充电函数。

