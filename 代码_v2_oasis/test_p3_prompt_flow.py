"""
P3 提示词与回复流程测试脚本（单场景 × 三氛围）。

用途：
1) 查看每个氛围下发送给模型的完整 P3 prompt（system + user）
2) 调用现有 LLMClient 获取真实回复
3) 解析结构化字段并保存到测试文件

运行示例：
python3 test_p3_prompt_flow.py
python3 test_p3_prompt_flow.py --persona risk_sensitive
python3 test_p3_prompt_flow.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from experiment_core.config import load_config
from experiment_core.env_utils import load_env_file
from experiment_core.prompts import build_system_message, build_prompt
from experiment_core.coding import LLMResponseParser
from experiment_core.llm_client import LLMClient
from experiment_core.oasis_bridge import (
    get_oasis_reddit_action_names,
    local_action_alias_from_oasis,
)
from experiment_core.p3_oasis_like import OasisLikeForumEnv, P3ActionEvent, to_manual_action_like


def _normalize_action(action: str, oasis_actions: set[str]) -> str:
    action = (action or "observe").strip().lower()
    local_allowed = {"post_comment", "reply", "like", "repost", "observe"}
    if action in local_allowed:
        return action

    alias = local_action_alias_from_oasis()
    if action in alias:
        return alias[action]
    if action in oasis_actions:
        return alias.get(action, "observe")
    return "observe"


def _safe_int(v: Any, default: int = 50, low: int = 0, high: int = 100) -> int:
    try:
        iv = int(v)
    except Exception:
        iv = default
    return max(low, min(high, iv))


def _extract_p3_fields(raw: str) -> Dict[str, Any]:
    """从模型原始输出中提取 P3 扩展字段。"""
    try:
        data = json.loads(raw)
    except Exception:
        import re

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {
                "planned_action": "observe",
                "reply_target": "none",
                "group_consensus_perception": 50,
                "public_comment": "",
                "private_reason": "",
            }
        try:
            data = json.loads(m.group(0))
        except Exception:
            return {
                "planned_action": "observe",
                "reply_target": "none",
                "group_consensus_perception": 50,
                "public_comment": "",
                "private_reason": "",
            }

    return {
        "planned_action": str(data.get("planned_action", "observe") or "observe"),
        "reply_target": str(data.get("reply_target", "none") or "none"),
        "group_consensus_perception": _safe_int(data.get("group_consensus_perception", 50), default=50),
        "public_comment": str(data.get("public_comment", "") or ""),
        "private_reason": str(data.get("private_reason", "") or ""),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="P3 完整回复流程测试（肺炎场景，三氛围）")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "experiment_config.yaml",
        help="配置文件路径",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="mycoplasma_pneumonia",
        help="场景名（默认 mycoplasma_pneumonia）",
    )
    parser.add_argument(
        "--persona",
        type=str,
        default="risk_sensitive",
        help="个性名（默认 risk_sensitive）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印 prompt，不调用模型",
    )
    parser.add_argument(
        "--simulate-p3",
        action="store_true",
        help="启用修改后P3仿真测试（OASIS-like step）",
    )
    parser.add_argument(
        "--agents",
        type=int,
        default=6,
        help="P3仿真测试参与agent数量（默认6）",
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=4,
        help="P3仿真测试时间步数量（默认4）",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="额外保存结构化JSON测试结果",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")
    load_env_file(root / ".env.example")
    config = load_config(args.config)

    scenario = next((s for s in config.scenarios if s.name == args.scenario), None)
    if scenario is None:
        raise ValueError(f"未找到场景: {args.scenario}")

    persona = next((p for p in config.personas if p.name == args.persona), None)
    if persona is None:
        raise ValueError(f"未找到个性: {args.persona}")

    climates = ["none", "positive_leaning", "negative_leaning"]
    llm_client = None if args.dry_run else LLMClient(config)

    out_dir = root / "outputs" / "high_interaction_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"p3_prompt_flow_{args.scenario}_{args.persona}_{stamp}.md"

    parser_obj = LLMResponseParser()
    oasis_available, oasis_actions = get_oasis_reddit_action_names()
    structured: Dict[str, Any] = {
        "scenario": args.scenario,
        "persona": args.persona,
        "model": f"{config.model.api_style}/{config.model.name}",
        "dry_run": args.dry_run,
        "simulate_p3": args.simulate_p3,
        "climates": {},
    }

    lines: list[str] = []
    lines.append(f"# P3 完整回复流程测试\n")
    lines.append(f"- 场景: {args.scenario}")
    lines.append(f"- 个性: {args.persona}")
    lines.append(f"- 模型: {config.model.api_style}/{config.model.name}")
    lines.append(f"- 路由策略: {getattr(config, 'model_assignment_strategy', 'single')}")
    lines.append(f"- OASIS包可用: {oasis_available}")
    lines.append(f"- OASIS Reddit动作数: {len(oasis_actions)}")
    lines.append(f"- 时间: {datetime.now().isoformat()}\n")

    lines.append("## OASIS 调用声明\n")
    lines.append("本测试已注入并调用 OASIS 默认 Reddit 动作集合（用于动作空间对齐）。")
    if oasis_actions:
        lines.append("```text")
        lines.append(", ".join(sorted(oasis_actions)))
        lines.append("```\n")

    system_message = build_system_message(persona)

    for climate in climates:
        user_prompt = build_prompt(
            scenario=scenario,
            condition="high_interaction",
            info1_polarity="negative",
            climate_type=climate,
            config=config,
            social_block="",
            include_reason=False,
        )

        lines.append(f"## 氛围: {climate}\n")
        lines.append("### System Prompt")
        lines.append("```text")
        lines.append(system_message)
        lines.append("```\n")

        lines.append("### User Prompt")
        lines.append("```text")
        lines.append(user_prompt)
        lines.append("```\n")

        if args.dry_run:
            lines.append("### Model Response\n")
            lines.append("(dry-run 模式未调用模型)\n")
            structured["climates"][climate] = {
                "raw_response": None,
                "parsed_decision": None,
                "parsed_p3_fields": None,
            }
            continue

        assert llm_client is not None
        response = await llm_client.call(
            system_message=system_message,
            user_message=user_prompt,
            route_key=f"test_{args.persona}_{climate}",
        )

        decision = parser_obj.parse_json_response(response)
        p3_fields = _extract_p3_fields(response)

        lines.append("### Raw Model Response")
        lines.append("```json")
        lines.append(response)
        lines.append("```\n")

        lines.append("### Parsed Decision")
        lines.append("```json")
        lines.append(json.dumps(decision.model_dump() if decision else {"parse": "failed"}, ensure_ascii=False, indent=2))
        lines.append("```\n")

        lines.append("### Parsed P3 Extra Fields")
        lines.append("```json")
        lines.append(json.dumps(p3_fields, ensure_ascii=False, indent=2))
        lines.append("```\n")

        structured["climates"][climate] = {
            "raw_response": response,
            "parsed_decision": decision.model_dump() if decision else None,
            "parsed_p3_fields": p3_fields,
        }

        if args.simulate_p3:
            lines.append("### P3 仿真回放（OASIS-like）")
            forum_env = OasisLikeForumEnv(
                climate=climate,
                seed_block=config.high_interaction_blocks.get(climate, ""),
            )
            max_visible_events = max(6, int(getattr(config, "high_interaction_max_visible_events", 18)))
            agent_ids = [f"agent_{i:03d}" for i in range(max(2, args.agents))]
            sim_steps: list[dict[str, Any]] = []

            for t in range(1, max(1, args.timesteps) + 1):
                step_events: list[P3ActionEvent] = []
                thread_tail = forum_env.recent_updates_text(max_visible_events)
                step_gcp_by_agent: Dict[str, int] = {}

                for aid in agent_ids:
                    if args.dry_run:
                        action = random.choice(["post_comment", "observe", "like", "reply"])
                        target = random.choice([x for x in agent_ids if x != aid]) if action == "reply" else "none"
                        p3 = {
                            "planned_action": action,
                            "reply_target": target,
                            "public_comment": f"{aid} 在 t={t} 的测试观点",
                            "group_consensus_perception": 50,
                        }
                    else:
                        sim_prompt = build_prompt(
                            scenario=scenario,
                            condition="high_interaction",
                            info1_polarity="negative",
                            climate_type=climate,
                            config=config,
                            social_block=(
                                f"[线程增量｜最近互动]\n{thread_tail}"
                            ),
                            include_reason=False,
                        )
                        raw = await llm_client.call(
                            system_message=system_message,
                            user_message=sim_prompt,
                            route_key=f"sim_{climate}_{aid}_t{t}",
                        )
                        p3 = _extract_p3_fields(raw)

                    norm_action = _normalize_action(p3.get("planned_action", "observe"), oasis_actions)
                    target = str(p3.get("reply_target", "none") or "none")
                    step_gcp_by_agent[aid] = _safe_int(p3.get("group_consensus_perception", 50), default=50)
                    if norm_action == "reply" and (target not in agent_ids or target == aid):
                        norm_action = "post_comment"
                        target = "none"

                    step_events.append(
                        P3ActionEvent(
                            agent_id=aid,
                            action=norm_action,
                            reply_target=target,
                            public_comment=str(p3.get("public_comment", "") or ""),
                        )
                    )

                step_actions = {e.agent_id: to_manual_action_like(e) for e in step_events}
                step_stats = forum_env.step(actions=step_actions, all_agent_ids=agent_ids)

                action_counts: Dict[str, int] = {
                    "post_comment": 0,
                    "reply": 0,
                    "like": 0,
                    "repost": 0,
                    "observe": 0,
                }
                reply_targets = set()
                gcp_values: list[int] = []
                for e in step_events:
                    if e.action in action_counts:
                        action_counts[e.action] += 1
                    if e.action == "reply" and e.reply_target not in {"", "none"}:
                        reply_targets.add(e.reply_target)
                    gcp_values.append(step_gcp_by_agent.get(e.agent_id, 50))

                total_actions = max(1, len(step_events))
                reply_ratio = action_counts["reply"] / total_actions
                new_post_ratio = action_counts["post_comment"] / total_actions
                observe_ratio = action_counts["observe"] / total_actions
                avg_gcp = sum(gcp_values) / len(gcp_values) if gcp_values else 50.0

                sim_steps.append(
                    {
                        "timestep": t,
                        "events_count": int(step_stats.get("events_count", 0)),
                        "comment_events": int(step_stats.get("comment_events", 0)),
                        "action_counts": action_counts,
                        "reply_ratio": round(reply_ratio, 4),
                        "new_post_ratio": round(new_post_ratio, 4),
                        "observe_ratio": round(observe_ratio, 4),
                        "unique_reply_targets": len(reply_targets),
                        "avg_group_consensus_perception": round(avg_gcp, 2),
                        "recent_updates": forum_env.recent_updates_text(max_visible_events),
                    }
                )

            lines.append("```json")
            lines.append(json.dumps(sim_steps, ensure_ascii=False, indent=2))
            lines.append("```\n")
            structured["climates"][climate]["simulation_steps"] = sim_steps

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ 已生成测试文件: {out_file}")

    if args.save_json:
        out_json = out_file.with_suffix(".json")
        out_json.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ 已生成结构化结果: {out_json}")


if __name__ == "__main__":
    asyncio.run(main())
