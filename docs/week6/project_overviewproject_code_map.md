# 1. Project Overview

这个项目主要用于研究和复现车辆路径问题 VRP 及其扩展问题，当前重点是 E-VRPTW，也就是带时间窗和充电站的电动车路径问题。项目中已经包含 OR-Tools、GA、PyVRP、POMO、ALNS，以及 GA+ALNS 混合方法等多种求解思路。数据主要来自 Solomon 数据集，项目会先把 Solomon 数据改造成 E-VRPTW 实例，再交给不同算法求解。不同算法求出的路线会统一交给 evaluator 检查可行性，并统一输出车辆数、距离、时间窗违反、电量违反、运行时间等指标。

当前最重要的复现模块是 `EVRPTW_Schneider2014`。这个模块中，`data_loader.py` 负责读取 Solomon 原始数据，`instance_builder.py` 负责生成 E-VRPTW 实例，`evaluator.py` 负责检查最终路线是否可行，`route_repair.py` 负责把普通客户路线修复成更符合电量和时间窗约束的路线。`solvers/` 目录中是 OR-Tools、GA、PyVRP、POMO、ALNS 的基础求解入口。`algorithms/hybrid_ga_alns/` 目录是后来新增的 GA+ALNS 混合算法实验模块。

如果你是零基础读者，不建议一开始阅读所有文件。应该先理解“数据怎么变成实例”“路线怎么表示”“路线怎么被评价”，再去看具体算法。也就是说，先看公共模块，再看算法模块，最后看实验脚本和输出文件。

# 2. Directory Map

下面只列出主要文件，不机械列出全部缓存、结果和自动生成文件。

## 2.1 算法核心

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/solvers/solve_ortools.py` | OR-Tools 基础求解器入口，构建 OR-Tools 路由模型并输出路线 | 是 | `run_single.py`, `run_experiments.py` | 是，适合了解 OR-Tools 如何接入项目 |
| `EVRPTW_Schneider2014/solvers/solve_ga.py` | 基础 GA 求解器，使用客户排列、选择、交叉、变异生成路线 | 是 | `run_single.py`, `run_experiments.py` | 是，但建议先看 evaluator |
| `EVRPTW_Schneider2014/solvers/solve_pyvrp.py` | PyVRP 基础求解器，把实例转成 PyVRP 可处理的模型 | 是 | `run_single.py`, `run_experiments.py` | 中等，依赖 PyVRP 用法 |
| `EVRPTW_Schneider2014/solvers/solve_alns.py` | 基础 ALNS 求解器，包含 `EVRPTWState`、destroy、repair 算子 | 是 | `run_single.py`, `run_experiments.py`, `hybrid_solver.py` | 是，理解 ALNS 的重点文件 |
| `EVRPTW_Schneider2014/solvers/solve_pomo.py` | POMO 接入入口，通过子进程调用 POMO 环境 | 半核心 | `run_single.py`, `run_experiments.py` | 暂时不优先，POMO 改造成本高 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/hybrid_solver.py` | GA+ALNS 混合方法核心，包含 Basic GA、Basic ALNS、post-processing、periodic、stagnation 模式 | 是 | `run_experiment.py`, `run_unified_benchmark.py` | 是，但建议在读完基础 GA 和 ALNS 后再读 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/enhanced_destroy.py` | 增强 ALNS destroy 算子，例如 time-window critical removal、energy critical removal | 是 | `hybrid_solver.py` | 中等，适合在理解 ALNS 后阅读 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/enhanced_repair.py` | 增强 ALNS repair 算子，例如 greedy insertion、regret insertion、energy-aware insertion | 是 | `hybrid_solver.py` | 中等，较复杂 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/local_search.py` | 局部搜索算子，例如 2-opt、relocate、swap、route merge | 是 | `hybrid_solver.py` | 中等，适合后读 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/candidate_selection.py` | 从 GA 种群中选择结构不同的 Top-K 候选解 | 是 | `hybrid_solver.py` | 中等 |
| `ETRD_NL/ga_model.py` | 早期 ETRD-NL 复现中的 GA 模型 | 是，但属于旧模块 | `ETRD_NL/run_ga.py`, `ETRD_NL/run_experiments.py` | 可以后读 |
| `ETRD_NL/ortools_model.py` | 早期 ETRD-NL 复现中的 OR-Tools 模型 | 是，但属于旧模块 | `ETRD_NL/run_ortools.py`, `ETRD_NL/run_experiments.py` | 可以后读 |

