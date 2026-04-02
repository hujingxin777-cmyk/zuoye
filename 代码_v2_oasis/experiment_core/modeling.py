"""
Agent 初始化与建模模块 (modeling.py)

负责创建和初始化Agent，配置其个性和初始状态。
"""

import random
from typing import Dict, List, Optional
from pathlib import Path

from .schemas import (
    AgentProfile,
    Persona,
    PersonaType,
    ConditionName,
    ExperimentRecord,
    DecisionResponse,
)
from .config import ExperimentConfig
from .prompts import build_system_message


class AgentFactory:
    """Agent工厂类，负责批量创建和初始化Agent"""
    
    def __init__(self, config: ExperimentConfig, random_seed: Optional[int] = None):
        """
        初始化Agent工厂
        
        Args:
            config: 实验配置对象
            random_seed: 随机种子，用于可重现性
        """
        self.config = config
        self.agent_counter = 0
        
        if random_seed is not None:
            random.seed(random_seed)
    
    def create_agent(
        self,
        persona: Persona,
        condition: ConditionName,
        agent_index: int,
        is_test_subject: bool = False,
    ) -> AgentProfile:
        """
        创建单个Agent
        
        Args:
            persona: Agent的个性设置
            condition: 实验条件(P1/P2/P3)
            agent_index: Agent在该条件下的序号
            is_test_subject: 是否是被测试的对象(P1/P2)
            
        Returns:
            AgentProfile: 创建的Agent配置
        """
        self.agent_counter += 1
        
        # 生成唯一的Agent ID
        agent_id = f"agent_{self.agent_counter:06d}"
        
        # 创建Agent配置
        agent_profile = AgentProfile(
            agent_id=agent_id,
            persona=persona,
            condition=condition,
            is_test_subject=is_test_subject,
            activity_level=random.choice(["high", "medium", "low"]) if condition == "high_interaction" else None,
        )
        
        return agent_profile
    
    def batch_create_agents(
        self,
        personas: List[Persona],
        condition: ConditionName,
        count_per_persona: int,
        is_test_subject: bool = False,
    ) -> List[AgentProfile]:
        """
        批量创建指定条件和个性的Agent
        
        Args:
            personas: 个性列表
            condition: 实验条件
            count_per_persona: 每个个性创建多少个Agent
            is_test_subject: 是否都是被测试对象
            
        Returns:
            List[AgentProfile]: 创建的Agent列表
        """
        agents = []
        for persona in personas:
            for i in range(count_per_persona):
                agent = self.create_agent(
                    persona=persona,
                    condition=condition,
                    agent_index=i,
                    is_test_subject=is_test_subject,
                )
                agents.append(agent)
        
        return agents
    
    def create_experiment_design(self) -> Dict[str, List[AgentProfile]]:
        """
        根据配置创建完整的实验设计
        
        生成实验矩阵：条件 × 个性 × 重复数
        对于P3条件，还会处理多Agent互动
        
        Returns:
            Dict[str, List[AgentProfile]]: 按条件分类的Agent列表
        """
        agents_by_condition = {}
        
        for condition in self.config.conditions:
            # 为每个条件创建多个Agent
            # P1和P2：每个个性20个Agent
            # P3：同样20个Agent，但会进行互动
            
            is_test_subject = condition in ["independent", "low_feedback"]
            agents = self.batch_create_agents(
                personas=self.config.personas,
                condition=condition,
                count_per_persona=self.config.repeats_per_cell,
                is_test_subject=is_test_subject,
            )
            agents_by_condition[condition] = agents
        
        return agents_by_condition


class AgentState:
    """Agent 状态管理"""
    
    def __init__(self, agent_profile: AgentProfile):
        """
        初始化Agent状态
        
        Args:
            agent_profile: Agent配置
        """
        self.agent_id = agent_profile.agent_id
        self.persona = agent_profile.persona
        self.condition = agent_profile.condition
        self.activity_level = agent_profile.activity_level
        
        # 初始化行为状态
        # 所有Agent统一从NCI=2.0(完全中立)开始
        self.current_nci = 2.0  # 负面信息选择指数
        self.stance_history = [2.0]  # 立场历史记录，用于计算SCM
        
        # 初始化LLM系统提示词
        self.system_message = build_system_message(self.persona)
    
    def update_nci(self, new_nci: float) -> None:
        """
        更新Agent的NCI(负面信息选择指数)
        
        Args:
            new_nci: 新的NCI值(0-4)
        """
        if not (0 <= new_nci <= 4):
            raise ValueError(f"NCI值必须在0-4之间，但得到{new_nci}")
        
        self.current_nci = new_nci
        self.stance_history.append(new_nci)
    
    def get_stance_change_magnitude(self) -> float:
        """
        获取相邻时刻的立场变化幅度(SCM)
        
        Returns:
            float: |NCI_current - NCI_previous|
        """
        if len(self.stance_history) < 2:
            return 0.0
        
        return abs(self.stance_history[-1] - self.stance_history[-2])
    
    def to_dict(self) -> Dict:
        """将Agent状态转换为字典"""
        return {
            "agent_id": self.agent_id,
            "persona_name": self.persona.name,
            "persona_type": self.persona.persona_type,
            "condition": self.condition,
            "current_nci": self.current_nci,
            "stance_history": self.stance_history,
            "activity_level": self.activity_level,
        }


