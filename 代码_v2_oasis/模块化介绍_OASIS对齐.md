# 模块化介绍（OASIS 对齐版）

> 目标：在现有 `代码_v2_oasis` 基础上，吸收 CAMEL/OASIS 与 MultiAgent4Collusion 的工程优点，形成可扩展、可诊断、可复现实验架构。

---

## 1. 顶层模块分层

## A. 配置与环境层
- `experiment_core/config.py`
- `experiment_core/env_utils.py`
- `experiment_config.yaml`

职责：
- 统一管理实验参数（平台、氛围、并发、停止条件）
- 读取 API 环境变量
- 支持 `active_plan` 方案切换（pilot/formal/custom）

对齐 OASIS 的价值：
- 配置驱动（而非硬编码）
- 动作空间、时间步、激活概率可外部化

---

## B. 数据模型层（Schema）
- `experiment_core/schemas.py`

职责：
- 定义输入输出的数据契约（`DecisionResponse`、`ExperimentRecord` 等）
- 定义 P3 动作字段（`planned_action`、`reply_target`、`group_consensus_perception`）
- 定义高阶事件字段（`p3_event_id`、`p3_participants_set`、`p3_copresence_size`）

对齐 OASIS 的价值：
- “动作是原子事件”的可追踪范式
- 结构化日志可直接用于可视化与回放

---

## C. Agent 建模层
- `experiment_core/modeling.py`

职责：
- 生成实验矩阵（场景×条件×人格×氛围×重复）
- 初始化 Agent 状态
- 构建 P3 群组（人格比例约束）

借鉴 MultiAgent4Collusion 的点：
- 多 Agent 激活与群组组织可参数化
- 为后续网络拓扑扩展预留空间（随机、cluster、hub）

---

## D. 提示词与行为约束层
- `experiment_core/prompts.py`

职责：
- 按 P1/P2/P3 构造 prompt
- 注入氛围操纵（`none/positive_leaning/negative_leaning`）
- 在 P3 约束动作多样性，减少“互相来回回复”

对齐 OASIS 的价值：
- 明确动作空间（类似 ActionType）
- 避免“只做一种动作”的退化策略

---

## E. 执行编排层（核心）
- `experiment_core/runner.py`

职责：
- 并行执行 P1/P2
- 时间步执行 P3（激活采样、超时控制、停止条件）
- 更新动态线程增量与动作冷却
- 写入结构化记录

本项目关键增强：
- 回复冷却（同对 Agent 在窗口内避免连续互回）
- 动作归一化（兼容 OASIS 风格动作名）
- 真实动作事件驱动停滞判定

---

## F. 解析与编码层
- `experiment_core/coding.py`

职责：
- 解析 LLM JSON 输出
- 将四维选择编码为指标（NCI/SCM/PES 等）

对齐 OASIS 的价值：
- 统一“行为 → 指标”的转换管道
- 错误回退策略明确（默认中立）

---

## G. I/O 与统计层
- `experiment_core/io_utils.py`

职责：
- 结果写入（JSONL/CSV）
- 汇总统计（条件、人格、场景、高阶机制）

价值：
- 支持论文主表与机制补充表的自动导出

---

## H. 可视化层
- `experiment_core/visualize.py`
- `paper_figures.py`

职责：
- 论文图（平台效应、人格异质性、氛围效应）
- 缺失图诊断

建议吸收 OASIS/MultiAgent4Collusion 的方向：
- 增加“事件级动作可视化”（动作堆叠、时间线）
- 增加“网络可视化”（回复网络、互回环比例）

---

## I. 部署与对齐层
- `main.py --mode oasis`

职责：
- 提供 OASIS 原生环境运行入口（严格部署模式）

价值：
- 可与本地 runner 结果做“同题双引擎对照”
- 提高方法学外部可信度

---

## 2. 模块边界与依赖原则

推荐依赖方向：
- `config/schemas` → 被所有层依赖
- `prompts/coding` ← 由 `runner` 调用
- `io_utils/visualize` ← 只消费结果，不反向影响执行

避免：
- 在可视化层写业务逻辑
- 在 schema 层写复杂流程控制
- 在 runner 中硬编码论文口径

---

## 3. 后续可扩展模块（建议）

1. `experiment_core/action_policy.py`
- 统一动作约束（冷却、去重、合法性）

2. `experiment_core/thread_state.py`
- 统一线程状态（可见窗口、事件缓存、回放）

3. `experiment_core/network_metrics.py`
- 回复网络指标（互惠率、集中度、连通性）

4. `experiment_core/diagnostics.py`
- 专门输出“逻辑健康报告”（互回率、单一动作率、停滞分解）

---

## 4. 一句话总结

当前架构已具备“可复现实验引擎”能力；继续沿 OASIS 的事件化动作与 MultiAgent4Collusion 的多 Agent 组织逻辑推进，可升级为“可解释的社交动力系统实验平台”。
