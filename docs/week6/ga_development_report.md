# Truck-Drone EVRPTW-NL 中 GA 方法阶段性开发报告

本文档单独记录 `TruckDrone_EVRPTW_NL` 模块中 GA 方法从“仅卡车/简单路线生成”扩展到“无人机-卡车协同、非线性充电、多车辆可行解构造器”的完整过程。

本文档重点回答：

- GA 每一步为什么要改；
- 遇到了什么问题；
- 具体改了哪些结构和函数；
- 改完后的效果如何；
- 当前 GA 方法的优缺点；
- 后续它适合在整体研究中承担什么角色。

当前相关代码主要位于：

- `TruckDrone_EVRPTW_NL/solvers/solve_ga.py`
- `TruckDrone_EVRPTW_NL/solvers/ga_tools.py`
- `TruckDrone_EVRPTW_NL/route_simulator.py`
- `TruckDrone_EVRPTW_NL/evaluator.py`
- `TruckDrone_EVRPTW_NL/docs/modeling_and_progress.md`

---

## 1. GA 方法在本项目中的定位

最初的 GA 思路比较接近普通 VRP/VRPTW：

```text
客户排列
-> 解码成卡车路线
-> evaluator 检查约束
-> 根据成本和罚项选择较优解
```

但 Truck-Drone EVRPTW-NL 不是普通 VRP。它同时包含：

- 多辆电动卡车；
- 无人机从卡车发射、回收；
- 客户可由卡车或无人机服务；
- 无人机可连续服务多个客户；
- 卡车和无人机都可能受电量限制；
- 卡车和无人机都可能访问充电站；
- 线性/非线性、满充/部分充电策略；
- 客户时间窗；
- 卡车与无人机同步等待。

因此，GA 不能只搜索“客户顺序”。如果 GA 只随机生成客户顺序，再交给统一 repair 修改，那么算法本身并没有真正理解这个问题。后续改造的核心目标就是让 GA decoder 主动考虑约束。

当前 GA 的定位是：

```text
可行性优先的 Truck-Drone EVRPTW-NL 初始解构造器
```

它现在已经可以为 25/50 客户规模生成硬约束可行解，但车辆数和距离仍偏保守。后续更适合让 ALNS 或 GA+ALNS 在 GA 可行解基础上继续压缩车辆数、距离、等待和充电成本。

---

## 2. Stage 0：问题扩展前的 GA 基线

### 2.1 当时的问题

早期 GA 更接近普通路径启发式：

```text
customer_order = [c1, c2, c3, ...]
```

然后按照客户顺序构造路线。

这个阶段的问题是：

- 没有明确区分客户由卡车服务还是无人机服务；
- 无人机任务更像是“附加装饰”，不是 GA 主动搜索出来的结构；
- 时间窗、电量、同步主要依靠统一 evaluator 事后检查；
- 生成解后经常 `feasible=False`；
- 即使输出路线，也不能说明 GA 真正在处理 Truck-Drone EVRPTW-NL。

### 2.2 暴露出的核心矛盾

这个阶段的本质矛盾是：

```text
问题已经变成 Truck-Drone EVRPTW-NL
但 GA 仍然像普通 VRP 那样只搜索客户顺序
```

所以后续必须扩展染色体和 decoder。

---

## 3. Stage 1：扩展完整解结构与模拟器

### 3.1 修改动机

原始无人机任务结构接近：

```python
{"route_index": 0, "launch": i, "customer": k, "recover": j}
```

这只能表达：

```text
launch -> 单个客户 -> recover
```

但我们后来明确，未来研究的是更一般的无人机-卡车协同问题。无人机不应被人为限制为一次只服务一个客户，也不应被禁止访问充电站。

因此需要把无人机任务扩展为：

```python
{
    "route_index": 0,
    "launch": i,
    "drone_route": [i, k1, k2, station_s, k3, j],
    "recover": j,
    "customers": [k1, k2, k3]
}
```

### 3.2 主要修改

修改重点：

- `route_simulator.py` 支持多路线 `truck_routes`；
- 支持 `drone_route`；
- 支持无人机访问充电站；
- 支持无人机充电时间；
- 支持无人机多客户服务；
- 支持卡车与无人机在 recover 节点同步；
- `charging_plan` 增加 `vehicle = "truck" | "drone"`；
- `charging_plan` 增加 `route_index` 和 `task_index`。