class ModelManager:
    """模型管理器，封装LLM调用接口"""
    
    def __init__(self, config: ExperimentConfig):
        """
        初始化模型管理器
        
        Args:
            config: 实验配置
        """
        self.config = config
        self.model_name = config.model_name
        self.api_style = config.api_style
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
    
    async def generate_decision(
        self,
        system_message: str,
        prompt: str,
        **kwargs
    ) -> str:
        """
        异步调用LLM生成决策
        
        Args:
            system_message: 系统提示词
            prompt: 用户提示词
            **kwargs: 其他参数
            
        Returns:
            str: LLM的响应(应为JSON格式)
        """
        # 注意：实际的API调用应根据api_style决定
        # - zhipu: 使用智谱GLM API
        # - openai: 使用OpenAI API
        # 这里为框架示例，实际实现需要集成具体API库
        
        raise NotImplementedError(
            f"ModelManager.generate_decision 需要集成 {self.api_style} API"
        )


class ExperimentMatrix:
    """实验矩阵管理器"""
    
    def __init__(self, config: ExperimentConfig):
        """
        初始化实验矩阵
        
        Args:
            config: 实验配置
        """
        self.config = config
        self.factory = AgentFactory(config, random_seed=config.random_seed)
    
    def get_design_summary(self) -> Dict:
        """
        获取实验设计摘要
        
        Returns:
            Dict: 包含实验规模信息
        """
        num_conditions = len(self.config.conditions)
        num_personas = len(self.config.personas)
        num_scenarios = len(self.config.scenarios)
        repeats = self.config.repeats_per_cell
        
        # 气候类型数
        num_climates = len(self.config.low_feedback_climates)  # 假设两个条件气候数相同
        
        total_combinations = num_conditions * num_personas * num_scenarios * num_climates
        total_agents = total_combinations * repeats
        
        return {
            "num_conditions": num_conditions,
            "num_personas": num_personas,
            "num_scenarios": num_scenarios,
            "num_climates": num_climates,
            "repeats_per_cell": repeats,
            "total_combinations": total_combinations,
            "total_agents": total_agents,
            "condition_list": list(self.config.conditions),
            "persona_list": [p.name for p in self.config.personas],
            "scenario_list": [s.name for s in self.config.scenarios],
        }
    
    def create_all_agents(self) -> Dict[str, List[AgentProfile]]:
        """
        创建所有实验条件下的Agent
        
        Returns:
            Dict[str, List[AgentProfile]]: 按条件分类的Agent
        """
        return self.factory.create_experiment_design()


def initialize_agent_states(
    agents: List[AgentProfile],
) -> Dict[str, AgentState]:
    """
    初始化Agent的状态管理对象
    
    Args:
        agents: AgentProfile列表
        
    Returns:
        Dict[str, AgentState]: 按agent_id索引的AgentState字典
    """
    agent_states = {}
    for agent_profile in agents:
        state = AgentState(agent_profile)
        agent_states[agent_profile.agent_id] = state
    
    return agent_states


if __name__ == "__main__":
    # 示例用法
    from .config import load_config
    
    config = load_config("experiment_config.yaml")
    
    # 1. 创建Agent工厂
    factory = AgentFactory(config)
    
    # 2. 获取实验设计摘要
    matrix = ExperimentMatrix(config)
    summary = matrix.get_design_summary()
    print("实验设计摘要:")
    print(f"  总Agent数: {summary['total_agents']}")
    print(f"  条件数: {summary['num_conditions']}")
    print(f"  个性数: {summary['num_personas']}")
    print(f"  场景数: {summary['num_scenarios']}")
    
    # 3. 创建所有Agent
    agents_by_condition = matrix.create_all_agents()
    for condition, agents in agents_by_condition.items():
        print(f"{condition}: {len(agents)} agents")
        # 初始化状态
        states = initialize_agent_states(agents)
        print(f"  已初始化状态: {len(states)} 个")
