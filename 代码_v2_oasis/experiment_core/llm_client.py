"""
LLM API 调用模块

优先使用 CAMEL 内置模型调用：
- 智谱 GLM (zhipu)
- OpenAI (openai)
"""

import os
import asyncio
from typing import Optional

from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from .config import ExperimentConfig, ModelConfig


class CamelChatClient:
    """基于 CAMEL ModelFactory + ChatAgent 的调用客户端。"""

    def __init__(self, model_cfg: ModelConfig, api_key: str):
        self.model_cfg = model_cfg
        self.api_key = api_key
        self.model = self._init_model()

    def _init_model(self):
        api_style = (self.model_cfg.api_style or "").strip().lower()
        model_config = {
            "temperature": self.model_cfg.temperature,
            "max_tokens": self.model_cfg.max_tokens,
        }

        if api_style == "zhipu":
            # CAMEL 直接集成 ZHIPU 平台读取 ZHIPUAI_API_KEY
            os.environ["ZHIPUAI_API_KEY"] = self.api_key
            return ModelFactory.create(
                model_platform=ModelPlatformType.ZHIPU,
                model_type=self.model_cfg.name,
                model_config_dict=model_config,
            )

        if api_style == "openai":
            os.environ["OPENAI_API_KEY"] = self.api_key
            return ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI,
                model_type=self.model_cfg.name,
                model_config_dict=model_config,
            )

        raise ValueError(f"不支持的API风格: {self.model_cfg.api_style}")

    async def call(self, system_message: str, user_message: str, temperature: float = 0.7) -> str:
        """调用模型并返回文本内容。"""

        def _sync_call() -> str:
            agent = ChatAgent(system_message=system_message, model=self.model)
            response = agent.step(user_message)
            msgs = getattr(response, "msgs", None) or []
            if msgs:
                content = getattr(msgs[-1], "content", "")
                return str(content or "")
            return ""

        try:
            return await asyncio.to_thread(_sync_call)
        except Exception as e:
            raise Exception(f"CAMEL调用失败: {str(e)}")


class LLMClient:
    """统一的LLM客户端接口"""
    
    def __init__(self, config: ExperimentConfig):
        """
        初始化LLM客户端
        
        Args:
            config: 实验配置
        """
        self.config = config
        self._route_counter = 0
        self._model_pool = self._build_model_pool()
        self._client_cache: dict[str, object] = {}

    def _build_model_pool(self) -> list[ModelConfig]:
        """构建模型池；若未配置则回退到单模型。"""
        if getattr(self.config, "model_pool", None):
            return list(self.config.model_pool)
        return [self.config.model]

    def _resolve_api_key(self, model_cfg: ModelConfig) -> str:
        """按模型类型解析 API Key。"""
        api_style = model_cfg.api_style

        if model_cfg.api_key_env:
            api_key = os.getenv(model_cfg.api_key_env)
            if not api_key:
                raise ValueError(f"未找到 {model_cfg.api_key_env} 环境变量")
            return api_key

        if api_style == "zhipu":
            api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("ZHIPUAI_API_KEY")
            if not api_key:
                raise ValueError("未找到 ZHIPU_API_KEY / ZHIPUAI_API_KEY 环境变量")
            return api_key

        if api_style == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("未找到 OPENAI_API_KEY 环境变量")
            return api_key

        raise ValueError(f"不支持的API风格: {api_style}")

    def _init_client(self, model_cfg: ModelConfig):
        """根据模型配置初始化客户端（CAMEL内置）。"""
        api_key = self._resolve_api_key(model_cfg)
        return CamelChatClient(model_cfg, api_key)

    def _get_client(self, model_cfg: ModelConfig):
        """获取（或缓存）指定模型客户端。"""
        cache_key = f"{model_cfg.api_style}::{model_cfg.name}::{model_cfg.api_base_url or ''}::{model_cfg.api_key_env or ''}"
        if cache_key not in self._client_cache:
            self._client_cache[cache_key] = self._init_client(model_cfg)
        return self._client_cache[cache_key]

    def _route_model(self, route_key: Optional[str] = None) -> ModelConfig:
        """根据策略路由到一个模型。"""
        strategy = getattr(self.config, "model_assignment_strategy", "single")
        if not self._model_pool:
            raise ValueError("model_pool 为空，无法路由模型")

        if strategy == "single" or len(self._model_pool) == 1:
            return self._model_pool[0]

        if strategy == "by_agent_hash":
            key = route_key or "default"
            idx = abs(hash(key)) % len(self._model_pool)
            return self._model_pool[idx]

        if strategy == "round_robin":
            idx = self._route_counter % len(self._model_pool)
            self._route_counter += 1
            return self._model_pool[idx]

        return self._model_pool[0]

    async def call(
        self,
        system_message: str,
        user_message: str,
        route_key: Optional[str] = None,
        model_override: Optional[ModelConfig] = None,
    ) -> str:
        """
        调用LLM
        
        Args:
            system_message: 系统提示词
            user_message: 用户消息
            route_key: 路由键（例如agent_id）
            model_override: 强制指定模型配置
            
        Returns:
            str: 模型响应
        """
        model_cfg = model_override or self._route_model(route_key=route_key)
        client = self._get_client(model_cfg)
        return await client.call(
            system_message,
            user_message,
            temperature=model_cfg.temperature
        )

    def choose_model(self, route_key: Optional[str] = None) -> ModelConfig:
        """暴露模型路由结果，供上层记录使用。"""
        return self._route_model(route_key=route_key)
