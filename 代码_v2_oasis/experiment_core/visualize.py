"""
可视化模块 (visualize.py)

用于生成论文所需的图表和可视化：
1. NCI时间序列曲线（P1 vs P2 vs P3对比）
2. GCR群体共识演化
3. 个性差异对比图
4. 场景×气候的热力图
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Optional
import json

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class ExperimentVisualizer:
    """实验结果可视化器"""
    
    def __init__(self, results_dir: Path, output_dir: Optional[Path] = None):
        """
        初始化可视化器
        
        Args:
            results_dir: 实验结果所在目录
            output_dir: 输出图表的目录（默认为results_dir/figures）
        """
        self.results_dir = Path(results_dir)
        self.output_dir = output_dir or self.results_dir / "figures"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 颜色方案
        self.colors = {
            "P1": "#FF6B6B",      # 红色
            "P2": "#4ECDC4",      # 青色
            "P3": "#45B7D1",      # 深青
            "risk_sensitive": "#FF9999",
            "authority_trusting": "#66B2FF",
            "neutral_prudent": "#99FF99"
        }
        
        self.data = None
    
    def load_results(self, results_file: str = "results.jsonl") -> pd.DataFrame:
        """
        加载JSONL格式的实验结果
        
        Args:
            results_file: 结果文件名
            
        Returns:
            DataFrame: 加载的数据
        """
        filepath = self.results_dir / results_file

        # 优先读取 JSONL；若不存在则自动回退读取 CSV
        if filepath.exists():
            records = []
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            self.data = pd.DataFrame(records)
            return self.data

        csv_path = self.results_dir / "results.csv"
        if csv_path.exists():
            self.data = pd.read_csv(csv_path)
            return self.data

        raise FileNotFoundError(
            f"未找到结果文件：{filepath} 或 {csv_path}"
        )
    
    def plot_nci_comparison(self, scenario: str = "mycoplasma_pneumonia"):
        """
        绘制NCI对比图：P1 vs P2 vs P3
        
        按个性分组，显示三个平台的NCI均值对比
        """
        # 筛选数据
        data = self.data[self.data['scenario_name'] == scenario].copy()
        
        # 映射条件名称到平台标记
        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3"
        }
        data['platform'] = data['condition_name'].map(condition_map)
        
        # 按个性和平台分组计算平均NCI
        grouped = data.groupby(['persona_name', 'platform'])['negative_choice_index'].agg(['mean', 'std', 'count']).reset_index()
        
        # 绘图
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        fig.suptitle(f'NCI对比：{scenario}场景', fontsize=14, fontweight='bold')
        
        personas = ['risk_sensitive', 'authority_trusting', 'neutral_prudent']
        persona_labels = ['风险敏感型', '权威信任型', '中立谨慎型']
        
        for idx, (persona, label) in enumerate(zip(personas, persona_labels)):
            ax = axes[idx]
            
            # 筛选该个性的数据
            persona_data = grouped[grouped['persona_name'] == persona]
            
            # 绘制柱状图
            x_pos = np.arange(len(persona_data))
            bars = ax.bar(x_pos, persona_data['mean'], 
                         yerr=persona_data['std'],
                         color=[self.colors[p] for p in persona_data['platform']],
                         alpha=0.8,
                         capsize=5,
                         edgecolor='black',
                         linewidth=1.5)
            
            # 添加中立线
            ax.axhline(y=2.0, color='gray', linestyle='--', linewidth=2, alpha=0.5, label='中立值')
            
            # 配置坐标轴
            ax.set_xlabel('平台', fontsize=11, fontweight='bold')
            ax.set_ylabel('NCI值', fontsize=11, fontweight='bold')
            ax.set_title(label, fontsize=12, fontweight='bold')
            ax.set_xticks(x_pos)
            ax.set_xticklabels(persona_data['platform'])
            ax.set_ylim(0, 4)
            ax.grid(axis='y', alpha=0.3)
            ax.legend()
            
            # 在柱子上标注数值
            for i, (bar, val) in enumerate(zip(bars, persona_data['mean'])):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                       f'{val:.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'nci_comparison_{scenario}.png', dpi=300, bbox_inches='tight')
        print(f"✓ 已保存: nci_comparison_{scenario}.png")
        plt.close()
    
    def plot_platform_effect(self):
        """
        绘制平台效应总体对比
        
        X轴：平台(P1/P2/P3)
        Y轴：平均NCI
        分组：场景
        """
        # 映射条件
        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3"
        }
        data = self.data.copy()
        data['platform'] = data['condition_name'].map(condition_map)
        
        # 按平台和场景聚合
        grouped = data.groupby(['platform', 'scenario_name'])['negative_choice_index'].agg(['mean', 'std']).reset_index()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        scenarios = grouped['scenario_name'].unique()
        x = np.arange(len(['P1', 'P2', 'P3']))
        width = 0.35
        
        for i, scenario in enumerate(scenarios):
            scenario_data = grouped[grouped['scenario_name'] == scenario].sort_values('platform')
            offset = width * (i - len(scenarios)/2 + 0.5)
            
            ax.bar(x + offset, scenario_data['mean'], width,
                  label=scenario,
                  alpha=0.8,
                  edgecolor='black',
                  linewidth=1)
        
        # 添加中立线
        ax.axhline(y=2.0, color='red', linestyle='--', linewidth=2, alpha=0.7, label='中立值')
        
        ax.set_xlabel('平台', fontsize=12, fontweight='bold')
        ax.set_ylabel('平均NCI', fontsize=12, fontweight='bold')
        ax.set_title('平台效应总体对比', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(['P1\n(独立)', 'P2\n(低反馈)', 'P3\n(高互动)'])
        ax.set_ylim(0, 4)
        ax.legend(loc='upper left')
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'platform_effect.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: platform_effect.png")
        plt.close()
    
    def plot_persona_effect(self):
        """
        绘制个性效应对比
        
        X轴：个性
        Y轴：平均NCI
        分组：平台
        """
        # 映射条件
        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3"
        }
        data = self.data.copy()
        data['platform'] = data['condition_name'].map(condition_map)
        
        # 按个性和平台聚合
        grouped = data.groupby(['persona_name', 'platform'])['negative_choice_index'].agg(['mean', 'std']).reset_index()
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        personas_data = grouped.pivot(index='persona_name', columns='platform', values='mean')
        
        # 绘制折线图
        for platform in ['P1', 'P2', 'P3']:
            if platform in personas_data.columns:
                ax.plot(personas_data.index, personas_data[platform],
                       marker='o', linewidth=2.5, markersize=8,
                       label=platform, color=self.colors[platform])
        
        # 添加中立线
        ax.axhline(y=2.0, color='red', linestyle='--', linewidth=2, alpha=0.7, label='中立值')
        
        ax.set_xlabel('个性类型', fontsize=12, fontweight='bold')
        ax.set_ylabel('平均NCI', fontsize=12, fontweight='bold')
        ax.set_title('个性效应对比（跨平台）', fontsize=14, fontweight='bold')
        ax.set_xticklabels(['风险敏感型', '权威信任型', '中立谨慎型'], rotation=15)
        ax.set_ylim(0, 4)
        ax.legend(loc='upper left')
        ax.grid(alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'persona_effect.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: persona_effect.png")
        plt.close()
    
    def plot_climate_effect(self):
        """
        绘制气候效应热力图
        
        行：场景
        列：气候
        值：平均NCI
        """
        # 按场景和气候聚合
        grouped = self.data.groupby(['scenario_name', 'climate_type'])['negative_choice_index'].mean().unstack()
        
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # 绘制热力图
        sns.heatmap(grouped, annot=True, fmt='.2f', cmap='RdYlGn_r',
                   center=2.0, vmin=0, vmax=4,
                   cbar_kws={'label': 'NCI值'},
                   ax=ax, linewidths=2, linecolor='black')
        
        ax.set_xlabel('气候类型', fontsize=12, fontweight='bold')
        ax.set_ylabel('场景', fontsize=12, fontweight='bold')
        ax.set_title('气候效应热力图', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'climate_effect_heatmap.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: climate_effect_heatmap.png")
        plt.close()

    def plot_climate_bias_overall(self):
        """
        绘制总体气候偏向对比图（含无气候基线）

        X轴：气候类型（none/positive_leaning/negative_leaning）
        Y轴：平均NCI
        """
        order = ["none", "positive_leaning", "negative_leaning"]
        label_map = {
            "none": "无气候",
            "positive_leaning": "正向气候",
            "negative_leaning": "负向气候",
        }

        grouped = (
            self.data.groupby("climate_type")["negative_choice_index"]
            .agg(["mean", "std", "count"])
            .reindex(order)
            .dropna(subset=["mean"])
        )

        fig, ax = plt.subplots(figsize=(8, 5))
        x = np.arange(len(grouped))
        bars = ax.bar(
            x,
            grouped["mean"].values,
            yerr=grouped["std"].values,
            capsize=5,
            color=["#B0BEC5", "#81C784", "#E57373"],
            edgecolor="black",
            linewidth=1.2,
            alpha=0.9,
        )

        ax.axhline(2.0, color="gray", linestyle="--", linewidth=2, alpha=0.7, label="中立值=2")

        # 无气候基线
        if "none" in grouped.index:
            base = float(grouped.loc["none", "mean"])
            ax.axhline(base, color="#455A64", linestyle=":", linewidth=2, alpha=0.9, label=f"无气候基线={base:.2f}")

        ax.set_xticks(x)
        ax.set_xticklabels([label_map[idx] for idx in grouped.index])
        ax.set_ylim(0, 4)
        ax.set_ylabel("平均NCI", fontsize=11, fontweight="bold")
        ax.set_xlabel("气候类型", fontsize=11, fontweight="bold")
        ax.set_title("不同气候 vs 无气候：总体偏向对比", fontsize=13, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        ax.legend(loc="upper left")

        for bar, val in zip(bars, grouped["mean"].values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.08, f"{val:.2f}", ha="center", va="bottom", fontsize=10)

        plt.tight_layout()
        plt.savefig(self.output_dir / "climate_bias_overall.png", dpi=300, bbox_inches="tight")
        print("✓ 已保存: climate_bias_overall.png")
        plt.close()

    def plot_climate_delta_from_none(self):
        """
        绘制相对“无气候”基线的偏移（按场景）

        纵轴为 ΔNCI = NCI(climate) - NCI(none)
        """
        order = ["positive_leaning", "negative_leaning"]
        label_map = {
            "positive_leaning": "正向-无气候",
            "negative_leaning": "负向-无气候",
        }

        base = (
            self.data[self.data["climate_type"] == "none"]
            .groupby("scenario_name")["negative_choice_index"]
            .mean()
        )

        climate_mean = (
            self.data[self.data["climate_type"].isin(order)]
            .groupby(["scenario_name", "climate_type"])["negative_choice_index"]
            .mean()
            .unstack("climate_type")
            .reindex(columns=order)
        )

        delta = climate_mean.sub(base, axis=0)

        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(delta.index))
        width = 0.36

        for i, climate in enumerate(order):
            vals = delta[climate].values
            offset = (i - 0.5) * width
            bars = ax.bar(
                x + offset,
                vals,
                width=width,
                label=label_map[climate],
                color="#81C784" if climate == "positive_leaning" else "#E57373",
                edgecolor="black",
                linewidth=1.1,
                alpha=0.9,
            )
            for bar, val in zip(bars, vals):
                ax.text(bar.get_x() + bar.get_width()/2, val + (0.03 if val >= 0 else -0.08), f"{val:+.2f}", ha="center", va="bottom", fontsize=9)

        ax.axhline(0, color="black", linewidth=1.2)
        ax.set_xticks(x)
        ax.set_xticklabels(delta.index)
        ax.set_ylabel("ΔNCI（相对无气候）", fontsize=11, fontweight="bold")
        ax.set_xlabel("场景", fontsize=11, fontweight="bold")
        ax.set_title("不同气候相对无气候的偏向变化", fontsize=13, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        ax.legend(loc="upper left")

        plt.tight_layout()
        plt.savefig(self.output_dir / "climate_delta_from_none.png", dpi=300, bbox_inches="tight")
        print("✓ 已保存: climate_delta_from_none.png")
        plt.close()

    def plot_climate_persona_heatmap(self):
        """
        绘制“个性 × 气候”的偏向热力图
        """
        order = ["none", "positive_leaning", "negative_leaning"]
        label_map = {
            "none": "无气候",
            "positive_leaning": "正向气候",
            "negative_leaning": "负向气候",
        }

        table = (
            self.data.groupby(["persona_name", "climate_type"])["negative_choice_index"]
            .mean()
            .unstack("climate_type")
            .reindex(columns=order)
        )

        fig, ax = plt.subplots(figsize=(9, 5))
        sns.heatmap(
            table,
            annot=True,
            fmt=".2f",
            cmap="RdYlGn_r",
            center=2.0,
            vmin=0,
            vmax=4,
            linewidths=1.5,
            linecolor="black",
            cbar_kws={"label": "NCI值"},
            ax=ax,
        )

        ax.set_title("个性 × 气候：偏向热力图", fontsize=13, fontweight="bold")
        ax.set_xlabel("气候类型", fontsize=11, fontweight="bold")
        ax.set_ylabel("个性", fontsize=11, fontweight="bold")
        ax.set_xticklabels([label_map.get(c, c) for c in table.columns], rotation=0)

        plt.tight_layout()
        plt.savefig(self.output_dir / "climate_persona_heatmap.png", dpi=300, bbox_inches="tight")
        print("✓ 已保存: climate_persona_heatmap.png")
        plt.close()

    def plot_persona_stage_response_by_climate(self):
        """
        绘制三类人格在不同气候下的阶段响应（P1→P2→P3）

        说明：
        - P1 固定取 independent + none
        - P2/P3 在对应气候下取 low_feedback/high_interaction
        - 每种气候输出一张图
        """
        stage_order = ["P1", "P2", "P3"]
        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3",
        }
        climate_order = ["none", "positive_leaning", "negative_leaning"]

        data = self.data.copy()
        data["platform"] = data["condition_name"].map(condition_map)

        p1 = data[(data["condition_name"] == "independent") & (data["climate_type"] == "none")]
        p2p3 = data[data["condition_name"].isin(["low_feedback", "high_interaction"])]

        for climate in climate_order:
            part = pd.concat([
                p1,
                p2p3[p2p3["climate_type"] == climate],
            ], ignore_index=True)

            grouped = (
                part.groupby(["persona_name", "platform"])["negative_choice_index"]
                .mean()
                .reset_index()
            )

            fig, ax = plt.subplots(figsize=(8, 5))
            for persona, sub in grouped.groupby("persona_name"):
                sub = sub.set_index("platform").reindex(stage_order).reset_index()
                ax.plot(
                    sub["platform"],
                    sub["negative_choice_index"],
                    marker="o",
                    linewidth=2.0,
                    label=persona,
                )

            ax.axhline(2.0, color="gray", linestyle="--", linewidth=1.8, alpha=0.7)
            ax.set_ylim(0, 4)
            ax.set_ylabel("平均NCI", fontsize=11, fontweight="bold")
            ax.set_xlabel("阶段", fontsize=11, fontweight="bold")
            ax.set_title(f"三类人格在 {climate} 下的阶段响应", fontsize=13, fontweight="bold")
            ax.grid(alpha=0.3)
            ax.legend(loc="best")

            filename = f"persona_stage_response_{climate}.png"
            plt.tight_layout()
            plt.savefig(self.output_dir / filename, dpi=300, bbox_inches="tight")
            print(f"✓ 已保存: {filename}")
            plt.close()

    def plot_persona_stage_delta_from_p1(self):
        """
        绘制三类人格在不同气候下、相对各自P1基线的阶段偏移图

        纵轴：ΔNCI = NCI(stage) - NCI(P1)
        """
        stage_order = ["P1", "P2", "P3"]
        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3",
        }
        climate_order = ["none", "positive_leaning", "negative_leaning"]

        data = self.data.copy()
        data["platform"] = data["condition_name"].map(condition_map)

        p1_base = (
            data[(data["condition_name"] == "independent") & (data["climate_type"] == "none")]
            .groupby("persona_name")["negative_choice_index"]
            .mean()
        )

        p2p3 = data[data["condition_name"].isin(["low_feedback", "high_interaction"])]

        for climate in climate_order:
            part = pd.concat([
                data[(data["condition_name"] == "independent") & (data["climate_type"] == "none")],
                p2p3[p2p3["climate_type"] == climate],
            ], ignore_index=True)

            grouped = (
                part.groupby(["persona_name", "platform"])["negative_choice_index"]
                .mean()
                .reset_index()
            )

            fig, ax = plt.subplots(figsize=(8, 5))
            for persona, sub in grouped.groupby("persona_name"):
                sub = sub.set_index("platform").reindex(stage_order)
                baseline = p1_base.get(persona, np.nan)
                delta = sub["negative_choice_index"] - baseline
                ax.plot(stage_order, delta.values, marker="o", linewidth=2.0, label=persona)

            ax.axhline(0.0, color="black", linestyle="-", linewidth=1.6, alpha=0.8)
            ax.set_ylabel("ΔNCI（相对P1）", fontsize=11, fontweight="bold")
            ax.set_xlabel("阶段", fontsize=11, fontweight="bold")
            ax.set_title(f"三类人格在 {climate} 下相对P1的偏移", fontsize=13, fontweight="bold")
            ax.grid(alpha=0.3)
            ax.legend(loc="best")

            filename = f"persona_stage_delta_from_P1_{climate}.png"
            plt.tight_layout()
            plt.savefig(self.output_dir / filename, dpi=300, bbox_inches="tight")
            print(f"✓ 已保存: {filename}")
            plt.close()
    
    def plot_hypothesis_verification(self):
        """
        绘制三个假设的验证图表
        
        H1: P1的NCI显著>2.0（个体认知偏向）
        H2: P2相对P1增幅>0.15（社交影响）
        H3: P3相对P2增幅>(P2-P1)（非线性放大）
        """
        # 映射条件
        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3"
        }
        data = self.data.copy()
        data['platform'] = data['condition_name'].map(condition_map)
        
        # 计算统计量
        platform_means = data.groupby('platform')['negative_choice_index'].agg(['mean', 'std', 'count']).reset_index()
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        fig.suptitle('三个假设的验证', fontsize=14, fontweight='bold')
        
        # H1验证
        ax = axes[0]
        p1_mean = platform_means[platform_means['platform'] == 'P1']['mean'].values[0]
        p1_std = platform_means[platform_means['platform'] == 'P1']['std'].values[0]
        
        ax.bar(['P1'], [p1_mean], yerr=[p1_std], color=self.colors['P1'], alpha=0.8, capsize=5, edgecolor='black', linewidth=2)
        ax.axhline(y=2.0, color='red', linestyle='--', linewidth=2, label='中立值(2.0)')
        ax.set_ylabel('NCI值', fontsize=11, fontweight='bold')
        ax.set_title('H1: 个体认知偏向\n(P1 > 2.0?)', fontsize=12, fontweight='bold')
        ax.set_ylim(0, 4)
        ax.legend()
        ax.text(0, p1_mean + p1_std + 0.2, f'{p1_mean:.2f}±{p1_std:.2f}', 
               ha='center', fontsize=11, fontweight='bold')
        
        # H2验证
        ax = axes[1]
        p2_mean = platform_means[platform_means['platform'] == 'P2']['mean'].values[0]
        increment_h2 = p2_mean - p1_mean
        
        ax.bar(['P1→P2'], [increment_h2], color='#90EE90' if increment_h2 > 0.15 else '#FFB6C1', 
              alpha=0.8, edgecolor='black', linewidth=2)
        ax.axhline(y=0.15, color='orange', linestyle='--', linewidth=2, label='阈值(0.15)')
        ax.set_ylabel('增幅(ΔNI)', fontsize=11, fontweight='bold')
        ax.set_title('H2: 社交影响\n(P2-P1 > 0.15?)', fontsize=12, fontweight='bold')
        ax.legend()
        ax.text(0, increment_h2 + 0.03, f'{increment_h2:.2f}', ha='center', fontsize=11, fontweight='bold')
        
        # H3验证
        ax = axes[2]
        p3_mean = platform_means[platform_means['platform'] == 'P3']['mean'].values[0]
        increment_h3 = p3_mean - p2_mean
        amplification = increment_h3 / increment_h2 if increment_h2 > 0 else 1.0
        
        x = np.arange(2)
        increments = [increment_h2, increment_h3]
        colors_h3 = ['#4ECDC4', '#45B7D1']
        
        ax.bar(x, increments, color=colors_h3, alpha=0.8, edgecolor='black', linewidth=2)
        ax.axhline(y=increment_h2, color='green', linestyle=':', linewidth=2, 
                  label=f'P2-P1 ({increment_h2:.3f})', alpha=0.7)
        ax.set_ylabel('增幅', fontsize=11, fontweight='bold')
        ax.set_title('H3: 非线性放大\n(P3-P2 > P2-P1?)', fontsize=12, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(['P2-P1', 'P3-P2'])
        ax.legend()
        
        for i, (inc, col) in enumerate(zip(increments, colors_h3)):
            ax.text(i, inc + 0.02, f'{inc:.3f}', ha='center', fontsize=10, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'hypothesis_verification.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: hypothesis_verification.png")
        plt.close()

    def plot_dynamic_metrics_timeline(self):
        """
        绘制动态指标时间轨迹图（GCR 与 SSA）

        输出：dynamic_metrics_timeline.png
        """
        required_cols = {
            'condition_name', 'timestep',
            'group_consensus_ratio', 'social_signal_asymmetry'
        }
        if self.data is None or not required_cols.issubset(set(self.data.columns)):
            print("⚠️ 跳过动态轨迹图：缺少GCR/SSA或timestep列")
            return

        condition_map = {
            "independent": "P1",
            "low_feedback": "P2",
            "high_interaction": "P3"
        }

        df = self.data.copy()
        df['platform'] = df['condition_name'].map(condition_map)

        grouped = (
            df.groupby(['platform', 'timestep'])
            .agg(
                gcr=('group_consensus_ratio', 'mean'),
                ssa=('social_signal_asymmetry', 'mean')
            )
            .reset_index()
        )

        fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

        for platform in ['P1', 'P2', 'P3']:
            sub = grouped[grouped['platform'] == platform].sort_values('timestep')
            if sub.empty:
                continue
            axes[0].plot(sub['timestep'], sub['gcr'], marker='o', linewidth=2, label=platform, color=self.colors.get(platform))
            axes[1].plot(sub['timestep'], sub['ssa'], marker='o', linewidth=2, label=platform, color=self.colors.get(platform))

        axes[0].set_ylabel('GCR', fontsize=11, fontweight='bold')
        axes[0].set_title('群体共识度（GCR）时间轨迹', fontsize=12, fontweight='bold')
        axes[0].grid(alpha=0.3)
        axes[0].legend(loc='best')

        axes[1].set_ylabel('SSA', fontsize=11, fontweight='bold')
        axes[1].set_xlabel('时间步', fontsize=11, fontweight='bold')
        axes[1].set_title('社交信号不对称度（SSA）时间轨迹', fontsize=12, fontweight='bold')
        axes[1].grid(alpha=0.3)

        plt.tight_layout()
        plt.savefig(self.output_dir / 'dynamic_metrics_timeline.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: dynamic_metrics_timeline.png")
        plt.close()

    def plot_p3_nci_trajectory(self):
        """
        绘制P3阶段NCI演化图（按scenario×climate分面，显示均值轨迹）。

        输出：p3_nci_trajectory.png
        """
        required_cols = {'condition_name', 'scenario_name', 'climate_type', 'negative_choice_index'}
        if self.data is None or not required_cols.issubset(set(self.data.columns)):
            print("⚠️ 跳过P3演化图：缺少必要列")
            return

        p3 = self.data[self.data['condition_name'] == 'high_interaction'].copy()
        if p3.empty:
            print("⚠️ 跳过P3演化图：无P3数据")
            return

        if 'timestep' not in p3.columns:
            if 'round_index' in p3.columns:
                p3['timestep'] = p3['round_index']
            else:
                p3['timestep'] = 1

        p3['timestep'] = pd.to_numeric(p3['timestep'], errors='coerce')
        p3['negative_choice_index'] = pd.to_numeric(p3['negative_choice_index'], errors='coerce')
        p3 = p3.dropna(subset=['timestep', 'negative_choice_index'])
        if p3.empty:
            print("⚠️ 跳过P3演化图：P3时间步数据为空")
            return

        agg = (
            p3.groupby(['scenario_name', 'climate_type', 'timestep'])['negative_choice_index']
            .agg(['mean', 'std', 'count'])
            .reset_index()
            .sort_values(['scenario_name', 'climate_type', 'timestep'])
        )

        scenarios = list(agg['scenario_name'].dropna().unique())
        climates = ['positive_leaning', 'negative_leaning', 'none']
        climates = [c for c in climates if c in set(agg['climate_type'])] or list(agg['climate_type'].dropna().unique())

        fig, axes = plt.subplots(
            nrows=max(1, len(scenarios)),
            ncols=max(1, len(climates)),
            figsize=(4.6 * max(1, len(climates)), 3.6 * max(1, len(scenarios))),
            sharex=True,
            sharey=True,
        )
        axes = np.atleast_2d(axes)

        climate_label = {
            'positive_leaning': '正向气候',
            'negative_leaning': '负向气候',
            'none': '无气候',
        }

        for i, scenario in enumerate(scenarios):
            for j, climate in enumerate(climates):
                ax = axes[i, j]
                sub = agg[(agg['scenario_name'] == scenario) & (agg['climate_type'] == climate)]
                if sub.empty:
                    ax.set_axis_off()
                    continue
                ax.plot(sub['timestep'], sub['mean'], marker='o', linewidth=2.2, color='#45B7D1')
                if sub['std'].notna().any():
                    y1 = sub['mean'] - sub['std'].fillna(0)
                    y2 = sub['mean'] + sub['std'].fillna(0)
                    ax.fill_between(sub['timestep'], y1, y2, alpha=0.18, color='#45B7D1')
                ax.axhline(2.0, color='gray', linestyle='--', linewidth=1.3, alpha=0.7)
                ax.set_title(f"{scenario} | {climate_label.get(climate, climate)}", fontsize=10)
                ax.grid(alpha=0.25)
                ax.set_ylim(0, 4)

        for i in range(len(scenarios)):
            axes[i, 0].set_ylabel('NCI均值', fontsize=10, fontweight='bold')
        for j in range(len(climates)):
            axes[-1, j].set_xlabel('时间步', fontsize=10, fontweight='bold')

        fig.suptitle('P3个体NCI演化轨迹（均值±标准差）', fontsize=13, fontweight='bold')
        plt.tight_layout()
        plt.savefig(self.output_dir / 'p3_nci_trajectory.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: p3_nci_trajectory.png")
        plt.close()

    def plot_final_nci_comparison_p1_p2_p3(self):
        """
        绘制最终NCI对比图（P1/P2终点/P3终点）。

        输出：final_nci_comparison_p1_p2_p3.png
        """
        required_cols = {'condition_name', 'scenario_name', 'climate_type', 'negative_choice_index'}
        if self.data is None or not required_cols.issubset(set(self.data.columns)):
            print("⚠️ 跳过最终NCI对比图：缺少必要列")
            return

        df = self.data.copy()
        if 'timestep' not in df.columns:
            if 'round_index' in df.columns:
                df['timestep'] = df['round_index']
            else:
                df['timestep'] = 1
        df['timestep'] = pd.to_numeric(df['timestep'], errors='coerce')
        df['negative_choice_index'] = pd.to_numeric(df['negative_choice_index'], errors='coerce')
        df = df.dropna(subset=['timestep', 'negative_choice_index'])
        if df.empty:
            print("⚠️ 跳过最终NCI对比图：数据为空")
            return

        base_keys = ['scenario_name', 'persona_name', 'repeat_index'] if set(['persona_name', 'repeat_index']).issubset(df.columns) else ['scenario_name']
        climate_keys = base_keys + ['climate_type'] if 'climate_type' in df.columns else base_keys

        p1 = df[df['condition_name'] == 'independent'].sort_values('timestep').groupby(base_keys, dropna=False).tail(1)
        p1 = p1[base_keys + ['negative_choice_index']].rename(columns={'negative_choice_index': 'P1'})

        p2 = df[df['condition_name'] == 'low_feedback'].sort_values('timestep').groupby(climate_keys, dropna=False).tail(1)
        p2 = p2[climate_keys + ['negative_choice_index']].rename(columns={'negative_choice_index': 'P2'})

        p3 = df[df['condition_name'] == 'high_interaction'].sort_values('timestep').groupby(climate_keys, dropna=False).tail(1)
        p3 = p3[climate_keys + ['negative_choice_index']].rename(columns={'negative_choice_index': 'P3'})

        if p2.empty or p3.empty or p1.empty:
            print("⚠️ 跳过最终NCI对比图：P1/P2/P3数据不完整")
            return

        merged = p3.merge(p2, on=climate_keys, how='left').merge(p1, on=base_keys, how='left')
        if merged.empty:
            print("⚠️ 跳过最终NCI对比图：合并后为空")
            return

        summary = merged.groupby(['scenario_name', 'climate_type'], dropna=False)[['P1', 'P2', 'P3']].mean().reset_index()
        summary['group_label'] = summary['scenario_name'] + ' | ' + summary['climate_type']

        x = np.arange(len(summary))
        width = 0.24
        fig, ax = plt.subplots(figsize=(max(9, 1.8 * len(summary)), 5.2))

        bars1 = ax.bar(x - width, summary['P1'], width=width, label='P1', color=self.colors['P1'], edgecolor='black', linewidth=1)
        bars2 = ax.bar(x, summary['P2'], width=width, label='P2', color=self.colors['P2'], edgecolor='black', linewidth=1)
        bars3 = ax.bar(x + width, summary['P3'], width=width, label='P3', color=self.colors['P3'], edgecolor='black', linewidth=1)

        ax.axhline(2.0, color='gray', linestyle='--', linewidth=1.4, alpha=0.7)
        ax.set_ylim(0, 4)
        ax.set_ylabel('最终NCI均值', fontsize=11, fontweight='bold')
        ax.set_xlabel('场景 | 气候', fontsize=11, fontweight='bold')
        ax.set_title('最终NCI对比：P3终点 vs P2终点 vs P1', fontsize=13, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(summary['group_label'], rotation=20, ha='right')
        ax.grid(axis='y', alpha=0.25)
        ax.legend(loc='upper left')

        for bars in [bars1, bars2, bars3]:
            for b in bars:
                h = b.get_height()
                ax.text(b.get_x() + b.get_width()/2, h + 0.05, f"{h:.2f}", ha='center', va='bottom', fontsize=8)

        plt.tight_layout()
        plt.savefig(self.output_dir / 'final_nci_comparison_p1_p2_p3.png', dpi=300, bbox_inches='tight')
        print("✓ 已保存: final_nci_comparison_p1_p2_p3.png")
        plt.close()
    
    def generate_all_visualizations(self):
        """生成所有图表"""
        print("\n开始生成可视化图表...")
        
        # 加载数据
        self.load_results()
        
        # 生成各类图表
        scenarios = self.data['scenario_name'].unique()
        for scenario in scenarios:
            self.plot_nci_comparison(scenario)
        
        self.plot_platform_effect()
        self.plot_persona_effect()
        self.plot_climate_effect()
        self.plot_climate_bias_overall()
        self.plot_climate_delta_from_none()
        self.plot_climate_persona_heatmap()
        self.plot_persona_stage_response_by_climate()
        self.plot_persona_stage_delta_from_p1()
        self.plot_hypothesis_verification()
        self.plot_dynamic_metrics_timeline()
        self.plot_p3_nci_trajectory()
        self.plot_final_nci_comparison_p1_p2_p3()
        
        print(f"\n✓ 所有图表已保存到: {self.output_dir}")


def generate_summary_statistics(results_df: pd.DataFrame, output_file: Optional[Path] = None) -> Dict:
    """
    生成汇总统计表
    
    Args:
        results_df: 结果DataFrame
        output_file: 输出CSV文件路径
        
    Returns:
        Dict: 汇总统计数据
    """
    # 映射条件
    condition_map = {
        "independent": "P1",
        "low_feedback": "P2",
        "high_interaction": "P3"
    }
    results_df['platform'] = results_df['condition_name'].map(condition_map)
    
    # 按多维度分组统计
    summary = results_df.groupby(['scenario_name', 'platform', 'persona_name'])['negative_choice_index'].agg([
        ('count', 'count'),
        ('mean', 'mean'),
        ('std', 'std'),
        ('min', 'min'),
        ('max', 'max')
    ]).reset_index()
    
    # 保存到CSV
    if output_file:
        summary.to_csv(output_file, index=False, encoding='utf-8')
        print(f"✓ 汇总统计已保存到: {output_file}")
    
    return summary


if __name__ == "__main__":
    # 示例用法
    viz = ExperimentVisualizer(Path("./outputs"))
    viz.generate_all_visualizations()
