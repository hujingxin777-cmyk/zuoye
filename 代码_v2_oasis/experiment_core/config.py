"""
配置加载模块。

支持从 YAML 或 JSON 配置文件加载实验配置。
"""

from pathlib import Path
from typing import Optional, Literal

import yaml
import json
from pydantic import BaseModel, Field

from .schemas import Scenario, Persona, ClimateType, ConditionName


class ModelConfig(BaseModel):
    """LLM 模型配置"""
    
    name: str = "glm-4"
    api_style: str = "zhipu"  # "zhipu" 或 "openai"
    temperature: float = 0.2
    max_tokens: int = 500
    api_key_env: Optional[str] = None
    api_base_url: Optional[str] = None


class ExperimentPlan(BaseModel):
    """实验方案（用于 pilot/formal/custom 切换）。"""

    conditions: Optional[list[ConditionName]] = None
    scenario_names: Optional[list[str]] = None
    persona_names: Optional[list[str]] = None
    repeats_per_cell: Optional[int] = None
    concurrency: Optional[int] = None
    api_concurrency: Optional[int] = None
    low_feedback_climates: Optional[list[ClimateType]] = None
    high_interaction_climates: Optional[list[ClimateType]] = None


class ExperimentConfig(BaseModel):
    """实验总配置。"""

    # 方案选择
    active_plan: str = "pilot"
    #
    use_oasis_deploy: bool = False

    # 模型配置
    model: ModelConfig = Field(default_factory=lambda: ModelConfig())
    model_pool: list[ModelConfig] = Field(default_factory=list)
    model_assignment_strategy: Literal["single", "by_agent_hash", "round_robin"] = "single"
    api_base_url: Optional[str] = "https://open.bigmodel.cn/api/paas/v4/"
    reason_max_chars: int = 30

    # 并发与重试
    concurrency: int = 5
    api_concurrency: int = 1
    repeats_per_cell: int = 3
    max_retries: int = 2
    retry_backoff_seconds: float = 2.0
    agent_retry_attempts: int = 2
    agent_retry_delay: float = 1.5

    # 高阶互动（P3）
    interaction_mode: str = "dynamic"  # "dynamic" 或 "static"
    high_interaction_agent_count: int = 9
    high_interaction_persona_ratio: list[int] = Field(default_factory=lambda: [1, 1, 1])
    high_interaction_rounds: int = 2
    high_interaction_max_timestep: int = 10
    high_interaction_activate_prob: float = 0.8
    high_interaction_step_timeout_seconds: float = 120.0
    high_consensus_threshold: float = 0.90
    high_consensus_hold_steps: int = 2
    discussion_stalled_steps: int = 4
    high_interaction_reply_cooldown: int = 1
    high_interaction_max_visible_events: int = 18

    # 随机种子
    random_seed: int = 42

    # 实验条件
    conditions: list[ConditionName]
    personas: list[Persona]
    scenarios: list[Scenario]

    # 条件子版本
    low_feedback_climates: list[ClimateType] = Field(
        default_factory=lambda: ["none", "positive_leaning", "negative_leaning"]
    )
    high_interaction_climates: list[ClimateType] = Field(
        default_factory=lambda: ["none", "positive_leaning", "negative_leaning"]
    )

    # 社交反馈文本
    low_feedback_blocks: dict[ClimateType, str]
    high_interaction_blocks: dict[ClimateType, str]

    # 实验方案预设
    plans: dict[str, ExperimentPlan] = Field(default_factory=dict)

    class Config:
        """配置模型行为。"""
        arbitrary_types_allowed = True


def load_config(config_path: Path | str) -> ExperimentConfig:
    """
    从 YAML 或 JSON 文件加载配置。

    Args:
        config_path: 配置文件路径

    Returns:
        ExperimentConfig: 加载的配置对象

    Raises:
        FileNotFoundError: 如果文件不存在
        ValueError: 如果文件格式不支持
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    if config_path.suffix == ".yaml" or config_path.suffix == ".yml":
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
    elif config_path.suffix == ".json":
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
    else:
        raise ValueError(f"不支持的配置文件格式: {config_path.suffix}")

    config = ExperimentConfig(**config_dict)

    # 应用实验方案（如有）
    if config.active_plan and config.active_plan != "custom":
        config = apply_experiment_plan(config)

    return config


def apply_experiment_plan(config: ExperimentConfig) -> ExperimentConfig:
    """
    根据 active_plan 应用预设方案。

    Args:
        config: 原始配置

    Returns:
        ExperimentConfig: 应用方案后的配置
    """
    if not config.plans or config.active_plan not in config.plans:
        return config

    plan = config.plans[config.active_plan]
    effective = config.model_copy(deep=True)

    # 覆盖相应字段（如果方案中有定义）
    if plan.conditions:
        effective.conditions = plan.conditions
    if plan.scenario_names:
        effective.scenarios = [
            s for s in effective.scenarios if s.name in plan.scenario_names
        ]
    if plan.persona_names:
        effective.personas = [
            p for p in effective.personas if p.name in plan.persona_names
        ]
    if plan.repeats_per_cell:
        effective.repeats_per_cell = plan.repeats_per_cell
    if plan.concurrency:
        effective.concurrency = plan.concurrency
    if plan.api_concurrency:
        effective.api_concurrency = plan.api_concurrency
    if plan.low_feedback_climates:
        effective.low_feedback_climates = plan.low_feedback_climates
    if plan.high_interaction_climates:
        effective.high_interaction_climates = plan.high_interaction_climates

    return effective