### 3.3 解决的问题

这个阶段解决了“解结构表达能力不足”的问题。

以前完整解只能表达：

```text
卡车路线 + 单客户无人机任务
```

现在可以表达：

```text
多辆卡车路线
多客户无人机任务
卡车充电
无人机充电
同步等待
```

### 3.4 效果

手工构造测试中，无人机访问充电站可以被 simulator 正确识别：

```text
drone_route = [52, 76, 1000, 0]
charging_count = 1
charging_time = 12.625
```

这说明无人机充电已经进入状态传播，而不只是写在路线里。

### 3.5 局限

这个阶段只是让数据结构和 simulator 能表达复杂解，还没有让 GA 真正高效搜索这些结构。

---

## 4. Stage 2：扩展 GA 染色体

### 4.1 修改动机

如果 GA individual 仍然只有客户顺序：

```python
[42, 7, 49, 82, ...]
```

那么 GA 无法主动决定：

- 哪些客户适合卡车服务；
- 哪些客户适合无人机服务；
- 无人机客户之间谁更优先；
- 允许多少车辆；
- 采用哪种充电策略；
- 客户更倾向放入哪条卡车路线。

因此需要把 individual 从简单 list 扩展为结构化染色体。

### 4.2 当前染色体结构

当前 GA individual 采用：

```python
{
    "customer_order": [...],
    "service_mode": {customer_id: "truck" | "drone"},
    "drone_priority": {customer_id: float},
    "charging_policy": "LFC|LPC|NFC|NPC",
    "max_vehicle_count": int,
    "route_split_bias": {customer_id: int},
    "drone_charging_preference": "avoid" | "allow" | "prefer_if_needed"
}
```

各字段含义：

| 字段 | 作用 |
|---|---|
| `customer_order` | 决定客户大致处理顺序 |
| `service_mode` | 表示客户倾向由卡车还是无人机服务 |
| `drone_priority` | 无人机客户组合和排序的优先级 |
| `charging_policy` | 当前采用 LFC/LPC/NFC/NPC 中哪种充电策略 |
| `max_vehicle_count` | GA 允许最多尝试多少辆车 |
| `route_split_bias` | 客户更倾向分配到哪条路线 |
| `drone_charging_preference` | 无人机是否倾向使用充电站 |

### 4.3 解决的问题

这个阶段让 GA 从：

```text
只搜索客户顺序
```

变成：

```text
同时搜索客户顺序、服务方式、车辆分配倾向、无人机优先级和充电策略
```

### 4.4 效果

GA 开始能产生更真实的 truck-drone 解，而不是单纯卡车路线。

例如 R101-5 中出现：

```text
Task: 52 ---> 76 ---> 77 ---> 0
```

说明无人机可以连续服务多个客户。

### 4.5 局限

染色体扩展以后，搜索空间明显变大。如果不控制候选数量，25/50 客户会很慢。

---

## 5. Stage 3：多客户、多充电无人机 sortie decoder

### 5.1 修改动机

有了结构化染色体以后，还需要 decoder 把 individual 变成真实 solution。

旧 decoder 的问题是：

- 无人机任务选择过于固定；
- launch/recover 组合不够灵活；
- 无人机服务多个客户时缺少系统评价；
- 无人机充电没有进入任务构造；
- 不可行无人机任务缺少 fallback。

### 5.2 新 decoder 流程

当前 GA decoder 的核心流程是：

```text
individual
-> 构造多条 truck base routes
-> 对 truck-mode 客户做 TW/Energy/Charging-aware 插入
-> 收集 drone-mode 客户
-> 对每条 truck route 枚举 launch/recover 区间
-> 构造 drone_route
-> drone_route 可包含多个客户和充电站
-> 传播无人机时间、电量、服务和充电状态
-> 与卡车 recover 时间同步
-> 不可行或收益差的客户 fallback 为 truck
-> 每条卡车路线插入卡车充电计划
-> evaluator 严格检查完整解
```

### 5.3 解决的问题

这个阶段让无人机任务真正参与构造，而不是简单附加。