## 2.2 数据与实例

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `datasets/solomon/json/` | Solomon JSON 数据集，当前 E-VRPTW 复现主要从这里读取数据 | 是，数据源 | `data_loader.py` | 不需要逐个读文件 |
| `EVRPTW_Schneider2014/data_loader.py` | 读取 Solomon JSON，提取 depot 和 customers | 是 | `instance_builder.py` | 是，建议优先阅读 |
| `EVRPTW_Schneider2014/instance_builder.py` | 把 Solomon 数据改造成 E-VRPTW 实例，生成充电站、电池容量、距离矩阵 | 是 | `run_single.py`, `run_experiments.py`, hybrid benchmark | 是，重点阅读 |
| `EVRPTW_Schneider2014/generated_instances/` | 保存已经生成的 E-VRPTW 实例 JSON | 不是算法核心 | 运行脚本读取或保存 | 可以暂时忽略 |
| `ETRD_NL/data_loader.py` | ETRD-NL 模块的数据读取器 | 是，但属于旧模块 | `ETRD_NL/instance_builder.py` | 后续研究 ETRD-NL 时再读 |
| `ETRD_NL/instance_builder.py` | ETRD-NL 模块的实例构造器 | 是，但属于旧模块 | `ETRD_NL/run_*.py` | 后读 |

## 2.3 可行性检查

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/evaluator.py` | 统一检查路线是否满足客户覆盖、容量、时间窗、电量等约束 | 是 | 所有 solver、repair、hybrid 模块 | 是，最重要文件之一 |
| `EVRPTW_Schneider2014/route_repair.py` | 内部调用 `evaluate_solution()` 判断修复后路线是否可行 | 是 | 所有 solver 间接使用 | 是 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/solution_adapter.py` | 调用统一 evaluator 计算扩展指标，例如 total_cost、charging_time、waiting_time | 是 | `hybrid_solver.py`, `local_search.py`, diagnostics | 是 |
| `ETRD_NL/evaluator.py` | ETRD-NL 早期模块的方案评价器，包含卡车-机器人协同评价逻辑 | 是，但属于旧模块 | `ETRD_NL/ga_model.py`, `ETRD_NL/ortools_model.py` | 后续研究协同时再读 |

## 2.4 成本评估

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/evaluator.py` | 输出基础评价结果：distance、vehicle_count、feasible、violations | 是 | 所有算法 | 是 |
| `EVRPTW_Schneider2014/route_repair.py` | `priority_objective()` 定义可行性优先的目标函数 | 是 | GA、ALNS、hybrid | 是 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/solution_adapter.py` | `solution_metrics()` 计算 total_cost、charging_count、charging_time、waiting_time | 是 | hybrid GA+ALNS | 是 |
| `EVRPTW_Schneider2014/result_schema.py` | 定义统一结果对象 `SolutionResult` 和 `make_result()` | 是 | 所有 solver | 是，文件短，建议读 |

