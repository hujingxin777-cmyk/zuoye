# LLM-Agent 负面信息选择实验框架（v2.0 OASIS版本）

## 项目概述

本项目研究在不同社交互动条件下（P1/P2/P3），不同个性的LLM-Agent对负面信息的选择偏好，基于OASIS框架改进。

### 核心研究问题

1. **H1**: 在缺乏社交信号的情况下(P1)，Agent是否存在个体认知偏向？
2. **H2**: 低强度社交反馈(P2)是否会增强Agent的负面信息偏向？
3. **H3**: 高互动讨论(P3)是否会产生非线性的放大效应？

## 框架设计

### 三层实验平台

| 平台 | 代码名 | 特点 | 描述 |
|------|--------|------|------|
| **P1** | independent | 独立决策 | 无任何社交信号，仅基于内容和个性做决策 |
| **P2** | low_feedback | 低反馈 | 可见少量静态评论与热度线索（无回复链）但不可互动 |
| **P3** | high_interaction | 高互动 | 多Agent实时讨论，产生动态社交信号 |

### 氛围（atmosphere）设置

- `none`：中性基线（无明显倾向）
- `positive_leaning`：偏正向氛围
- `negative_leaning`：偏负向氛围

呈现方式：
- P2：通过少量静态评论快照（含热度线索、无回复链）呈现三档氛围；
- P3：通过动态讨论线程呈现三档氛围，并观察共识随时间形成。
- 输入端规则：P2/P3提示词均显式注入“当前讨论氛围：xxx”；P3在t=1额外注入“这是讨论输入端（t=1）”以固定初始操纵。

实验目的：
- 在平台内比较不同氛围的主效应；
- 在平台间识别“静态社会证明（P2）”与“高阶互动放大（P3）”的机制差异。

### 三种Agent个性

所有Agent从**完全中立状态(NCI=2.0)**出发，个性差异通过**LLM系统提示词**体现：

| 个性 | 代码 | 心理特征 | 决策特点 |
|------|------|--------|--------|
| 风险敏感型 | risk_sensitive | 对潜在风险敏感，易受负面信息影响 | 对负面信息倾斜度高，易被社交信号说服 |
| 权威信任型 | authority_trusting | 倾向相信权威信息来源 | 依赖信息来源权威性，对社交信号抵抗力强 |
| 中立谨慎型 | neutral_prudent | 平衡多种信息，但易受群体影响 | 初期中立，高度受群体共识影响 |

**重要**: 不使用权重系数区分个性。所有Agent使用统一的决策公式:
```
Stance = ContentScore + SocialScore + GroupScore
NCI = 2.0 + Stance × (4/3)  [范围: 0-4]
```

### 关键指标体系

| 指标 | 代码 | 含义 | 公式 |
|------|------|------|------|
| **NCI** | negative_choice_index | 负面信息选择指数 | 0-4，中立=2.0 |
| **SCM** | stance_change_magnitude | 立场变化幅度 | 相邻时刻的NCI差值绝对值 |
| **PES** | persuasion_effect_score | 说服效应强度 | \|SocialScore + GroupScore\| |
| **GCR** | group_consensus_ratio | 群体共识比例 | max(r⁺, r⁻)，≥0.90时停止讨论 |
| **SSA** | social_signal_asymmetry | 社交信号不对称性 | 正向vs负向反馈比例 |
| **SSAF** | signal_amplification_factor | 信号放大系数 | AvgPES_P3 / AvgPES_P2 |

> 口径说明：P2为静态反馈条件，不具备真实评论点赞/回复的动态演化网络。
> 因此涉及点赞-回复网络演化的动态指标（如GCR/SSA时间步分析）仅在P3计算与报告。

> 高阶互动操作化：P3新增事件级字段 `p3_event_id`、`p3_participants_set`、`p3_copresence_size`、`p3_event_order`，
> 用“同一步多主体共同在场”表示 higher-order interaction，而非二元边的简单叠加。

## 项目文件结构

```
代码_v2_oasis/
├── 📄 核心 Python 文件
│   └── main.py                         # 主程序入口
│
├── 📁 experiment_core/                 # 核心模块
│   ├── __init__.py
│   ├── config.py                       # 配置加载和管理
│   ├── schemas.py                      # 数据结构定义 (Pydantic Models)
│   ├── env_utils.py                    # 环境变量加载
│   ├── modeling.py                     # Agent初始化和模型管理
│   ├── prompts.py                      # LLM提示词构建
│   ├── coding.py                       # 决策编码和指标计算
│   ├── runner.py                       # 异步实验执行引擎
│   ├── io_utils.py                     # 数据I/O和统计分析
│   ├── interaction.py                  # 高阶互动处理
│   ├── llm_client.py                   # LLM API 客户端
│   └── visualize.py                    # 可视化生成
│
├── 📁 outputs/                         # 输出目录
│   ├── results.jsonl                   # 实验结果(JSONL格式)
│   ├── results.csv                     # 实验结果(CSV表格)
│   ├── figures/                        # 图表输出
│   └── high_interaction_test/          # 高阶互动测试
│
├── ⚙️ 配置文件
│   ├── experiment_config.yaml ⭐⭐⭐    # 唯一配置文件（YAML格式）
│   ├── .env.example                    # 环境变量示例
│   └── requirements.txt                # 依赖列表
│
├── 📚 文档
│   ├── README.md ← 本文件
│   ├── DATA_FLOW.md                    # 数据流程图讲解 ⭐
│   ├── 模块化介绍_OASIS对齐.md          # 模块分层与职责说明
│   ├── 流程介绍_OASIS对齐.md            # 端到端流程说明
│   ├── 多模型接入与立场对比方案.md        # 多LLM接入与对比实验方案
│   └── FRAMEWORK_AND_CONFIG.md         # 框架说明
│
└── 📋 其他
    └── logs/                           # 日志目录
```

