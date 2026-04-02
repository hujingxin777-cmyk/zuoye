"""
程序主入口。

运行实验：python main.py
后处理（可视化）：python main.py --visualize
生成统计摘要：python main.py --stats
"""

import argparse
import asyncio
import importlib
import os
import time
from pathlib import Path
from typing import Optional

from experiment_core.config import load_config
from experiment_core.env_utils import load_env_file
from experiment_core.visualize import ExperimentVisualizer
from experiment_core.io_utils import ExperimentResultReader, ExperimentLogger
from experiment_core.runner import ExperimentRunner


async def run_oasis_deploy(output_dir: Path):
    """运行严格 OASIS 部署流程（统一入口）。"""
    print("\n" + "=" * 60)
    print("运行严格 OASIS 部署模式")
    print("=" * 60)

    oasis = importlib.import_module("oasis")
    ActionType = getattr(oasis, "ActionType")
    LLMAction = getattr(oasis, "LLMAction")
    ManualAction = getattr(oasis, "ManualAction")
    generate_reddit_agent_graph = getattr(oasis, "generate_reddit_agent_graph")

    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType

    script_dir = Path(__file__).resolve().parent
    db_path = output_dir / "oasis_strict_reddit_simulation.db"
    profile_path = script_dir / "data" / "reddit" / "user_data_36.json"

    if not profile_path.exists():
        raise FileNotFoundError(
            f"未找到 OASIS 用户画像文件: {profile_path}\n"
            "请按 OASIS README 准备 profile 数据后再运行。"
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("缺少 OPENAI_API_KEY 环境变量")

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=ModelType.GPT_4O_MINI,
    )

    available_actions = ActionType.get_default_reddit_actions()
    agent_graph = await generate_reddit_agent_graph(
        profile_path=str(profile_path),
        model=model,
        available_actions=available_actions,
    )

    if db_path.exists():
        db_path.unlink()

    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=str(db_path),
    )

    await env.reset()

    actions_1 = {
        env.agent_graph.get_agent(0): ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={
                "content": (
                    "近期多地医院儿科门诊接诊量增加，支原体肺炎相关话题引发讨论。"
                    "有观点认为风险被低估，也有观点认为整体可管理。"
                )
            },
        )
    }
    await env.step(actions_1)

    for _ in range(8):
        actions_t = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}
        await env.step(actions_t)

    await env.close()
    print(f"✓ OASIS 严格部署运行完成，DB: {db_path}")


async def run_experiments(config, output_dir: Path):
    """
    执行实验主流程
    
    Args:
        config: 实验配置对象
        output_dir: 输出目录
    """
    print("\n" + "="*60)
    print("开始执行LLM-Agent负面信息选择实验")
    print("="*60)
    
    # 初始化日志
    logger = ExperimentLogger(output_dir / "experiment.log")
    logger.info("实验开始", {
        "config_plan": config.active_plan,
        "conditions": len(config.conditions),
        "scenarios": len(config.scenarios),
        "personas": len(config.personas)
    })
    
    print(f"✓ 配置已加载")
    print(f"  - 实验方案: {config.active_plan}")
    print(f"  - 模型路由策略: {getattr(config, 'model_assignment_strategy', 'single')}")
    print(f"  - 模型池数量: {len(getattr(config, 'model_pool', [])) or 1}")
    print(f"  - 条件数: {len(config.conditions)} (P1/P2/P3)")
    print(f"  - 场景数: {len(config.scenarios)}")
    print(f"  - 个性数: {len(config.personas)}")
    
    # 计算实验规模（按记录条数估算）
    repeats = getattr(config, 'repeats_per_cell', 1)
    agents_per_condition = len(config.personas) * repeats
    p1_climates = 1
    p2_climates = len(getattr(config, 'low_feedback_climates', []))
    p3_climates = len(getattr(config, 'high_interaction_climates', []))
    p3_timesteps = max(1, int(getattr(config, 'high_interaction_max_timestep', getattr(config, 'high_interaction_rounds', 1))))

    records_per_scenario = (
        agents_per_condition * p1_climates
        + agents_per_condition * p2_climates
        + agents_per_condition * p3_climates * p3_timesteps
    )
    total_records = records_per_scenario * len(config.scenarios)

    print(f"  - 低反馈气候数: {p2_climates}")
    print(f"  - 高互动气候数: {p3_climates}")
    print(f"  - P3时间步: {p3_timesteps}")
    print(f"  - 预计记录数: {total_records}")
    
    # 创建并运行实验
    start_time = time.time()
    runner = ExperimentRunner(config, output_dir)
    
    try:
        await runner.run_experiment()
        elapsed_time = time.time() - start_time
        logger.info("实验完成", {
            "status": "success",
            "elapsed_seconds": elapsed_time,
            "total_records": total_records
        })
        print(f"\n✓ 实验完成（耗时: {elapsed_time:.1f}秒）")
    except Exception as e:
        logger.error("实验失败", {"error": str(e)})
        print(f"\n✗ 实验失败: {e}")
        raise