无人机任务可以表达：

```text
launch -> customer -> customer -> station -> customer -> recover
```

### 5.4 效果

R101-5 中 GA 可行，并出现多客户无人机任务。

代表结果：

```text
feasible = True
vehicle_count = 2
total_violation = 0
drone task = 52 ---> 76 ---> 77 ---> 0
```

### 5.5 遇到的新问题

Stage 3 暴露了严重运行时间问题：

```text
R101-25 + GA + NPC
300 秒内未完成
```

原因是：

```text
客户组组合
× launch/recover 组合
× 充电站插入
× evaluator 完整检查
```

组合数量太大。

---

## 6. Stage 4：无人机任务搜索的分层剪枝

### 6.1 修改动机

Stage 3 已经能表达复杂无人机任务，但太慢。要进入 25/50 客户规模，必须减少无意义候选。

注意：剪枝不是改变数学模型。

模型仍允许无人机服务多个客户、访问充电站。剪枝只是让 decoder 优先检查更可能有效的候选。

### 6.2 主要修改

新增控制参数：

```python
MAX_DRONE_CANDIDATES_PER_ROUTE = 6
MAX_DRONE_EXTENSION_ROUNDS = 3
MAX_LAUNCH_RECOVER_PAIRS = 10
```

新增函数：

```python
_rank_drone_candidate_pool()
_rank_launch_recover_pairs()
```

### 6.3 算法逻辑

无人机候选客户不再全部尝试，而是按以下因素排序：

```text
drone_priority
空间距离
due time
```

launch/recover 组合也不再全部尝试，而是优先选择与无人机客户组空间更匹配的组合。

### 6.4 效果

Stage 4 后：

```text
R101-25 不再 300 秒超时
可以在几十秒内完成
```

### 6.5 局限

剪枝可能丢掉某些潜在好解，所以后续必须用 mutation、crossover、多样性候选补回来。

---

## 7. Stage 5：评价缓存与轻量路线再平衡

### 7.1 修改动机

GA decoder 会大量调用 evaluator。很多 solution 是重复或接近重复的。如果每次都完整计算，会浪费时间。

同时，多路线插入时，客户可能过早进入不合适路线，导致时间窗压力集中。

### 7.2 主要修改

新增：

```python
_evaluate_cached()
_solution_cache_key()
_rebalance_routes()
```

修改：

```python
_insert_customer_into_best_route()
```

使其支持：

```python
route_split_bias
eval_cache
```

### 7.3 算法逻辑

缓存逻辑：

```text
如果完全相同 solution 已经评价过
-> 直接复用 evaluator 结果
否则
-> 调用 evaluator 并保存结果
```

路线再平衡逻辑：

```text
从客户较多或压力较大的路线中选择少量客户
尝试移动到其他路线
如果总评分改善则接受
尝试次数有限，避免运行时间失控
```

### 7.4 效果

Stage 5 后：

```text
R101-25 可以完成运行
首轮约 17 秒
```

但当时车辆上限偏小，仍有时间窗违反。

### 7.5 局限

`_rebalance_routes()` 是轻量移动，不是完整 ALNS 局部搜索。它不能充分执行 route merge、2-opt*、大范围 relocate。

---

## 8. Stage 6：Truck-Drone 专用 mutation

### 8.1 修改动机

普通 GA mutation 只交换客户顺序，对 Truck-Drone EVRPTW-NL 不够。

本问题中，一个好解不仅取决于客户顺序，还取决于：

- 客户由卡车还是无人机服务；
- 无人机客户的优先级；
- 客户分配到哪辆车；
- 采用哪种充电偏好；
- 最大允许车辆数。

### 8.2 主要修改

增强：

```python
mutate_individual()
```

新增 mutation 类型：

| mutation 类型 | 作用 |
|---|---|
| 客户顺序交换 | 改变访问顺序 |
| 客户顺序片段反转 | 改变局部路线结构 |
| `truck -> drone` | 尝试让无人机分担客户 |
| `drone -> truck` | 避免不合适无人机任务造成违反 |
| `drone_priority` 扰动 | 改变无人机客户组队倾向 |
| `route_split_bias` 扰动 | 改变客户路线分配倾向 |
| `drone_charging_preference` 切换 | 改变无人机充电倾向 |
| `max_vehicle_count` 小范围变化 | 调整可行性和车辆数 |

