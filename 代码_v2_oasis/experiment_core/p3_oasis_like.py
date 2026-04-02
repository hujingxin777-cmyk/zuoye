"""P3 Oasis-like 社交仿真环境。

目标：参考 OASIS 的 `env.step(actions)` 方式，
将 P3 的线程更新从 runner 逻辑中抽离为独立环境层。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class P3ActionEvent:
    agent_id: str
    action: str
    reply_target: str
    public_comment: str


@dataclass
class ManualActionLike:
    """对齐 OASIS ManualAction 命名（轻量版）。"""

    action_type: str
    action_args: Dict[str, Any]


@dataclass
class LLMActionLike:
    """对齐 OASIS LLMAction 命名（占位版）。"""

    action_type: str = "llm_action"


def to_manual_action_like(event: P3ActionEvent) -> ManualActionLike:
    """将内部事件映射为 OASIS 风格动作结构。"""
    return ManualActionLike(
        action_type=event.action,
        action_args={
            "reply_target": event.reply_target,
            "public_comment": event.public_comment,
        },
    )


class OasisLikeForumEnv:
    """轻量化论坛环境，接口风格对齐 OASIS step。"""

    def __init__(self, climate: str, seed_block: str):
        self.climate = climate
        self.seed_block = seed_block
        self.thread_updates: List[str] = []

    def recent_updates_text(self, max_visible_events: int) -> str:
        if not self.thread_updates:
            return "（暂无）"
        return "\n".join(self.thread_updates[-max_visible_events:])

    def step(
        self,
        actions: Dict[str, ManualActionLike],
        all_agent_ids: List[str],
    ) -> Dict[str, int]:
        """执行一个时间步动作批次，返回事件统计。"""
        comment_events = 0

        for aid, action_obj in actions.items():
            action = (action_obj.action_type or "observe").strip().lower()
            target = str(action_obj.action_args.get("reply_target", "none") or "none")
            text = str(action_obj.action_args.get("public_comment", "") or "").strip()

            if action == "reply":
                line = f"{aid} 回复 {target}：{text or '我补充一点，先看后续数据。'}"
                self.thread_updates.append(line)
                comment_events += 1
            elif action == "post_comment":
                line = f"{aid}：{text or '先补充一个观察点，别急着下结论。'}"
                self.thread_updates.append(line)
                comment_events += 1
            elif action == "like":
                valid_targets = [x for x in all_agent_ids if x != aid]
                t = target if target in valid_targets else (random.choice(valid_targets) if valid_targets else "帖子")
                self.thread_updates.append(f"{aid} 点赞了 {t} 的发言。")
            elif action == "repost":
                valid_targets = [x for x in all_agent_ids if x != aid]
                t = target if target in valid_targets else (random.choice(valid_targets) if valid_targets else "帖子")
                self.thread_updates.append(f"{aid} 转发了 {t} 的观点。")
            else:
                self.thread_updates.append(f"{aid} 继续观察讨论。")

        return {
            "comment_events": comment_events,
            "events_count": len(actions),
        }