def perform_visualization(output_dir: Path):
    """
    执行可视化分析
    
    Args:
        output_dir: 输出目录
    """
    print("\n" + "="*60)
    print("执行可视化分析")
    print("="*60)
    
    try:
        viz = ExperimentVisualizer(output_dir)
        viz.generate_all_visualizations()
        print("\n✓ 可视化分析完成")
    except FileNotFoundError as e:
        print(f"\n✗ 结果文件未找到: {e}")
        print("  请先运行实验生成results.jsonl")


def generate_statistics(output_dir: Path):
    """
    生成统计摘要
    
    Args:
        output_dir: 输出目录
    """
    print("\n" + "="*60)
    print("生成统计摘要")
    print("="*60)
    
    try:
        reader = ExperimentResultReader(output_dir / "results.jsonl")
        reader.load()
        
        print("\n【按条件汇总】")
        print(reader.get_summary_by_condition())
        
        print("\n【按个性汇总】")
        print(reader.get_summary_by_persona())
        
        print("\n【按场景汇总】")
        print(reader.get_summary_by_scenario())

        summary_by_model = reader.get_summary_by_model()
        if not summary_by_model.empty:
            print("\n【按模型汇总】")
            print(summary_by_model)

        summary_by_model_condition = reader.get_summary_by_model_condition()
        if not summary_by_model_condition.empty:
            print("\n【按模型×条件汇总】")
            print(summary_by_model_condition)

        mechanism_summary = reader.get_higher_order_mechanism_summary()
        if not mechanism_summary.empty:
            print("\n【高阶机制汇总（CMT/ASI/HO-Event）】")
            print(mechanism_summary)

        p3_traj_summary = reader.get_p3_nci_trajectory_summary()
        if not p3_traj_summary.empty:
            print("\n【P3个体NCI演化（按时间步汇总）】")
            print(p3_traj_summary)

        final_comp_summary = reader.get_final_nci_comparison_summary()
        if not final_comp_summary.empty:
            print("\n【最终NCI对比（P3终点 vs P2终点 vs P1）】")
            print(final_comp_summary)
        
        # 保存汇总统计
        reader.save_summary_statistics(output_dir / "figures")
        
        print("\n✓ 统计摘要已生成")
    except FileNotFoundError as e:
        print(f"\n✗ 结果文件未找到: {e}")
        print("  请先运行实验生成results.jsonl")


async def main():
    """主程序入口。"""

    # 解析命令行参数
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="LLM-Agent负面信息选择实验（v2.0 OASIS版本）",
        epilog="""
示例用法:
  python main.py                          # 运行实验
  python main.py --visualize              # 仅生成可视化
  python main.py --stats                  # 仅生成统计
  python main.py --visualize --stats      # 生成可视化和统计
        """
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=script_dir / "experiment_config.yaml",
        help="实验配置文件路径（YAML 或 JSON）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "outputs",
        help="结果输出目录",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="仅执行可视化分析（不运行实验）",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="仅生成统计摘要（不运行实验）",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["run", "visualize", "stats", "full"],
        default="run",
        help="执行模式",
    )
    
    args = parser.parse_args()

    # 加载环境变量
    load_env_file(script_dir / ".env")
    load_env_file(script_dir / ".env.example")

    # 加载配置
    print(f"加载配置：{args.config}")
    config = load_config(args.config)

    # 准备输出目录
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "figures").mkdir(parents=True, exist_ok=True)

    # 根据参数执行对应操作
    if args.visualize or args.mode == "visualize":
        perform_visualization(args.output_dir)
    elif args.stats or args.mode == "stats":
        generate_statistics(args.output_dir)
    elif args.mode == "full":
        if getattr(config, "use_oasis_deploy", False):
            await run_oasis_deploy(args.output_dir)
        else:
            await run_experiments(config, args.output_dir)
        perform_visualization(args.output_dir)
        generate_statistics(args.output_dir)
    else:  # 默认：run
        if getattr(config, "use_oasis_deploy", False):
            await run_oasis_deploy(args.output_dir)
        else:
            await run_experiments(config, args.output_dir)

    print(f"\n输出目录：{args.output_dir}")


if __name__ == "__main__":
    asyncio.run(main())

