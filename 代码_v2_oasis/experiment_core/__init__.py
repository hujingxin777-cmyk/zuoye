"""
实验框架核心模块 v2.0

基于 OASIS 框架改进的负面信息选择实验框架。
"""

__version__ = "2.0.0"

from .schemas import (
    Scenario,
    Persona,
    DecisionResponse,
    ConditionName,
    ClimateType,
)
from .config import ExperimentConfig, load_config
from .env_utils import load_env_file
from .modeling import AgentFactory, AgentState, ExperimentMatrix, ModelManager
from .prompts import build_system_message, build_prompt
from .coding import code_negative_index, DecisionEncoder, LLMResponseParser
from .runner import ExperimentRunner

__all__ = [
    "Scenario",
    "Persona",
    "DecisionResponse",
    "ConditionName",
    "ClimateType",
    "ExperimentConfig",
    "load_config",
    "load_env_file",
    "AgentFactory",
    "AgentState",
    "ExperimentMatrix",
    "ModelManager",
    "build_system_message",
    "build_prompt",
    "code_negative_index",
    "DecisionEncoder",
    "LLMResponseParser",
    "ExperimentRunner",
]