## 2.5 修复与后处理

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/route_repair.py` | 把客户路线修复为更可行的 E-VRPTW 路线，包括容量拆分、充电站插入、路线合并、时间窗修复 | 是 | GA、ALNS、OR-Tools、PyVRP、POMO、hybrid | 是，重点文件 |
| `EVRPTW_Schneider2014/solvers/common.py` | 提供容量拆分、最近邻路线等基础工具 | 是 | 多个 solver | 是 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/enhanced_repair.py` | GA+ALNS 增强修复器，处理贪心插入、后悔值插入、电量修复、充电站清理 | 是 | `hybrid_solver.py` | 后读 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/local_search.py` | ALNS repair 后的局部搜索和路线合并 | 是 | `hybrid_solver.py` | 后读 |
| `ETRD_NL/charging.py` | 早期 ETRD-NL 中的线性/非线性充电函数 | 是，但属于旧模块 | `ETRD_NL/evaluator.py` | 研究 EVRPTW-NL 时值得读 |

## 2.6 可视化

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/visualization.py` | 使用 matplotlib 绘制路线图，区分 depot、customers、stations 和 routes | 辅助核心 | `run_single.py`, `run_experiments.py` | 可以读，较直观 |
| `ETRD_NL/visualization.py` | ETRD-NL 模块的路线绘图工具 | 辅助核心 | `ETRD_NL/run_*.py` | 后读 |
| `EVRPTW_Schneider2014/figures/` | 已生成路线图 PNG | 不是代码 | 报告引用 | 不需要读代码 |
| `EVRPTW_Schneider2014/results/unified_benchmark_smoke/*.png` | 统一实验生成的收敛曲线、成本图、车辆数图、运行时间图 | 不是代码 | 报告引用 | 不需要读 |

