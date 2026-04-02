"""
Prompt 构造模块。

负责为不同实验条件构造合适的 prompt 模板。
"""

from .config import ExperimentConfig
from .schemas import ChoiceBinary, ClimateType, ConditionName, Persona, Scenario


def _climate_label(climate_type: ClimateType) -> str:
    """将配置值映射为可读的氛围标签。"""
    mapping = {
        "none": "中性基线（none）",
        "positive_leaning": "偏正向氛围（positive_leaning）",
        "negative_leaning": "偏负向氛围（negative_leaning）",
    }
    return mapping.get(climate_type, f"未定义氛围（{climate_type}）")


def build_system_message(persona: Persona) -> str:
    """
    构造 Agent 的系统提示词。

    Args:
        persona: 人物角色

    Returns:
        str: 系统提示词
    """
    return (
        "你是一名普通社交媒体用户。\n"
        "请像真实用户一样基于当前信息环境作答，不要回避选择。\n"
        "不要提供医疗建议，不要编造额外事实。\n"
        f"\n角色设定：{persona.profile}"
    )


def build_prompt(
    scenario: Scenario,
    condition: ConditionName,
    climate_type: ClimateType,
    info1_polarity: ChoiceBinary,
    config: ExperimentConfig,
    social_block: str = "",
    include_reason: bool = True,
) -> str:
    """
    构造完整的实验 prompt。

    Args:
        scenario: 实验场景
        condition: 实验条件
        climate_type: 互动氛围类型
        info1_polarity: 信息 1 的倾向（positive 或 negative）
        config: 实验配置
        social_block: 社交反馈或互动线程文本
        include_reason: 是否要求提供理由

    Returns:
        str: 完整的 prompt
    """
    # 根据 info1_polarity 决定哪条是正向/负向
    if info1_polarity == "positive":
        info1 = scenario.positive_narrative
        info2 = scenario.negative_narrative
        info1_label = "正向"
        info2_label = "负向"
    else:
        info1 = scenario.negative_narrative
        info2 = scenario.positive_narrative
        info1_label = "负向"
        info2_label = "正向"

    parts = [
        "请阅读下面的信息环境并完成判断。",
        "",
        "注意：",
        "1. 这是信息判断任务，不是医疗建议任务。",
        "2. 只能依据给定内容作答。",
        "3. 只输出 JSON。",
        "",
        "【事件背景】",
        scenario.background,
        "",
        "【信息 1】",
        info1,
        "",
        "【信息 2】",
        info2,
    ]

    if condition in ["low_feedback", "high_interaction"]:
        parts.extend(
            [
                "",
                "【平台内讨论氛围】",
                f"当前讨论氛围：{_climate_label(climate_type)}",
            ]
        )

    # 根据条件添加社交反馈或互动线程
    if condition == "low_feedback":
        # P2 平台：显示静态评论快照（无回复链）
        parts.extend(["", "【评论区 - 静态快照（无回复链）】", social_block])
    elif condition == "high_interaction":
        # P3 平台：显示完整的社群讨论线程（含回复链）
        parts.extend(["", "【社群讨论现场】", social_block])

    parts.extend(["", "按以下字段输出（JSON 格式）："])
    
    # 基础决策字段（所有条件通用）
    parts.extend([
        '- credible_choice: "positive"、"negative" 或 "neutral"',
        '- like_choice: "positive"、"negative" 或 "none"',
        '- share_choice: "positive"、"negative" 或 "none"',
        '- comment_choice: "support_positive"、"support_negative" 或 "neutral"',
    ])
    
    # P3 额外字段：计划的社群行动
    if condition == "high_interaction":
        parts.extend([
            '- planned_action: "post_comment"（发表评论）、"reply"（回复某位用户）、"like"（点赞）、"repost"（转发）、"observe"（继续观察）',
            '- reply_target: 若 planned_action="reply"，填写要回复的用户ID（如 agent_000123）；否则写 "none"',
            '- group_consensus_perception: 0-100 之间的数字，表示你认为社群中支持负向观点的比例',
            '- public_comment: 你在论坛公开发布的评论（1-40字，避免重复）',
            '- private_reason: 仅供研究记录的内部理由，其他Agent不可见',
        ])

    if include_reason and condition != "high_interaction":
        parts.append(f'- reason: 简短理由，不超过 {config.reason_max_chars} 字')

    parts.extend(
        [
            "",
            "补充说明：",
            f"- 信息 1 为{info1_label}信息",
            f"- 信息 2 为{info2_label}信息",
        ]
    )

    if condition == "high_interaction":
        parts.extend([
            "- 论坛中不会显示你的立场标签，请通过评论文本自然表达。",
            "- 评论避免复读，尽量补充新角度（优先发布新观点，而不是只回复别人）。",
            "- 不要连续多轮只做同一种动作（尤其不要一直互相回复同一对象）。",
            "- 若要回复，优先选择近期未互动过的对象，减少A↔B来回互回。",
            "- 如果没有明确回复对象或没有新证据支持回复，优先使用 post_comment 发表独立观点。",
            f"- 你在 t=1 进入讨论时，已处在“{_climate_label(climate_type)}”的信息环境中。",
        ])
    elif condition == "low_feedback":
        parts.extend([
            "- 当前评论区是单一时刻的静态截面：只有少量评论及其热度线索，看不到评论随时间的新增或变化。",
            "- 你只能基于当前快照中的评论内容与热度线索判断“当前多数倾向”。",
            f"- 你在 t=1 仅基于“{_climate_label(climate_type)}”快照做一次判断。",
        ])

    return "\n".join(parts)


