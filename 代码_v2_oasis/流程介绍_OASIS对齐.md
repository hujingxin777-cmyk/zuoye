# 流程介绍（OASIS 对齐版）

> 本文档描述当前项目从“配置加载 → 实验执行 → 结果统计 → 图表输出”的完整流程，并标注可对齐 OASIS 的关键节点。

---

## 1. 全流程总览

1. 读取配置与环境变量
2. 构建实验矩阵与 Agent 状态
3. 按场景/条件/氛围进入执行循环
4. 生成 prompt，调用 LLM，解析并编码
5. 写入记录并更新动态状态
6. 输出统计摘要与可视化图表

入口文件：
- `main.py`（run / visualize / stats）

---

## 2. 启动阶段（Initialization）

## 2.1 参数与配置加载
- `main.py` 解析 CLI 参数
- `env_utils.py` 加载 `.env`
- `config.py` 读取 `experiment_config.yaml`
- 若设置 `active_plan`，应用方案覆盖

输出：`ExperimentConfig`

## 2.2 运行器初始化
- 创建 `ExperimentRunner`
- 初始化：
  - `ExperimentMatrix`（实验单元矩阵）
  - `DecisionEncoder`
  - `LLMResponseParser`
  - `ExperimentResultWriter`
  - `ExperimentLogger`

---

## 3. 实验执行阶段（Run Loop）

## 3.1 外层循环
- 场景循环：`for scenario in config.scenarios`
- 条件循环：`P1 / P2 / P3`
- 氛围循环：
  - P1 固定 `none`
  - P2/P3 使用三档氛围

## 3.2 P1/P2 执行逻辑（静态）
- 调用 `_run_parallel_condition`
- 每个 Agent 单步决策（`timestep=1`）
- 无动态线程演化

## 3.3 P3 执行逻辑（动态）
- 调用 `_run_interactive_condition`
- 时间步推进：`t=1..T`
- 每步动作：
  - 分层激活 Agent（按人格桶）
  - prompt 中注入“当前氛围 + 最近线程增量”
  - 并发调用 LLM

关键机制：
- 动作归一化（兼容 OASIS 风格动作名）
- 回复冷却（防 A↔B 连续互回）
- 动作多样化约束（避免单一动作连续重复）

---

## 4. 单 Agent 处理阶段（Per-Agent）

函数：`_process_single_agent`

步骤：
1. 构造 system + user prompt
2. 调用 `LLMClient.call`
3. 解析 JSON（失败回退默认中立）
4. 编码指标（NCI/SCM/PES...）
5. 更新 Agent 状态（当前 NCI）
6. 组装 `ExperimentRecord`
7. 写入结果（或在 P3 汇总后写入）

P3 扩展字段：
- `planned_action`
- `reply_target`
- `group_consensus_perception`
- `public_comment` / `private_reason`

---

## 5. 群体状态更新与停止条件（P3）

每个时间步完成后：
- 计算群体指标：
  - `GCR`（共识比例）
  - `SSA`（信号不对称）
- 更新事件级字段：
  - `p3_event_id`
  - `p3_participants_set`
  - `p3_copresence_size`

停止条件：
1. 达到 `max_timestep`
2. `GCR >= threshold` 且连续保持 N 步
3. 新增互动事件连续停滞 N 步

---

## 6. 输出与后处理

## 6.1 数据输出
- `outputs/results.jsonl`
- `outputs/results.csv`

## 6.2 统计输出
- `main.py --stats`
- 条件/人格/场景汇总
- 高阶机制汇总（CMT/ASI/HO Event）

## 6.3 图表输出
- `main.py --visualize`（常规图）
- `paper_figures.py`（论文图）

---

## 7. 与 OASIS 对齐的流程映射

1. OASIS 的“动作驱动” → 本项目 P3 的 `planned_action` 事件流
2. OASIS 的“时间步环境刷新” → 本项目每步注入“最近线程增量”
3. OASIS 的“动作合法性约束” → 本项目动作归一化与回复冷却
4. OASIS 的“trace 可追踪” → 本项目事件字段 + 结构化记录

---

## 8. 建议新增的流程化诊断

建议新增 `--diagnose` 模式，自动输出：
- 连续互回率（pair reciprocity）
- 单一动作连续率
- 每步新增事件数曲线
- 停止原因占比（共识/停滞/时长）

这样能把“逻辑正确”从主观判断变成可量化验收。

---

## 9. 一句话总结

当前流程已经从“静态问答实验”升级为“时间步驱动的多 Agent 互动实验”；后续重点应放在事件级诊断可视化与网络结构解释。