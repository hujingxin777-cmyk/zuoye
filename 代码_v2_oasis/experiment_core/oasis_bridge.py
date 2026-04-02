"""OASIS 桥接模块：用于声明并复用 OASIS 动作集合。"""

from __future__ import annotations

from typing import Tuple, Set


def get_oasis_reddit_action_names() -> tuple[bool, set[str]]:
    """
    获取 OASIS Reddit 默认动作名（小写）。

    Returns:
        (is_available, action_names)
    """
    try:
        from oasis import ActionType  # type: ignore

        actions = ActionType.get_default_reddit_actions()
        names: set[str] = set()
        for a in actions:
            # ActionType 枚举通常有 value，如 "create_post"
            v = getattr(a, "value", None)
            if isinstance(v, str):
                names.add(v.strip().lower())
            else:
                names.add(str(a).strip().lower())

        return True, names
    except Exception:
        return False, set()


def local_action_alias_from_oasis() -> dict[str, str]:
    """OASIS 动作到本项目 P3 动作空间的映射。"""
    return {
        "create_post": "post_comment",
        "create_comment": "post_comment",
        "do_nothing": "observe",
        "refresh": "observe",
        "trend": "observe",
        "search_posts": "observe",
        "search_user": "observe",
        "like_post": "like",
        "like_comment": "like",
        "repost": "repost",
        "quote_post": "repost",
    }
