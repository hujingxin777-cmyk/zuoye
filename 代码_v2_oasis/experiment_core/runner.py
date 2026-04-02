"""
实验执行引擎 (runner.py)

负责异步执行完整的实验流程，包括Agent决策收集和结果保存
"""

import asyncio
import uuid
import random
import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path

from .config import ExperimentConfig
from .schemas import (
    Scenario,
    Persona,
    ConditionName,
    ExperimentRecord,
    AgentProfile,
)
from .modeling import (
    AgentFactory,
    AgentState,
    ExperimentMatrix,
    initialize_agent_states,
)
from .prompts import build_system_message, build_prompt
from .coding import DecisionEncoder, LLMResponseParser
from .io_utils import ExperimentResultWriter, ExperimentLogger
from .oasis_bridge import get_oasis_reddit_action_names, local_action_alias_from_oasis
from .p3_oasis_like import (
    OasisLikeForumEnv,
    P3ActionEvent,
    ManualActionLike,
    to_manual_action_like,
)


def _climate_label(climate: str) -> str:
    """将氛围类型映射为可读标签。"""
    mapping = {
        "none": "中性基线（none）",
        "positive_leaning": "偏正向氛围（positive_leaning）",
        "negative_leaning": "偏负向氛围（negative_leaning）",
    }
    return mapping.get(climate, f"未定义氛围（{climate}）")


_OASIS_AVAILABLE, _OASIS_REDDIT_ACTIONS = get_oasis_reddit_action_names()


def _normalize_planned_action(action: str) -> str:
    """对齐动作名；若安装了 OASIS 包则参考其动作集合。"""

    action = (action or "observe").strip().lower()
    local_allowed = {"post_comment", "reply", "like", "repost", "observe"}
    if action in local_allowed:
        return action

    # 兼容 OASIS 中常见动作名称
    alias = local_action_alias_from_oasis()
    if action in alias:
        return alias[action]

    if action in _OASIS_REDDIT_ACTIONS:
        return alias.get(action, "observe")

    return "observe"


def _fallback_forum_comment(climate: str, timestep: int, is_reply: bool = False) -> str:
    """为P3生成更像论坛的新观点评论，减少空洞互回。"""
    base = {
        "none": [
            "我补充个观察：不同年龄段恢复速度差异挺明显。",
            "从信息完整性看，样本来源和时间窗口都还不够。",
            "先看连续几天趋势，比看单日更稳妥。",
        ],
        "positive_leaning": [
            "补一个角度：多数案例可控，但个体差异不能忽视。",
            "我倾向先看医院端连续数据，不被标题牵着走。",
            "短期波动不等于失控，先按证据更新判断。",
        ],
        "negative_leaning": [
            "我想补充：就诊压力上升可能意味着低估了传播强度。",
            "从家长反馈看，恢复周期拉长值得继续追踪。",
            "如果后续数据仍走高，风险判断可能要上调。",
        ],
    }
    candidates = base.get(climate, base["none"])
    text = random.choice(candidates)
    prefix = "我补充一点：" if is_reply else ""
    return f"{prefix}{text}（t={timestep}）"


