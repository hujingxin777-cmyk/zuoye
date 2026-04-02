"""
数据结构定义（Pydantic Models）

定义实验中所有的数据结构，包括场景、人物、决策响应等。
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


# 类型约束
ChoiceBinary = Literal["positive", "negative"]
ChoiceTernary = Literal["positive", "negative", "none"]
CredibilityChoice = Literal["positive", "neutral", "negative"]  # 可信度判断允许中立
CommentChoice = Literal["support_positive", "support_negative", "neutral"]
ConditionName = Literal["independent", "low_feedback", "high_interaction"]
ClimateType = Literal["none", "positive_leaning", "negative_leaning"]

# Agent 个性类型（参考 v1 版本的三类 Agent）
PersonaType = Literal[
    "risk_sensitive",      # 对潜在健康风险较为敏感
    "authority_trusting",  # 更相信专家和正式信息来源
    "neutral_prudent",     # 平衡不同信息，但易受群体影响
]


class Scenario(BaseModel):
    """实验场景定义。"""

    name: str = Field(description="场景名称，如 mycoplasma_pneumonia")
    background: str = Field(description="中立背景信息")
    positive_narrative: str = Field(description="正向叙事（风险可控、情况缓和）")
    negative_narrative: str = Field(description="负向叙事（风险升级、信息被低估）")


class Persona(BaseModel):
    """Agent 人物角色定义（参考 v1 版本）。"""

    name: str = Field(description="人物名称，如 risk_sensitive")
    profile: str = Field(description="人物描述，用于系统提示词")
    persona_type: Optional[PersonaType] = Field(
        default=None,
        description="Agent 的个性类型：risk_sensitive、authority_trusting、neutral_prudent"
    )


class AgentProfile(BaseModel):
    """Agent 的完整配置（包含个性和平台角色）。"""
    
    agent_id: str = Field(description="Agent 的唯一 ID")
    persona: Persona = Field(description="Agent 的人物角色（个性）")
    condition: ConditionName = Field(description="所属的实验条件")
    
    # 用于 P1/P2 的额外属性
    is_test_subject: bool = Field(
        default=False,
        description="是否是专门的被试对象（P1/P2 中被完整测量）"
    )
    
    # 用于 P3 的额外属性
    # 注意：initial_stance 已移除，所有 Agent 都从中立(neutral)开始
    # 注意：persuadability 已移除，个性差异通过LLM prompt体现
    activity_level: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="讨论参与活跃度（仅用于 P3，high/medium/low）"
    )


class DecisionResponse(BaseModel):
    """Agent 的结构化决策输出。
    
    根据论文设计（4.2 测量维度）：
    - credible_choice: 可信度判断，允许正向/中立/负向
    - like_choice: 点赞倾向，可选正向/负向/不点赞
    - share_choice: 转发意愿，可选正向/负向/不转发
    - comment_choice: 评论立场，支持正向/负向/中立
    """

    credible_choice: CredibilityChoice = Field(
        description="可信度判断：认为哪条信息更可信（positive/neutral/negative）"
    )
    like_choice: ChoiceTernary = Field(
        description="点赞倾向：更愿意点赞哪条信息（positive、negative 或 none）"
    )
    share_choice: ChoiceTernary = Field(
        description="转发意愿：更愿意转发哪条信息（positive、negative 或 none）"
    )
    comment_choice: CommentChoice = Field(
        description="评论立场：表达的立场倾向（support_positive、support_negative 或 neutral）"
    )
    reason: Optional[str] = Field(
        default=None,
        description="简短理由，不超过指定字符数（可选，如果LLM未生成则为None）"
    )


class DecisionResponseLite(BaseModel):
    """精简版结构化输出（长度超限时的回退方案）。"""

    credible_choice: CredibilityChoice  # 与DecisionResponse保持一致
    like_choice: ChoiceTernary
    share_choice: ChoiceTernary
    comment_choice: CommentChoice


class ExperimentRecord(BaseModel):
    """单次实验的完整记录。"""

    run_id: str = Field(description="实验唯一 ID")
    agent_id: str = Field(description="Agent ID")
    scenario_name: str = Field(description="场景名称")
    persona_name: str = Field(description="人物角色名")
    condition_name: ConditionName = Field(description="实验条件")
    climate_type: ClimateType = Field(description="互动氛围类型")
    repeat_index: int = Field(description="重复索引")
    round_index: int = Field(default=1, description="互动轮次索引（P1/P2默认为1）")
    timestep: int = Field(default=1, description="时间步（P1/P2默认为1，P3为动态步）")
    info1_polarity: ChoiceBinary = Field(description="信息 1 的倾向")
    info2_polarity: ChoiceBinary = Field(description="信息 2 的倾向")
    
    # 输出与编码
    model_name_used: Optional[str] = Field(default=None, description="本次决策实际调用的模型名")
    model_api_style_used: Optional[str] = Field(default=None, description="本次决策实际调用的API风格")
    credible_choice: CredibilityChoice  # 可信度判断允许中立
    like_choice: ChoiceTernary
    share_choice: ChoiceTernary
    comment_choice: CommentChoice
    reason: Optional[str] = None
    public_comment: Optional[str] = Field(default=None, description="P3公开评论（对其他Agent可见）")
    private_reason: Optional[str] = Field(default=None, description="仅研究记录可见的内部理由")
    planned_action: Optional[Literal["post_comment", "reply", "like", "repost", "observe"]] = Field(
        default=None,
        description="P3计划动作",
    )
    reply_target: Optional[str] = Field(default=None, description="P3回复目标用户ID")
    group_consensus_perception: Optional[int] = Field(
        default=None,
        description="P3对群体共识的主观感知（0-100）",
    )
    
    # 编码指标
    negative_choice_index: int = Field(
        description="总体负面选择指数（0-4）"
    )
    negative_choice_intensity: Optional[float] = Field(
        default=None,
        description="连续强度型NCI（0-4），由stance线性映射得到",
    )
    content_score: Optional[float] = Field(default=None, description="内容分量分数")
    social_score: Optional[float] = Field(default=None, description="社交分量分数")
    group_score: Optional[float] = Field(default=None, description="群体分量分数")
    stance: Optional[float] = Field(default=None, description="综合立场分数")
    persuasion_effect_score: Optional[float] = Field(default=None, description="PES=|SocialScore+GroupScore|")
    stance_change_magnitude: Optional[float] = Field(default=None, description="SCM=|NCI_t-NCI_t-1|")

    credibility_negative: int
    like_negative: int
    share_negative: int
    comment_negative: int

    # 动态群体指标（主要用于P3）
    group_consensus_ratio: Optional[float] = Field(default=None, description="GCR，群体共识度")
    social_signal_asymmetry: Optional[float] = Field(default=None, description="SSA，社交信号不对称度")
    is_stop_step: bool = Field(default=False, description="该时间步是否触发停止")
    stop_reason: Optional[str] = Field(default=None, description="停止原因")

    # P3 高阶互动（事件/超边）字段
    p3_is_higher_order_event: Optional[bool] = Field(
        default=None,
        description="是否属于P3的高阶事件（多主体共同在场）",
    )
    p3_event_order: Optional[int] = Field(
        default=None,
        description="P3时间步内事件顺序（1-based）",
    )
    p3_event_id: Optional[str] = Field(
        default=None,
        description="P3事件ID（scenario+climate+repeat+timestep）",
    )
    p3_participants_set: Optional[str] = Field(
        default=None,
        description="P3该步激活参与者集合（JSON字符串）",
    )
    p3_copresence_size: Optional[int] = Field(
        default=None,
        description="P3该步共同在场参与者数量",
    )
    
    # 元数据
    status: Literal["ok", "ok_lite", "error"] = Field(description="执行状态")
    error_message: Optional[str] = None
    raw_response: Optional[str] = None
    timestamp: Optional[str] = None  # ISO 格式时间戳


class SocialFeedbackBlock(BaseModel):
    """社交反馈文本块（用于低强度和高阶互动条件）。"""

    climate_type: ClimateType = Field(description="反馈倾向类型")
    content: str = Field(description="反馈文本内容")
    num_comments: int = Field(description="评论/发言数量")

# P3 特有的数据结构
PlannedAction = Literal["post_comment", "reply", "like", "repost", "observe"]


class HighInteractionDecisionResponse(DecisionResponse):
    """P3 平台（社群讨论）的扩展决策响应。"""

    planned_action: PlannedAction = Field(
        description="计划采取的社群行动：post_comment、reply、like、repost 或 observe"
    )
    group_consensus_perception: int = Field(
        ge=0, le=100,
        description="对群体共识的感知（0-100，表示认为支持负向观点的比例）"
    )


class CommunityAgentState(BaseModel):
    """社群中单个 Agent 的状态记录（用于动态追踪）。"""

    agent_id: str = Field(description="Agent ID")
    timestep: int = Field(description="当前时间步")
    
    # 当前的决策与感知
    credible_choice: ChoiceBinary
    planned_action: PlannedAction
    group_consensus_perception: int
    
    # 看到的环境
    visible_comments_count: int = Field(description="看到的评论总数")
    highest_liked_stance: Optional[ChoiceBinary] = Field(description="最高赞评论的立场")
    discussion_thread_length: int = Field(description="讨论线程的深度")
    
    # 代理的历史决策变化
    decision_change_from_t0: Optional[ChoiceBinary] = Field(
        description="相比初始决策的改变（None 表示没变）"
    )


class CommunitySimulationState(BaseModel):
    """社群模拟的全局状态（P3 平台每个时间步的快照）。"""

    platform_id: str
    timestep: int
    scenario_name: str
    climate_type: ClimateType
    
    # 群体统计
    total_agents: int
    positive_advocates: int = Field(description="支持正向观点的 Agent 数")
    negative_advocates: int = Field(description="支持负向观点的 Agent 数")
    neutral_or_undecided: int
    
    # 讨论度量
    total_comments: int
    avg_likes_per_comment: float
    discussion_polarization: float = Field(
        ge=0, le=1,
        description="讨论极化程度（0=完全中立，1=完全极化）"
    )
    
    # 停止信号评估
    should_stop: bool = Field(description="是否应该停止仿真")
    stop_reason: Optional[str] = Field(
        description="停止原因：max_timestep、high_consensus、discussion_stalled 等"
    )