### 8.3 效果

mutation 能生成更多不同结构的候选解，尤其是：

- truck-heavy；
- drone-heavy；
- 不同路线分配；
- 不同无人机优先级。

### 8.4 局限

当前 mutation 仍是启发式扰动，不是针对失败节点的精确修复。

未来可以进一步做：

```text
time-window failed node targeted mutation
energy-critical mutation
sync-wait targeted mutation
charging-station relocation mutation
```

---

## 9. Stage 7：车辆数递增扩展与路线分裂策略

### 9.1 修改动机

R101 类实例时间窗很紧。即使：

```text
客户覆盖 = 100%
容量满足
电量满足
无人机同步满足
```

只要车辆数太少，仍会迟到。

所以必须允许 GA 在不可行时增加车辆数。

### 9.2 主要修改

修改：

```python
default_max_vehicle_count()
```

当前策略：

```python
return min(18, max(2, (customer_count + 2) // 3))
```

含义：

- 小规模至少 2 辆车；
- 车辆数随客户数增长；
- 50 客户最多允许到 18 辆；
- decoder 仍然从 1 辆车开始尝试；
- 找到可行解后停止继续增加车辆。

### 9.3 解决的问题

这个阶段解决了“为了减少车辆数导致时间窗不可行”的问题。

当前优先级变成：

```text
第一：约束违反为 0
第二：在可行解里减少车辆数
第三：减少距离、充电、等待和同步成本
```

### 9.4 效果

R101-25：

```text
feasible = True
vehicle_count = 8
total_violation = 0
runtime_seconds ≈ 54.7s
```

R101-50：

```text
feasible = True
vehicle_count = 16
total_violation = 0
runtime_seconds ≈ 260.4s
```

### 9.5 局限

车辆数明显偏多。

这说明当前 GA 更偏向：

```text
可行解构造
```

而不是：

```text
高质量最终优化
```

后续需要 ALNS 来压缩车辆数。

---

## 10. Stage 8：结构保留 crossover、多样性锚点与时间预算

### 10.1 修改动机

加入 TW 排序后，曾出现一个现象：

```text
TW 排序解距离更短、车辆更少
但反而丢掉原先可行的 service-mode 组合
```

这说明不能只依赖某一种排序或某一个 seed。

### 10.2 主要修改

新增：

```python
crossover_individual()
_mode_shifted_individual()
_deduplicate_individuals()
```

修改：

```python
candidate_individuals()
default_ga_orders()
solve_ga.py
```

### 10.3 Crossover 逻辑

`crossover_individual()` 的基本逻辑：

```text
从父代 A 保留一段客户顺序
再按照父代 B 的顺序补齐剩余客户
同时继承 service_mode、drone_priority、route_split_bias 和充电偏好
```

这比简单随机打乱更合理，因为它能保留已有优秀路线结构。

### 10.4 多样性候选

当前候选包括：

- 按 ready time / due time 排序；
- 按 due time / ready time 排序；
- 原始客户 id 顺序；
- 随机顺序；
- mutated 个体；
- truck-heavy 个体；
- drone-heavy 个体；
- crossover 个体；
- stable anchor 个体。

### 10.5 时间预算

`solve_ga.py` 增加默认预算：

| 客户数 | 默认时间预算 |
|---:|---:|
| 5 | 15s |
| 10 | 45s |
| 25 | 120s |
| 50 | 240s |
| 更大规模 | 360s |

说明：

实际运行可能略超过预算，因为预算是在候选之间检查的；如果某个候选正在 decode，中途不会强行终止。

### 10.6 效果

`debug_small.yaml` 批量回归：

```text
R101/C101/RC101
5/10 customers
LFC/LPC/NFC/NPC
GA 均返回可行解
Hybrid 当前继承 GA 可行解，也均返回可行解
```

R101-25 和 R101-50 均可行。

### 10.7 局限

50 客户仍然慢：

```text
R101-50 + GA + NPC ≈ 260s
```

这已经能用于阶段性实验，但不是高效最终算法。

---

## 11. 当前 GA 的完整求解流程