class ExperimentRunner:
    """
    主实验执行器
    
    负责：
    1. 创建实验Agent
    2. 为每个Agent生成提示词
    3. 调用LLM获得决策
    4. 编码决策为指标
    5. 保存结果
    """
    
    def __init__(
        self,
        config: ExperimentConfig,
        output_dir: Path,
    ):
        """
        初始化实验运行器
        
        Args:
            config: 实验配置
            output_dir: 结果输出目录
        """
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化日志和结果写入器
        self.logger = ExperimentLogger(self.output_dir / "experiment.log")
        self.result_writer = ExperimentResultWriter(self.output_dir)
        
        # 初始化其他组件
        self.matrix = ExperimentMatrix(config)
        self.encoder = DecisionEncoder()
        self.parser = LLMResponseParser()
        
        # 记录实验参数
        summary = self.matrix.get_design_summary()
        self.logger.info("实验初始化", summary)

        # 声明 OASIS 调用状态（可用于排查动作空间对齐问题）
        self.logger.info(
            "OASIS桥接状态",
            {
                "oasis_available": _OASIS_AVAILABLE,
                "oasis_reddit_actions_count": len(_OASIS_REDDIT_ACTIONS),
            },
        )
        
        self.total_agents = summary["total_agents"]
        self.processed_agents = 0
    
    async def run_experiment(self) -> None:
        """
        执行完整的实验流程
        
        步骤：
        1. 创建所有Agent
        2. 遍历所有场景×条件×个性×气候组合
        3. 为每个Agent生成决策
        4. 保存结果
        """
        self.logger.info("开始实验执行")
        
        try:
            # 创建所有Agent
            agents_by_condition = self.matrix.create_all_agents()
            self.logger.info(
                "Agent创建完成",
                {
                    "条件数": len(agents_by_condition),
                    "总Agent数": sum(len(a) for a in agents_by_condition.values()),
                }
            )
            
            # 遍历每个场景
            for scenario in self.config.scenarios:
                await self._run_scenario(scenario, agents_by_condition)
            
            # 完成写入
            self.result_writer.finalize()
            self.logger.info(
                "实验执行完成",
                {
                    "处理Agent数": self.processed_agents,
                    "目标Agent数": self.total_agents,
                }
            )
            
        except Exception as e:
            self.logger.error(f"实验执行出错: {str(e)}")
            raise
    
    async def _run_scenario(
        self,
        scenario: Scenario,
        agents_by_condition: Dict[str, List[AgentProfile]],
    ) -> None:
        """
        执行单个场景的所有条件组合
        
        Args:
            scenario: 实验场景
            agents_by_condition: 按条件分类的Agent
        """
        self.logger.info(f"开始场景: {scenario.name}")
        
        for condition in self.config.conditions:
            await self._run_condition(
                scenario=scenario,
                condition=condition,
                agents=agents_by_condition.get(condition, []),
            )
    
    async def _run_condition(
        self,
        scenario: Scenario,
        condition: ConditionName,
        agents: List[AgentProfile],
    ) -> None:
        """
        执行单个条件下的所有Agent
        
        Args:
            scenario: 实验场景
            condition: 实验条件(P1/P2/P3)
            agents: 该条件下的所有Agent
        """
        # 获取该条件的气候类型
        if condition == "low_feedback":
            climates = self.config.low_feedback_climates
        elif condition == "high_interaction":
            climates = self.config.high_interaction_climates
        else:
            climates = ["none"]  # P1没有气候差异

        if condition == "high_interaction":
            groups = self._build_high_interaction_groups(agents)
            for repeat_index, group_agents in enumerate(groups):
                for climate in climates:
                    await self._run_climate(
                        scenario=scenario,
                        condition=condition,
                        climate=climate,
                        agents=group_agents,
                        repeat_index=repeat_index,
                    )
            return
        
        # agents 已按「每个persona重复 repeats_per_cell 次」创建。
        # 这里按 repeat_index 抽取对应子样本，避免与外层 repeat 循环叠加导致样本量膨胀。
        persona_count = len(self.config.personas)
        repeats = self.config.repeats_per_cell

        for repeat_index in range(self.config.repeats_per_cell):
            repeat_agents: List[AgentProfile] = []

            expected_len = persona_count * repeats
            if len(agents) == expected_len and repeats > 0:
                for persona_idx in range(persona_count):
                    agent_pos = persona_idx * repeats + repeat_index
                    if 0 <= agent_pos < len(agents):
                        repeat_agents.append(agents[agent_pos])
            else:
                # 回退策略：若输入结构不满足预期，保持原逻辑避免中断。
                repeat_agents = agents

            for climate in climates:
                await self._run_climate(
                    scenario=scenario,
                    condition=condition,
                    climate=climate,
                    agents=repeat_agents,
                    repeat_index=repeat_index,
                )

    def _build_high_interaction_groups(self, agents: List[AgentProfile]) -> List[List[AgentProfile]]:
        """构建P3群组：默认9人且三类人格按1:1:1均衡。"""
        if not agents:
            return []

        persona_names = [p.name for p in self.config.personas]
        ratio = getattr(self.config, "high_interaction_persona_ratio", [1] * len(persona_names))
        if len(ratio) != len(persona_names) or any(r <= 0 for r in ratio):
            ratio = [1] * len(persona_names)

        target_group_size = int(getattr(self.config, "high_interaction_agent_count", 9))
        target_group_size = max(len(persona_names), target_group_size)

        ratio_sum = sum(ratio)
        target_counts: Dict[str, int] = {}
        assigned = 0
        for i, name in enumerate(persona_names):
            if i == len(persona_names) - 1:
                cnt = target_group_size - assigned
            else:
                cnt = int(round(target_group_size * ratio[i] / ratio_sum))
                cnt = max(1, cnt)
                assigned += cnt
            target_counts[name] = cnt

        # 修正四舍五入造成的总数偏差
        diff = target_group_size - sum(target_counts.values())
        if diff != 0 and persona_names:
            target_counts[persona_names[-1]] += diff

        buckets: Dict[str, List[AgentProfile]] = {name: [] for name in persona_names}
        for a in agents:
            buckets.setdefault(a.persona.name, []).append(a)

        num_groups = max(1, int(getattr(self.config, "repeats_per_cell", 1)))
        groups: List[List[AgentProfile]] = []

        for _ in range(num_groups):
            group: List[AgentProfile] = []
            for name in persona_names:
                pool = buckets.get(name, [])
                need = max(1, int(target_counts.get(name, 1)))
                if not pool:
                    continue
                if len(pool) >= need:
                    chosen = random.sample(pool, need)
                else:
                    # 不足时有放回补齐，保证比例结构
                    chosen = pool[:] + random.choices(pool, k=need - len(pool))
                group.extend(chosen)

            random.shuffle(group)
            groups.append(group)

        self.logger.info(
            "P3群组构建",
            {
                "group_size": target_group_size,
                "persona_ratio": ratio,
                "num_groups": len(groups),
            },
        )
        return groups
    
    async def _run_climate(
        self,
        scenario: Scenario,
        condition: ConditionName,
        climate: str,
        agents: List[AgentProfile],
        repeat_index: int = 0,
    ) -> None:
        """
        执行单个气候下的所有Agent决策
        
        Args:
            scenario: 实验场景
            condition: 实验条件
            climate: 气候类型
            agents: Agent列表
            repeat_index: 重复索引
        """
        # 初始化所有Agent的状态
        agent_states = initialize_agent_states(agents)
        
        # 为P1和P2条件，使用并发执行多个Agent
        # 为P3条件，使用多轮互动
        
        if condition in ["independent", "low_feedback"]:
            await self._run_parallel_condition(
                scenario=scenario,
                condition=condition,
                climate=climate,
                agent_states=agent_states,
                repeat_index=repeat_index,
            )
        elif condition == "high_interaction":
            await self._run_interactive_condition(
                scenario=scenario,
                condition=condition,
                climate=climate,
                agent_states=agent_states,
                repeat_index=repeat_index,
            )
    
    async def _run_parallel_condition(
        self,
        scenario: Scenario,
        condition: ConditionName,
        climate: str,
        agent_states: Dict[str, AgentState],
        repeat_index: int = 0,
    ) -> None:
        """
        执行P1/P2条件（并行执行）
        
        Args:
            scenario: 场景
            condition: 条件
            climate: 气候
            agent_states: Agent状态字典
            repeat_index: 重复索引
        """
        # 生成社交反馈文本（如果需要）
        social_block = ""
        if condition == "low_feedback":
            social_block = self.config.low_feedback_blocks.get(
                climate, "默认反馈文本"
            )
        
        # 创建并发任务
        tasks = []
        for agent_id, agent_state in agent_states.items():
            task = self._process_single_agent(
                agent_id=agent_id,
                agent_state=agent_state,
                scenario=scenario,
                condition=condition,
                climate=climate,
                repeat_index=repeat_index,
                round_index=1,
                social_block=social_block,
            )
            tasks.append(task)
        
        # 使用信号量控制并发数
        semaphore = asyncio.Semaphore(self.config.concurrency)
        
        async def bounded_task(task):
            async with semaphore:
                return await task
        
        # 执行所有任务
        await asyncio.gather(*[bounded_task(t) for t in tasks])
    
    async def _run_interactive_condition(
        self,
        scenario: Scenario,
        condition: ConditionName,
        climate: str,
        agent_states: Dict[str, AgentState],
        repeat_index: int = 0,
    ) -> None:
        """
        执行P3条件（高互动讨论）
        
                实现要点：
                - 按时间步推进（t=1..T）
                - 每个时间步计算群体指标：GCR、SSA
                - 支持停止条件：
                    1) 达到最大时间步
                    2) 高共识连续出现（GCR >= 阈值，连续N步）
                    3) 讨论停滞（连续N步无新增评论代理信号）
        
        Args:
            scenario: 场景
            condition: 条件
            climate: 气候
            agent_states: Agent状态字典
            repeat_index: 重复索引
        """
        # P3 冷启动：仅给事件背景 + 信息1/2，不注入任何预设评论块
        social_block = ""
        max_timestep = max(1, int(getattr(self.config, "high_interaction_max_timestep", 10)))
        round_index = max(1, int(getattr(self.config, "high_interaction_rounds", 1)))
        consensus_threshold = float(getattr(self.config, "high_consensus_threshold", 0.90))
        consensus_hold_steps = max(1, int(getattr(self.config, "high_consensus_hold_steps", 2)))
        stalled_steps = max(1, int(getattr(self.config, "discussion_stalled_steps", 4)))
        activate_prob = float(getattr(self.config, "high_interaction_activate_prob", 0.8))
        activate_prob = max(0.05, min(1.0, activate_prob))
        step_timeout_seconds = float(getattr(self.config, "high_interaction_step_timeout_seconds", 120.0))
        reply_cooldown = max(0, int(getattr(self.config, "high_interaction_reply_cooldown", 1)))
        max_visible_events = max(6, int(getattr(self.config, "high_interaction_max_visible_events", 18)))

        consecutive_high_consensus = 0
        consecutive_stalled = 0
        previous_comment_events: Optional[int] = None
        forum_env = OasisLikeForumEnv(climate=climate, seed_block=social_block)
        pair_last_timestep: Dict[tuple[str, str], int] = {}
        agent_last_action: Dict[str, str] = {}
        agent_recent_actions: Dict[str, List[str]] = {}

        # 为P3构建persona分组，保证每个时间步激活时仍尽量保持类型均衡
        persona_buckets: Dict[str, List[str]] = {}
        for aid, state in agent_states.items():
            persona_buckets.setdefault(state.persona.name, []).append(aid)

        for timestep in range(1, max_timestep + 1):
            t1_hint = ""
            if timestep == 1:
                t1_hint = "[实验操纵] 这是讨论输入端（t=1），请先基于当前氛围建立初始判断。\n"

            dynamic_tail = forum_env.recent_updates_text(max_visible_events)
            round_social_block = (
                f"[实验操纵] 当前讨论氛围：{_climate_label(climate)}\n"
                f"{t1_hint}"
                f"{social_block}\n\n"
                f"[线程增量｜最近互动]\n{dynamic_tail}\n\n"
                f"[系统提示] 当前为第{timestep}个时间步，请结合已有讨论趋势继续作答。"
            )

            # 每个时间步按persona分层激活，减少同步噪声并保留异步并发
            active_agent_ids: List[str] = []
            for _, ids in persona_buckets.items():
                local_ids = ids[:]
                random.shuffle(local_ids)
                k = max(1, int(round(len(local_ids) * activate_prob)))
                k = min(k, len(local_ids))
                active_agent_ids.extend(local_ids[:k])

            if not active_agent_ids:
                active_agent_ids = [random.choice(list(agent_states.keys()))]

            tasks = []
            for agent_id in active_agent_ids:
                agent_state = agent_states[agent_id]
                task = self._process_single_agent(
                    agent_id=agent_id,
                    agent_state=agent_state,
                    scenario=scenario,
                    condition=condition,
                    climate=climate,
                    repeat_index=repeat_index,
                    round_index=round_index,
                    timestep=timestep,
                    social_block=round_social_block,
                    write_record=False,
                )
                tasks.append(task)

            semaphore = asyncio.Semaphore(self.config.concurrency)

            async def bounded_task(task):
                async with semaphore:
                    return await task

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*[bounded_task(t) for t in tasks], return_exceptions=True),
                    timeout=step_timeout_seconds,
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    "P3时间步超时",
                    {
                        "scenario": scenario.name,
                        "climate": climate,
                        "repeat_index": repeat_index,
                        "timestep": timestep,
                        "active_agents": len(active_agent_ids),
                        "timeout_seconds": step_timeout_seconds,
                    },
                )
                continue

            # 清理任务异常，保留成功结果
            filtered_results: List[Optional[Dict[str, Any]]] = []
            for r in results:
                if isinstance(r, Exception):
                    self.logger.warning(f"P3 agent任务异常: {str(r)}")
                    continue
                filtered_results.append(r)

            valid_results = [r for r in filtered_results if r is not None]
            if not valid_results:
                continue

            nci_values = [float(r["negative_choice_index"]) for r in valid_results]
            total = len(nci_values)
            positive_advocates = sum(1 for v in nci_values if v < 1.5)
            negative_advocates = sum(1 for v in nci_values if v > 2.5)
            gcr = max(positive_advocates / total, negative_advocates / total)

            like_pos = sum(1 for r in valid_results if r.get("like_choice") == "positive")
            like_neg = sum(1 for r in valid_results if r.get("like_choice") == "negative")
            comment_pos = sum(1 for r in valid_results if r.get("comment_choice") == "support_positive")
            comment_neg = sum(1 for r in valid_results if r.get("comment_choice") == "support_negative")

            social_plus = max(1, like_pos + comment_pos)
            social_minus = max(1, like_neg + comment_neg)
            ssa = abs((social_plus / social_minus) - 1.0)

            comment_events = 0
            reply_quota = max(1, int(round(len(valid_results) * 0.35)))
            min_new_post_quota = max(1, int(round(len(valid_results) * 0.40)))
            reply_count = 0
            new_post_count = 0
            reply_target_counter: Counter[str] = Counter()
            used_comment_texts: set[str] = set()

            step_events: List[P3ActionEvent] = []

            for idx, result in enumerate(valid_results):
                aid = str(result.get("agent_id", ""))
                action = _normalize_planned_action(
                    str(result.get("planned_action", "observe") or "observe")
                )
                recent_actions = agent_recent_actions.get(aid, [])

                # 借鉴 OASIS 的动作多样化原则：避免个体持续重复单一动作
                if agent_last_action.get(aid) == action and action in {"post_comment", "reply"}:
                    action = "observe"

                # 防止连续回复导致互回回路：若近期已回复过，优先改为发新评论
                if action == "reply" and recent_actions[-2:].count("reply") >= 1:
                    action = "post_comment"

                public_comment = str(result.get("public_comment", "") or "").strip()
                if len(public_comment) > 40:
                    public_comment = public_comment[:40]

                reply_target = str(result.get("reply_target", "none") or "none").strip()
                all_targets = [x for x in agent_states.keys() if x != aid]

                if action == "reply":
                    if reply_target == "none" or reply_target == aid or reply_target not in agent_states:
                        action = "post_comment"
                    else:
                        # 时间步级别限制：避免大量回复涌向同一用户
                        if reply_target_counter[reply_target] >= 1:
                            action = "post_comment"

                    # 全局回复配额：限制回复比例，鼓励原创发言
                    if action == "reply" and reply_count >= reply_quota:
                        action = "post_comment"

                # 保证每步有足够“新观点评论”
                remaining = len(valid_results) - idx
                needed_new_posts = max(0, min_new_post_quota - new_post_count)
                if action in {"observe", "like", "repost"} and needed_new_posts >= remaining:
                    action = "post_comment"

                if action == "reply":
                    # 回复冷却：限制A↔B短周期来回
                        pair = tuple(sorted([aid, reply_target]))
                        last_ts = pair_last_timestep.get(pair, -999)
                        if timestep - last_ts <= reply_cooldown:
                            action = "post_comment"
                        else:
                            pair_last_timestep[pair] = timestep
                            reply_target_counter[reply_target] += 1
                            reply_count += 1

                if action in {"reply", "post_comment"}:
                    if len(public_comment) < 8:
                        public_comment = _fallback_forum_comment(
                            climate=climate,
                            timestep=timestep,
                            is_reply=(action == "reply"),
                        )

                    # 同一步去重，避免多人复读同句
                    if public_comment in used_comment_texts:
                        public_comment = _fallback_forum_comment(
                            climate=climate,
                            timestep=timestep,
                            is_reply=(action == "reply"),
                        )
                    used_comment_texts.add(public_comment)

                if action == "reply":
                    step_events.append(
                        P3ActionEvent(
                            agent_id=aid,
                            action="reply",
                            reply_target=reply_target,
                            public_comment=public_comment,
                        )
                    )
                elif action == "post_comment":
                    step_events.append(
                        P3ActionEvent(
                            agent_id=aid,
                            action="post_comment",
                            reply_target="none",
                            public_comment=public_comment,
                        )
                    )
                    new_post_count += 1
                elif action == "like":
                    step_events.append(
                        P3ActionEvent(
                            agent_id=aid,
                            action="like",
                            reply_target=reply_target,
                            public_comment="",
                        )
                    )
                elif action == "repost":
                    step_events.append(
                        P3ActionEvent(
                            agent_id=aid,
                            action="repost",
                            reply_target=reply_target,
                            public_comment="",
                        )
                    )
                else:
                    step_events.append(
                        P3ActionEvent(
                            agent_id=aid,
                            action="observe",
                            reply_target="none",
                            public_comment="",
                        )
                    )

                agent_last_action[aid] = action
                agent_recent_actions.setdefault(aid, []).append(action)
                if len(agent_recent_actions[aid]) > 3:
                    agent_recent_actions[aid] = agent_recent_actions[aid][-3:]
                result["planned_action"] = action

            # Oasis-like: 每个时间步统一提交动作并更新环境
            step_actions: Dict[str, ManualActionLike] = {
                e.agent_id: to_manual_action_like(e)
                for e in step_events
            }
            step_stats = forum_env.step(
                actions=step_actions,
                all_agent_ids=list(agent_states.keys()),
            )
            comment_events = int(step_stats.get("comment_events", 0))

            if previous_comment_events is not None and comment_events <= previous_comment_events:
                consecutive_stalled += 1
            else:
                consecutive_stalled = 0
            previous_comment_events = comment_events

            if gcr >= consensus_threshold:
                consecutive_high_consensus += 1
            else:
                consecutive_high_consensus = 0

            should_stop = False
            stop_reason: Optional[str] = None
            if consecutive_high_consensus >= consensus_hold_steps:
                should_stop = True
                stop_reason = "high_consensus"
            elif consecutive_stalled >= stalled_steps:
                should_stop = True
                stop_reason = "discussion_stalled"
            elif timestep >= max_timestep:
                should_stop = True
                stop_reason = "max_timestep"

            for result in valid_results:
                record = result["record"]
                record.group_consensus_ratio = gcr
                record.social_signal_asymmetry = ssa
                record.is_stop_step = should_stop
                record.stop_reason = stop_reason if should_stop else None
                record.p3_is_higher_order_event = True
                record.p3_event_order = timestep
                record.p3_event_id = (
                    f"{scenario.name}|{climate}|r{repeat_index}|t{timestep}"
                )
                record.p3_participants_set = json.dumps(
                    sorted(active_agent_ids), ensure_ascii=False
                )
                record.p3_copresence_size = len(active_agent_ids)

                self.result_writer.add_record(record)
                self.processed_agents += 1
                if self.processed_agents % 50 == 0:
                    self.logger.info(
                        f"已处理 {self.processed_agents}/{self.total_agents} 个Agent"
                    )

            self.logger.info(
                "P3时间步完成",
                {
                    "scenario": scenario.name,
                    "climate": climate,
                    "repeat_index": repeat_index,
                    "timestep": timestep,
                    "active_agents": len(active_agent_ids),
                    "total_agents": len(agent_states),
                    "gcr": round(gcr, 4),
                    "ssa": round(ssa, 4),
                    "comment_events": comment_events,
                    "should_stop": should_stop,
                    "stop_reason": stop_reason,
                },
            )

            if should_stop:
                break
    
    async def _process_single_agent(
        self,
        agent_id: str,
        agent_state: AgentState,
        scenario: Scenario,
        condition: ConditionName,
        climate: str,
        repeat_index: int = 0,
        round_index: int = 1,
        timestep: int = 1,
        social_block: str = "",
        write_record: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个Agent的完整流程
        
        Args:
            agent_id: Agent ID
            agent_state: Agent状态
            scenario: 场景
            condition: 条件
            climate: 气候
            repeat_index: 重复索引
            round_index: 互动轮次
            timestep: 时间步
            social_block: 社交反馈文本
            write_record: 是否立即写入结果
        """
        try:
            def _extract_extra_fields(raw: str) -> Dict[str, Any]:
                try:
                    d = json.loads(raw)
                except Exception:
                    m = re.search(r"\{.*\}", raw, re.DOTALL)
                    if not m:
                        return {}
                    try:
                        d = json.loads(m.group(0))
                    except Exception:
                        return {}
                planned_action = _normalize_planned_action(
                    str(d.get("planned_action", "observe") or "observe")
                )

                try:
                    gcp = int(d.get("group_consensus_perception", 50))
                except Exception:
                    gcp = 50
                gcp = max(0, min(100, gcp))

                return {
                    "public_comment": str(d.get("public_comment", "")).strip(),
                    "private_reason": str(d.get("private_reason", "")).strip(),
                    "planned_action": planned_action,
                    "reply_target": str(d.get("reply_target", "none")).strip(),
                    "group_consensus_perception": gcp,
                }

            # 1. 生成提示词
            system_message = agent_state.system_message
            prompt = build_prompt(
                scenario=scenario,
                condition=condition,
                climate_type=climate,
                info1_polarity="negative",  # 默认：信息1是负向的
                config=self.config,
                social_block=social_block,
                include_reason=(condition != "high_interaction"),
            )
            
            # 2. 调用LLM（这里需要实际实现LLM调用）
            # 目前使用Mock响应用于演示
            response_text, model_name_used, model_api_style_used = await self._call_llm(
                system_message,
                prompt,
                route_key=agent_id,
            )
            
            # 3. 解析响应
            decision = self.parser.parse_json_response(response_text)
            extra_fields = _extract_extra_fields(response_text)
            if decision is None:
                self.logger.warning(f"无法解析Agent {agent_id}的响应，使用默认决策")
                # 降级方案：使用中立的默认响应
                # 根据论文设计，credible_choice可以是positive/neutral/negative
                from .schemas import DecisionResponse
                decision = DecisionResponse(
                    credible_choice="neutral",
                    like_choice="none",
                    share_choice="none",
                    comment_choice="neutral",
                    reason="自动系统：无法解析响应"
                )
                extra_fields = {
                    "public_comment": "",
                    "private_reason": "自动系统：无法解析响应",
                    "planned_action": "observe",
                    "reply_target": "none",
                    "group_consensus_perception": 50,
                }
            
            # 4. 编码决策
            metrics = self.encoder.encode_decision(
                decision,
                previous_nci=agent_state.current_nci,
            )
            
            # 5. 更新Agent状态
            agent_state.update_nci(metrics["negative_choice_index"])
            
            # 6. 创建实验记录
            record = ExperimentRecord(
                run_id=str(uuid.uuid4()),
                agent_id=agent_id,
                scenario_name=scenario.name,
                condition_name=condition,
                persona_name=agent_state.persona.name,
                climate_type=climate,
                repeat_index=repeat_index,
                round_index=round_index,
                timestep=timestep,
                info1_polarity="negative",
                info2_polarity="positive",
                # 输出与编码
                model_name_used=model_name_used,
                model_api_style_used=model_api_style_used,
                credible_choice=decision.credible_choice,
                like_choice=decision.like_choice,
                share_choice=decision.share_choice,
                comment_choice=decision.comment_choice,
                reason=(decision.reason or "模型未提供理由") if condition != "high_interaction" else None,
                public_comment=extra_fields.get("public_comment") if condition == "high_interaction" else None,
                private_reason=(extra_fields.get("private_reason") or decision.reason or "模型未提供理由") if condition == "high_interaction" else None,
                planned_action=extra_fields.get("planned_action") if condition == "high_interaction" else None,
                reply_target=extra_fields.get("reply_target") if condition == "high_interaction" else None,
                group_consensus_perception=extra_fields.get("group_consensus_perception") if condition == "high_interaction" else None,
                # 编码指标
                negative_choice_index=int(metrics.get("negative_choice_index", 0)),
                negative_choice_intensity=metrics.get("negative_choice_intensity"),
                content_score=metrics.get("content_score"),
                social_score=metrics.get("social_score"),
                group_score=metrics.get("group_score"),
                stance=metrics.get("stance"),
                persuasion_effect_score=metrics.get("persuasion_effect_score"),
                stance_change_magnitude=metrics.get("stance_change_magnitude"),
                credibility_negative=int(metrics.get("credibility_negative", 0)),
                like_negative=int(metrics.get("like_negative", 0)),
                share_negative=int(metrics.get("share_negative", 0)),
                comment_negative=int(metrics.get("comment_negative", 0)),
                # 元数据
                status="ok",
                error_message=None,
                raw_response=None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
            if write_record:
                # 7. 保存结果
                self.result_writer.add_record(record)
                
                # 更新计数
                self.processed_agents += 1
                if self.processed_agents % 50 == 0:
                    self.logger.info(
                        f"已处理 {self.processed_agents}/{self.total_agents} 个Agent"
                    )
                return None

            return {
                "agent_id": agent_id,
                "record": record,
                "negative_choice_index": int(metrics.get("negative_choice_index", 0)),
                "like_choice": decision.like_choice,
                "comment_choice": decision.comment_choice,
                "planned_action": extra_fields.get("planned_action", "observe"),
                "public_comment": extra_fields.get("public_comment", ""),
                "reply_target": extra_fields.get("reply_target", "none"),
                "group_consensus_perception": extra_fields.get("group_consensus_perception", 50),
            }
            
        except Exception as e:
            self.logger.error(f"处理Agent {agent_id}出错: {str(e)}")
            return None
    
    async def _call_llm(
        self,
        system_message: str,
        prompt: str,
        route_key: Optional[str] = None,
    ) -> tuple[str, Optional[str], Optional[str]]:
        """
        调用LLM获得决策响应
        
        Args:
            system_message: 系统提示词
            prompt: 用户提示词
            
        Returns:
            tuple[str, Optional[str], Optional[str]]:
                (LLM的JSON响应, 实际模型名, API风格)
        """
        from .llm_client import LLMClient
        
        try:
            # 初始化LLM客户端
            if not hasattr(self, 'llm_client'):
                self.llm_client = LLMClient(self.config)

            model_cfg = self.llm_client.choose_model(route_key=route_key)
            
            # 调用LLM API
            response = await self.llm_client.call(
                system_message,
                prompt,
                route_key=route_key,
                model_override=model_cfg,
            )
            return response, model_cfg.name, model_cfg.api_style
            
        except Exception as e:
            self.logger.error(f"LLM API调用失败: {str(e)}")
            # 如果API调用失败，返回默认响应
            import json
            default_response = {
                "credible_choice": "neutral",
                "like_choice": "none",
                "share_choice": "none",
                "comment_choice": "neutral",
                "reason": "API调用失败，系统未能获得决策",
                "planned_action": "observe",
                "reply_target": "none",
                "group_consensus_perception": 50,
                "public_comment": "",
                "private_reason": "API调用失败，系统未能获得决策",
            }
            return json.dumps(default_response), None, None


async def run_full_experiment(config: ExperimentConfig, output_dir: Path) -> None:
    """
    运行完整的实验
    
    Args:
        config: 实验配置
        output_dir: 输出目录
    """
    runner = ExperimentRunner(config, output_dir)
    await runner.run_experiment()


if __name__ == "__main__":
    import asyncio
    from .config import load_config
    
    # 加载配置
    config = load_config("experiment_config.yaml")
    
    # 运行实验
    asyncio.run(run_full_experiment(config, Path("./outputs")))