def build_independent_prompt(
    scenario: Scenario,
    persona: Persona,
    info1_polarity: ChoiceBinary,
    config: ExperimentConfig,
) -> str:
    """
    构造独立决策条件的 prompt。

    Args:
        scenario: 实验场景
        persona: 人物角色
        info1_polarity: 信息 1 倾向
        config: 实验配置

    Returns:
        str: 包含系统提示的完整 prompt
    """
    system_msg = build_system_message(persona)
    user_msg = build_prompt(
        scenario=scenario,
        condition="independent",
        climate_type="none",
        info1_polarity=info1_polarity,
        config=config,
        social_block="",
        include_reason=True,
    )
    return f"{system_msg}\n\n{user_msg}"


def build_low_feedback_prompt(
    scenario: Scenario,
    persona: Persona,
    info1_polarity: ChoiceBinary,
    climate_type: ClimateType,
    config: ExperimentConfig,
) -> str:
    """
    构造低强度互动条件的 prompt（P2 平台）。
    
    Agent 可以看到：
    - 原始信息（正向和负向叙事）
    - 其他用户的评论内容和评论作者
    - 点赞数、转发数、回复数等社交信号
    - 少量评论构成的静态讨论截面
    
    Agent 看不到：
    - 评论新增与热度变化的时间过程
    - 互动如何随时间推进形成共识

    Args:
        scenario: 实验场景
        persona: 人物角色
        info1_polarity: 信息 1 倾向
        climate_type: 互动氛围类型
        config: 实验配置

    Returns:
        str: 包含系统提示的完整 prompt
    """
    system_msg = build_system_message(persona)
    social_block = config.low_feedback_blocks.get(climate_type, "")
    user_msg = build_prompt(
        scenario=scenario,
        condition="low_feedback",
        climate_type=climate_type,
        info1_polarity=info1_polarity,
        config=config,
        social_block=social_block,
        include_reason=True,
    )
    return f"{system_msg}\n\n{user_msg}"


def build_high_interaction_prompt(
    scenario: Scenario,
    persona: Persona,
    info1_polarity: ChoiceBinary,
    climate_type: ClimateType,
    config: ExperimentConfig,
) -> str:
    """
    构造高阶互动条件的 prompt（P3 平台 - 动态社群讨论）。
    
    P3 是一个实时的社群讨论环境：
    - 看到原始帖子和背景信息
    - 看到其他参与者的讨论和立场
    - 看到点赞、转发、回复等社交信号
    - 可以选择发表评论、点赞、转发或观察
    
    所有 Agent 都是被试者，被完整测量：
    - 做出的决策（现在相信哪个立场）
    - 计划采取的行动（发言还是观察）
    - 对讨论的理解（群体态度）

    Args:
        scenario: 实验场景
        persona: 人物角色
        info1_polarity: 信息 1 倾向
        climate_type: 互动氛围类型
        config: 实验配置

    Returns:
        str: 包含系统提示的完整 prompt
    """
    system_msg = build_system_message(persona)
    social_block = config.high_interaction_blocks.get(climate_type, "")
    user_msg = build_prompt(
        scenario=scenario,
        condition="high_interaction",
        climate_type=climate_type,
        info1_polarity=info1_polarity,
        config=config,
        social_block=social_block,
        include_reason=True,
    )
    return f"{system_msg}\n\n{user_msg}"