当前 GA 的整体流程可以理解为：

```text
读取实例
-> 生成多种 customer_order
-> 构造 structured individual
-> mutation / crossover / 多样性候选
-> 对每个 individual 执行 decoder
-> 从 1 辆车开始递增尝试
-> TW/Energy/Charging-aware truck insertion
-> 轻量 route rebalance
-> 选择 drone-mode 客户
-> 枚举并剪枝 launch/recover
-> 构造多客户 drone_route
-> 必要时插入无人机充电站
-> 不合适无人机任务 fallback 为 truck
-> 插入卡车充电站
-> evaluator 严格检查
-> 选择最优可行解或违反最小解
-> 输出 summary.csv / raw_results.jsonl / route figure
```

---

## 12. 当前 GA 处理的约束

| 约束 | 当前 GA 如何处理 |
|---|---|
| 客户唯一服务 | evaluator 严格检查；decoder 避免 truck/drone 重复服务 |
| 卡车起终点 | 每条 `truck_routes` 都从 0 出发并返回 0 |
| 多车辆 | `truck_routes` 支持多条路线，车辆数递增尝试 |
| 卡车容量 | evaluator 检查，truck insertion 通过评分间接考虑 |
| 时间窗 | truck insertion、drone task 构造、evaluator 均考虑 |
| 卡车电量 | 卡车路线中主动插入已有充电站 |
| 无人机电量 | drone_route 传播电量，必要时插入已有充电站 |
| 非线性充电 | 通过 LFC/LPC/NFC/NPC 策略计算充电时间 |
| 无人机多客户任务 | `drone_route` 支持多个客户 |
| 无人机充电 | `drone_route` 可包含 station，charging_plan 标记 `vehicle="drone"` |
| 同车发射回收 | `route_index` 限定同一条卡车路线 |
| 跨车回收 | 当前不允许 |
| 同步等待 | recover 节点计算 truck wait 与 drone wait |

---

## 13. 关键实验结果

### 13.1 R101-5 + GA + NPC

```text
feasible = True
vehicle_count = 2
total_violation = 0
runtime_seconds ≈ 0.165s
```

代表意义：

- 小规模下 GA 能快速构造可行解；
- 能出现无人机任务；
- 适合调试和诊断。

### 13.2 R101-25 + GA + NPC

```text
feasible = True
vehicle_count = 8
total_distance = 906.833
completion_time = 212.028
charging_count = 4
total_violation = 0
runtime_seconds ≈ 54.7s
```

代表意义：

- 25 客户已从超时不可用变为可行；
- 车辆数偏多；
- 可作为 ALNS 初始可行解。

### 13.3 R101-50 + GA + NPC

```text
feasible = True
vehicle_count = 16
total_distance = 1694.875
completion_time = 248.980
charging_count = 18
total_violation = 0
runtime_seconds ≈ 260.4s
```

代表意义：

- 50 客户也能得到硬约束可行解；
- 运行时间偏长；
- 车辆数明显保守；
- 说明 GA 已可支撑较大规模实验，但还不是最终优化器。

### 13.4 debug_small.yaml 批量结果

实验范围：

```text
R101/C101/RC101
5/10 customers
LFC/LPC/NFC/NPC
GA / ALNS / Hybrid
```

结果：

```text
GA：全部可行
Hybrid：当前继承 GA 可行解，全部可行
ALNS baseline：仍多为不可行
```

说明：

- GA 的可行解构造能力已经明显强于当前 ALNS baseline；
- 当前 Hybrid 的优势主要来自 GA；
- 后续重点应放在 ALNS 深度改造。

---

## 14. 当前 GA 的优点

### 14.1 可行性明显提升

相比早期版本，当前 GA 已经能稳定满足：

```text
客户覆盖
容量
时间窗
卡车电量
无人机电量
充电结构
卡车-无人机同步
```

在 R101-25 和 R101-50 中均实现：

```text
total_violation = 0
```

### 14.2 模型表达能力强

当前 GA 不再只是普通 VRP GA，而是能表达：

- 多车辆；
- 多客户无人机任务；
- 无人机访问充电站；
- 卡车访问充电站；
- 四类充电策略；
- 同步等待；
- 服务方式选择。