## 核心模块说明

### 1. schemas.py - 数据结构定义

使用Pydantic定义所有数据模型，支持自动验证和序列化：

```python
# 关键数据结构
- Scenario: 实验场景（背景、正向、负向叙事）
- Persona: Agent个性（名称、个性类型、系统提示词）
- AgentProfile: Agent配置（个性、条件、活跃度）
- DecisionResponse: Agent决策输出（四维决策）
- ExperimentRecord: 实验记录（完整的一次决策的所有数据）
```

### 2. prompts.py - 提示词构建

为不同个性和条件构建定制化的LLM提示词：

```python
def build_system_message(persona: Persona) -> str:
    # 根据个性类型生成系统提示词
    # 例如risk_sensitive会强调潜在风险

def build_prompt(scenario: Scenario, condition: str, social_block: Optional[str]) -> str:
    # 为specific条件构建提示词
    # P1: 无社交块
    # P2: 静态社交块（少量评论 + 点赞/分享/回复数）
    # P3: 动态讨论块（其他Agent的评论）
```

### 3. config.py - 配置管理

从YAML/JSON配置文件加载实验参数。

### 4. io_utils.py - 数据I/O

负责结果持久化和统计分析：

```python
# 写入结果
writer = ExperimentResultWriter(Path("./outputs"))
writer.add_record(experiment_record)
writer.finalize()  # 生成JSONL和CSV

# 读取和分析结果
reader = ExperimentResultReader(Path("./outputs/results.jsonl"))
reader.load()
summary = reader.get_multidimensional_summary()  # 多维度汇总
reader.save_summary_statistics(Path("./outputs/figures"))
```

### 5. visualize.py - 可视化模块

生成论文所需的各类图表：

```python
viz = ExperimentVisualizer(Path("./outputs"))
viz.load_results("results.jsonl")

# 生成各类图表
viz.plot_nci_comparison("scenario_name")        # NCI对比
viz.plot_platform_effect()                       # 平台效应
viz.plot_persona_effect()                        # 个性效应
viz.plot_climate_effect()                        # 氛围效应热力图
viz.plot_hypothesis_verification()               # 假设验证图
```

### 6. coding.py - 决策编码 [待实现]

将Agent的结构化决策转换为NCI和其他指标。

### 7. modeling.py - Agent初始化 [待实现]

根据配置创建Agent并初始化其个性和状态。

### 8. runner.py - 实验执行引擎 [待实现]

异步执行完整实验流程。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

创建 `.env` 文件，填入 API Key：

```bash
ZHIPU_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here  # 可选
```

### 3. 修改配置（推荐方式）⭐⭐⭐

编辑 `experiment_config.yaml` 文件，修改所需参数：

```yaml
# 实验方案选择
active_plan: "pilot"          # 改为 "formal" 做正式实验

# 模型配置
model:
  name: "glm-4"               # 改为 "glm-4.5-air" 用更快的模型
  api_style: "zhipu"          # 改为 "openai" 用 OpenAI
  temperature: 0.2            # 调整生成的随机性（0.0-1.0）
  max_tokens: 500             # 最大生成长度

# 并发与重试配置
concurrency: 5                # 同时运行的 Agent 数
repeats_per_cell: 2           # 每个单元重复次数
max_retries: 2                # API 失败重试次数
```

### 4. 运行实验

```bash
# 运行实验（使用默认配置）
python main.py

# 指定自定义配置文件
python main.py --config experiment_config.yaml

# 指定输出目录
python main.py --output-dir outputs/

# 严格按 OASIS 官方流程部署（P3推荐）
python main.py --mode oasis
```

### 5. 严格 OASIS 部署模式（新增）

统一入口 [main.py](main.py)：

- 使用 OASIS 官方环境 API（`oasis.make`, `LLMAction`, `ManualAction`）
- 冷启动注入事件背景，不注入预置评论
- 多时间步由 OASIS 原生 agent 行为推进
- 输出 SQLite 轨迹库到 `outputs/oasis_strict_reddit_simulation.db`

## 配置参数说明

在 `experiment_config.yaml` 中配置所有参数，包括：
- ✅ 模型选择（Zhipu GLM / OpenAI）
- ✅ 温度和 Token 限制
- ✅ 并发数和重试策略
- ✅ 所有实验场景和人物
- ✅ 社交反馈文本和讨论线程