## 2.7 实验运行

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/run_single.py` | 单次运行入口，可指定 instance、customers、method，并可画图 | 是，运行入口 | 用户命令行调用 | 是，建议第一个看 |
| `EVRPTW_Schneider2014/run_experiments.py` | 批量运行 OR-Tools、GA、PyVRP、POMO、ALNS 等基础方法 | 是，运行入口 | 用户命令行调用 | 是 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/run_experiment.py` | 专门比较 Basic GA、Basic ALNS、GA+ALNS 的单实例实验脚本 | 是，实验入口 | 用户命令行调用 | 是，在理解基础模块后读 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/run_unified_benchmark.py` | 统一 benchmark 框架，比较 7 类 GA/ALNS/GA+ALNS 方法并输出表格和图 | 是，实验入口 | 用户命令行调用 | 后读，文件较长 |
| `ETRD_NL/run_ga.py` | 运行 ETRD-NL GA 方法 | 是，旧模块入口 | 用户命令行调用 | 后读 |
| `ETRD_NL/run_ortools.py` | 运行 ETRD-NL OR-Tools 方法 | 是，旧模块入口 | 用户命令行调用 | 后读 |
| `ETRD_NL/run_experiments.py` | 批量运行 ETRD-NL 早期实验 | 是，旧模块入口 | 用户命令行调用 | 后读 |

## 2.8 配置

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/config.py` | 读取简化 YAML 配置、解析路径、处理命令行覆盖 | 是 | 所有运行脚本 | 是，文件较短 |
| `EVRPTW_Schneider2014/configs/debug_small.yaml` | 小规模调试配置 | 配置文件 | `run_single.py`, `run_experiments.py` | 是 |
| `EVRPTW_Schneider2014/configs/paper_small36.yaml` | 更接近论文小规模实验的配置 | 配置文件 | `run_experiments.py` | 后读 |
| `EVRPTW_Schneider2014/configs/solomon_56.yaml` | Solomon 56 组扩展实验配置 | 配置文件 | `run_experiments.py` | 后读 |
| `EVRPTW_Schneider2014/configs/custom.yaml` | 自定义实验配置 | 配置文件 | 用户修改 | 是 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/config.py` | GA+ALNS 混合算法默认参数 | 是，配置核心 | `hybrid_solver.py`, `run_experiment.py`, benchmark | 是 |

## 2.9 输出结果

| 文件路径 | 主要作用 | 是否核心代码 | 被哪些模块调用 | 是否适合初学者优先阅读 |
|---|---|---:|---|---:|
| `EVRPTW_Schneider2014/results/summary.csv` | 基础批量实验汇总表 | 否 | 报告分析 | 可以用 Excel 看 |
| `EVRPTW_Schneider2014/results/raw_results.jsonl` | 基础批量实验原始结果 | 否 | 报告分析 | 暂时不优先 |
| `EVRPTW_Schneider2014/results/hybrid_ga_alns_summary.csv` | GA+ALNS 单次实验汇总 | 否 | 报告分析 | 可以看 |
| `EVRPTW_Schneider2014/results/diagnostics/` | GA、ALNS、算子、触发记录等诊断 CSV | 否 | 报告分析 | 做算法分析时再看 |
| `EVRPTW_Schneider2014/results/unified_benchmark_smoke/` | 统一实验 smoke test 输出，包括 CSV、Markdown、PNG | 否 | 报告分析 | 可以看结果，不是代码 |
| `ETRD_NL/results/` | ETRD-NL 早期实验输出 | 否 | 报告分析 | 暂时不优先 |

## 2.10 可以暂时忽略的文件

| 文件或目录 | 原因 |
|---|---|
| `__pycache__/` | Python 自动生成缓存，不需要阅读 |
| `.venv/` | Python 虚拟环境，包含第三方库，不是项目代码 |
| `generated_instances/` | 自动生成的数据实例 JSON，除非你要检查具体数据 |
| `results/` | 实验输出，不是算法代码 |
| `figures/` | 图片输出，不是算法代码 |
| `*.png` | 可视化结果，不是源码 |
| `*.csv` | 实验表格，不是源码 |
| `*.jsonl` | 原始实验日志，不是源码 |
| `algorithms/POMO/POMO/` | 克隆的 POMO 原始仓库，除非专门研究 POMO，否则先不读 |
| `algorithms/GA/py-ga-VRPTW/` | 原始 GA 仓库，可作为参考，但当前 E-VRPTW 主逻辑不应从这里开始读 |
| `algorithms/ortools/` | OR-Tools 示例目录，可参考，但主复现入口在 `EVRPTW_Schneider2014/solvers/solve_ortools.py` |

# 3. Recommended Reading Order

建议阅读顺序如下：

```text
run_single.py
-> config.py
-> data_loader.py
-> instance_builder.py
-> result_schema.py
-> evaluator.py
-> route_repair.py
-> solvers/common.py
-> solvers/solve_ga.py
-> solvers/solve_alns.py
-> solvers/solve_ortools.py
-> solvers/solve_pyvrp.py
-> visualization.py
-> run_experiments.py
-> algorithms/hybrid_ga_alns/solution_adapter.py
-> algorithms/hybrid_ga_alns/hybrid_solver.py
-> algorithms/hybrid_ga_alns/enhanced_destroy.py
-> algorithms/hybrid_ga_alns/enhanced_repair.py
-> algorithms/hybrid_ga_alns/local_search.py
-> algorithms/hybrid_ga_alns/run_unified_benchmark.py
```

这样排序的原因是：初学者最先需要知道“程序从哪里开始运行”，所以先看 `run_single.py`。然后理解配置如何读取、Solomon 数据如何加载、实例如何生成。接着看 `result_schema.py` 和 `evaluator.py`，因为所有算法最终都要输出统一结果并接受统一评价。然后看 `route_repair.py`，理解为什么普通路线还需要修复。最后再看 GA、ALNS、OR-Tools、PyVRP 等具体算法。

不要一开始就读 `hybrid_solver.py` 或 `enhanced_repair.py`。这些文件依赖前面的数据结构、评价函数和修复器，如果直接读会很难理解。

# 4. Shared Modules

下面这些模块是多个算法共同使用的公共基础。

| 共享模块 | 输入 | 输出 | 用途 | 主要调用者 |
|---|---|---|---|---|
| `EVRPTW_Schneider2014/data_loader.py` | Solomon JSON 路径、实例名 | depot、customers 原始信息 | 读取基础数据 | `instance_builder.py` |
| `EVRPTW_Schneider2014/instance_builder.py` | 配置、实例名、客户数量 | 统一 `instance` 字典 | 生成 E-VRPTW 实例，包括客户、充电站、电池参数、距离矩阵 | `run_single.py`, `run_experiments.py`, hybrid benchmark |
| `EVRPTW_Schneider2014/evaluator.py` | `instance`, `routes` | `feasible`, `distance`, `vehicle_count`, `violations` | 判断路线是否满足容量、时间窗、电量、客户覆盖 | 所有 solver、repair、hybrid |
| `EVRPTW_Schneider2014/route_repair.py` | `instance`, 客户路线或普通 routes | 修复后的 routes、priority objective | 插入充电站、拆分容量、合并路线、改善时间可行性 | GA、ALNS、OR-Tools、PyVRP、POMO、hybrid |
| `EVRPTW_Schneider2014/result_schema.py` | instance、method、routes、runtime、metrics | 统一结果字典 | 让不同算法输出统一格式 | 所有 solver |
| `EVRPTW_Schneider2014/visualization.py` | `instance`, `result` | PNG 或 matplotlib 窗口 | 绘制路线图 | `run_single.py`, `run_experiments.py` |
| `EVRPTW_Schneider2014/solvers/common.py` | instance、客户顺序 | 容量拆分路线、最近邻路线 | 多个求解器共用的小工具 | GA、ALNS、POMO 等 |
| `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/solution_adapter.py` | GA individual、routes、ALNS state | 相互转换后的结构、扩展指标 | 连接 GA 和 ALNS | `hybrid_solver.py`, `local_search.py` |

可以把项目理解成下面的流程：

```text
Solomon JSON
-> data_loader.py
-> instance_builder.py
-> solver
-> route_repair.py
-> evaluator.py
-> result_schema.py
-> CSV / JSONL / PNG
```

# 5. Algorithm Entry Points

## 5.1 OR-Tools

| 项目 | 内容 |
|---|---|
| 文件路径 | `EVRPTW_Schneider2014/solvers/solve_ortools.py` |
| 入口函数 | `solve(instance: dict, time_limit_seconds: int = 5) -> dict` |
| 调用方式 | `run_single.py` 或 `run_experiments.py` 根据 `--method ortools` 调用 |
| 输出 | 统一 `SolutionResult` 字典 |
| 备注 | OR-Tools 主要负责生成 VRPTW/VRP 风格路线，电量和充电可行性依赖统一 evaluator 和 repair 检查 |

## 5.2 GA

| 项目 | 内容 |
|---|---|
| 文件路径 | `EVRPTW_Schneider2014/solvers/solve_ga.py` |
| 入口函数 | `solve(instance: dict, population_size: int = 80, generations: int = 120, seed: int = 64) -> dict` |
| 关键函数 | `_mate()`, `_mutate()` |
| 调用方式 | `run_single.py` 或 `run_experiments.py` 根据 `--method ga` 调用 |
| 输出 | 统一 `SolutionResult` 字典 |
| 备注 | GA individual 是客户排列，解码后交给 `route_repair.py` 修复 |

## 5.3 PyVRP

| 项目 | 内容 |
|---|---|
| 文件路径 | `EVRPTW_Schneider2014/solvers/solve_pyvrp.py` |
| 入口函数 | `solve(instance: dict, time_limit_seconds: int = 5, seed: int = 64) -> dict` |
| 内部函数 | `_solve_pyvrp(instance, time_limit_seconds, seed)` |
| 调用方式 | `run_single.py` 或 `run_experiments.py` 根据 `--method pyvrp` 调用 |
| 输出 | 统一 `SolutionResult` 字典 |
| 备注 | PyVRP 适合生成强 VRPTW 基础路线，复杂电量和充电仍由本项目统一检查 |

## 5.4 ALNS

| 项目 | 内容 |
|---|---|
| 文件路径 | `EVRPTW_Schneider2014/solvers/solve_alns.py` |
| 入口函数 | `solve(instance: dict, iterations: int = 60, seed: int = 64) -> dict` |
| 状态类 | `EVRPTWState` |
| destroy 函数 | `_random_removal()`, `_worst_distance_removal()`, `_route_segment_removal()` |
| repair 函数 | `_greedy_repair()`, `_regret_repair()` |
| 调用方式 | `run_single.py` 或 `run_experiments.py` 根据 `--method alns` 调用 |
| 输出 | 统一 `SolutionResult` 字典 |

## 5.5 GA+ALNS

| 项目 | 内容 |
|---|---|
| 文件路径 | `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/hybrid_solver.py` |
| 主入口函数 | `solve(instance: dict[str, Any], **kwargs: Any) -> dict[str, Any]` |
| Basic GA 入口 | `solve_basic_ga(instance, **kwargs)` |
| Basic ALNS 入口 | `solve_basic_alns(instance, **kwargs)` |
| GA 内部搜索 | `_run_ga_search()` |
| ALNS 内部搜索 | `_run_alns_from_routes()` |
| 候选解选择 | `_select_candidates()` |
| Periodic/Stagnation 触发 | `_should_trigger_embedded_alns()`, `_run_embedded_alns_improvement()` |
| 单次实验脚本 | `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/run_experiment.py`, `main()` |
| 统一 benchmark 脚本 | `EVRPTW_Schneider2014/algorithms/hybrid_ga_alns/run_unified_benchmark.py`, `main()` |
| 输出 | hybrid summary、diagnostics、benchmark CSV、PNG 图 |

## 5.6 POMO

| 项目 | 内容 |
|---|---|
| 文件路径 | `EVRPTW_Schneider2014/solvers/solve_pomo.py` |
| 入口函数 | `solve(instance: dict, conda_env: str = "pomo_env", timeout_seconds: int = 120) -> dict` |
| 子进程脚本 | `EVRPTW_Schneider2014/solvers/pomo_infer.py`, `main()` |
| 调用方式 | `run_single.py` 或 `run_experiments.py` 根据 `--method pomo` 调用 |
| 备注 | POMO 当前更像 CVRP/TSP 学习模型 baseline，不是严格 E-VRPTW 主算法 |

# 6. Files That Can Be Ignored Temporarily

为了避免浪费时间，下面这些文件或目录可以暂时不看。

## 6.1 缓存

| 文件或目录 | 为什么可以忽略 |
|---|---|
| `__pycache__/` | Python 自动生成的字节码缓存 |
| `.pytest_cache/` 如果存在 | 测试工具缓存 |

## 6.2 日志与结果

| 文件或目录 | 为什么可以忽略 |
|---|---|
| `EVRPTW_Schneider2014/results/*.csv` | 实验结果表，不是算法源码 |
| `EVRPTW_Schneider2014/results/*.jsonl` | 原始运行记录，内容长，初学阶段不必读 |
| `EVRPTW_Schneider2014/results/diagnostics/` | 诊断日志，做算法分析时再读 |
| `ETRD_NL/results/` | ETRD-NL 旧实验结果 |

## 6.3 图片

| 文件或目录 | 为什么可以忽略 |
|---|---|
| `EVRPTW_Schneider2014/figures/` | 路线图输出，不是源码 |
| `EVRPTW_Schneider2014/results/**/*.png` | benchmark 自动生成的对比图 |

## 6.4 自动生成数据

| 文件或目录 | 为什么可以忽略 |
|---|---|
| `EVRPTW_Schneider2014/generated_instances/` | 由 `instance_builder.py` 生成的实例文件，不是算法逻辑 |
| `datasets/solomon/json_customize/` | 自定义数据副本或实验数据，除非你明确要比较 |
| `datasets/solomon/text_customize/` | 自定义文本数据，初学阶段不必读 |

## 6.5 环境和第三方仓库

| 文件或目录 | 为什么可以忽略 |
|---|---|
| `.venv/` | 虚拟环境，里面是安装的第三方包 |
| `algorithms/POMO/POMO/` | POMO 官方仓库源码，当前不是主复现逻辑 |
| `algorithms/GA/py-ga-VRPTW/` | 原始 GA 仓库源码，当前项目只是借鉴或调用其中思想 |
| `algorithms/PyVRP/` | PyVRP 相关外部资料或仓库，主入口在 `solve_pyvrp.py` |
| `algorithms/ortools/` | OR-Tools 示例，主入口在 `solve_ortools.py` |

## 6.6 测试和 smoke 脚本

| 文件 | 为什么可以暂时忽略 |
|---|---|
| `verify_minimal.py` | 只用于确认模块能运行 |
| `verify_hybrid_modes.py` | 只用于确认 GA+ALNS 三种模式能运行 |
| `verify_destroy_operators.py` | 只用于测试 destroy 算子 |
| `verify_repair_operators.py` | 只用于测试 repair 算子 |
| `verify_local_search.py` | 只用于测试 local search |

这些测试文件不是无用文件，但初学阅读主流程时可以先跳过。等你理解主算法后，再用它们验证某个模块是否正常。