### 14.3 适合作为 Hybrid 初始解来源

当前 GA 能给 ALNS 提供一个可行初始解。

这很重要，因为 ALNS 如果从不可行解开始，需要大量 repair；如果从 GA 可行解开始，可以把搜索重点放在：

```text
减少车辆数
减少距离
减少等待
减少充电时间
优化无人机任务
```

### 14.4 输出统一

GA 输出仍然兼容项目统一格式：

- `summary.csv`
- `raw_results.jsonl`
- 路线图绘制；
- `run_single --diagnose` 逐节点诊断。

---

## 15. 当前 GA 的缺点

### 15.1 解偏保守

为了保证硬约束可行，GA 倾向于：

- 增加车辆数；
- 缩短每条路线；
- 插入较多充电站；
- 接受较高等待时间；
- 少做高风险无人机任务。

例如 R101-50 使用了 16 辆车，说明它更重视可行性，而不是成本最优。

### 15.2 运行时间仍偏长

R101-50 约 260 秒，已经能跑，但不够轻量。

主要耗时来自：

```text
多车辆尝试
多候选 individual
无人机任务构造
充电插入
完整 evaluator 检查
```

### 15.3 mutation 仍不够智能

当前 mutation 是结构化启发式扰动，但还没有做到：

- 专门针对迟到客户；
- 专门针对高等待任务；
- 专门针对高充电路线；
- 专门针对失败无人机任务。

### 15.4 不擅长压缩车辆数

GA 可以通过增加车辆数获得可行解，但不擅长把 16 辆车压回更少车辆。

这种工作更适合 ALNS 的：

- route removal；
- route merge；
- regret insertion；
- relocate；
- 2-opt*。

---

## 16. 当前 GA 适合扮演的角色

当前 GA 最适合扮演：

```text
可行初始解生成器
```

而不是：

```text
最终最优求解器
```

推荐分工：

| 方法 | 角色 |
|---|---|
| GA | 快速构造符合复杂约束的可行解 |
| ALNS | 在可行解基础上减少车辆数、距离、等待和充电成本 |
| GA+ALNS | 论文主方法候选：GA 提供全局结构，ALNS 做局部深度优化 |
| OR-Tools/PyVRP | truck-only baseline，不直接解决完整 Truck-Drone EVRPTW-NL |

---

## 17. 后续建议

GA 部分当前可以暂告一段落。

如果继续改 GA，收益可能低于改 ALNS。更推荐下一阶段转向：

```text
ALNS for Truck-Drone EVRPTW-NL
```

重点包括：

1. 使用 GA 可行解作为 ALNS initial state；
2. 实现 route removal；
3. 实现 route merge；
4. 实现 regret insertion；
5. 实现 time-window critical removal；
6. 实现 energy-aware insertion；
7. 实现 drone sortie re-optimization；
8. 实现 charging cleanup；
9. 统计各算子成功率；
10. 对比 GA、ALNS、GA+ALNS 在 25/50 客户下的车辆数、距离、充电、等待和运行时间。

最终论文中的方法主线可以表述为：

```text
GA 负责产生复杂约束下的可行协同配送结构；
ALNS 负责在该结构基础上进行破坏、修复和局部优化；
GA+ALNS 用于在可行性达标前提下提升路线质量。
```

---

## 18. 阶段性结论

从问题扩展至无人机卡车 EVRPTW-NL 以来，GA 经历了以下变化：

```text
普通客户顺序 GA
-> 结构化 service_mode chromosome
-> 多车辆 truck_routes
-> 多客户 drone_route
-> 无人机充电
-> 同步等待传播
-> 约束感知 decoder
-> 候选剪枝和缓存
-> 专用 mutation
-> 车辆递增扩展
-> route-preserving crossover
```

当前 GA 已经解决了最关键的工程问题：

```text
能在复杂 Truck-Drone EVRPTW-NL 约束下生成可行解
```

但还没有解决最终优化问题：

```text
如何用更少车辆、更短距离、更少等待和更少充电完成配送
```

因此，GA 当前的阶段性结论是：

```text
GA 已经达到“论文实验可用的可行初始解构造器”水平；
但若要达到“论文主算法的高质量优化器”水平，需要与 ALNS 深度结合。
```