## 项目文件结构

## 实验设计矩阵

基础配置：
- **条件**: 3个 (P1/P2/P3)
- **场景**: N个 (可配置，默认2-3个)
- **个性**: 3个 (risk_sensitive, authority_trusting, neutral_prudent)
- **氛围**: 3个 (none, positive_leaning, negative_leaning)
- **Agent数**: 每个组合20个

总规模示例 (2个场景):
```
2 scenarios × 3 conditions × 3 personas × 3 atmospheres × 20 agents = 3,240 agents
```

## 关键修改点（vs v1）

### 1. 移除权重系数
- ❌ 之前: `Stance = w_cs·ContentScore + w_ss·SocialScore + w_gc·GroupScore`
- ✅ 现在: `Stance = ContentScore + SocialScore + GroupScore`

### 2. 个性差异实现方式
- ❌ 之前: 通过权重系数(w^{cs}, w^{ss}, w^{gc})区分个性
- ✅ 现在: 通过LLM系统提示词体现个性差异

### 3. PES公式简化
- ❌ 之前: `PES = |SocialScore + GroupScore| × w_susceptibility`
- ✅ 现在: `PES = |SocialScore + GroupScore|`

### 4. 初始状态统一
- ❌ 之前: 不同个性可能有不同初始立场
- ✅ 现在: 所有Agent统一从NCI=2.0(完全中立)开始

## 待实现的核心功能

### Priority 1: 实验执行引擎
- [✅] modeling.py: Agent初始化
- [✅] runner.py: 异步实验循环
- [✅] coding.py: 决策编码
- [✅] llm_client.py: LLM API 客户端（支持 Zhipu + OpenAI）
- [✅] SSL 证书验证错误修复

### Priority 2: 高级功能
- [ ] GCR动态计算（群体共识达到0.90时停止）
- [ ] P3高互动讨论的对话生成
- [ ] 时间序列分析

## 框架技术栈

### 核心框架
- **CAMEL-AI** (https://github.com/camel-ai/camel) >= 0.2.78
  - ChatAgent：Agent 创建与管理
  - ModelFactory：统一的模型工厂
  - 支持多个 LLM 提供商

- **CAMEL-OASIS** >= 0.2.5
  - 社交媒体仿真模块

### 依赖库
- **Pydantic** >= 2.0.0: 数据验证
- **PyYAML** >= 6.0: 配置管理
- **OpenAI API** >= 1.0.0: GPT 模型
- **Zhipu AI** >= 2.0.0: 智谱 GLM 模型
- **aiohttp** >= 3.8.0: 异步 HTTP
- **pandas**, **numpy**, **matplotlib**: 数据分析和可视化

详见 [requirements.txt](requirements.txt)

## 输出格式

### ExperimentRecord (schemas.py)

```json
{
  "agent_id": "agent_001",
  "scenario_name": "mycoplasma_pneumonia",
  "condition_name": "high_interaction",
  "persona_name": "risk_sensitive",
  "climate_type": "negative_leaning",
  "decision_response": {
    "credible_choice": "negative",
    "like_choice": "negative",
    "share_choice": "negative",
    "comment_choice": "support_negative"
  },
  "negative_choice_index": 3.5,
  "stance_change": 0.25,
  "persuasion_effect": 1.2,
  "timestamp": "2025-01-15T10:30:45Z"
}
```

### 汇总统计文件

- `summary_by_condition.csv` - 按条件(P1/P2/P3)汇总
- `summary_by_persona.csv` - 按个性汇总
- `summary_by_scenario.csv` - 按场景汇总
- `summary_multidimensional.csv` - 多维度(条件×个性×场景)汇总

## 故障排除

### Q: results.jsonl文件未找到
A: 请先运行实验生成结果：`python main.py`

### Q: 如何修改场景或个性？
A: 编辑 `experiment_config.yaml` 并重新运行

### Q: 如何使用自定义LLM模型？
A: 修改 `config.py` 中的模型配置部分

---

**最后更新**: 2026年3月30日  
**版本**: v2.0 OASIS  
**状态**: 生产就绪

## 相关文档

| 文档 | 内容 | 适合场景 |
|------|------|---------|
| [FRAMEWORK_AND_CONFIG.md](FRAMEWORK_AND_CONFIG.md) | 框架和依赖说明 | 理解项目技术栈 |
| [DATA_FLOW.md](DATA_FLOW.md) | 数据流程图讲解 | 理解数据处理流程 |

## 许可与引用

本项目基于 OASIS (Apache 2.0) 改进。

```bibtex
@misc{yang2024oasisopenagentsocial,
  title={OASIS: Open Agent Social Interaction Simulations with One Million Agents},
  author={Yang, Ziyi and others},
  year={2024},
  eprint={2411.11581},
  archivePrefix={arXiv}
}
```

## 联系与支持

- 问题与建议：GitHub Issues
- 学术合作：camel.ai.team@gmail.com
