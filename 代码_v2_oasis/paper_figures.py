from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs' / 'paper_figures'
OUT.mkdir(parents=True, exist_ok=True)


def load_data() -> pd.DataFrame:
    j = ROOT / 'outputs' / 'results.jsonl'
    c = ROOT / 'outputs' / 'results.csv'
    if j.exists():
        records = []
        with open(j, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        if records:
            return pd.DataFrame(records)
    if c.exists():
        return pd.read_csv(c)
    raise FileNotFoundError('未找到 results.jsonl 或 results.csv')


def map_platform(df: pd.DataFrame) -> pd.DataFrame:
    m = {'independent': 'P1', 'low_feedback': 'P2', 'high_interaction': 'P3'}
    out = df.copy()
    out['platform'] = out['condition_name'].map(m)
    return out


def fig1_nci_platform_and_persona(df: pd.DataFrame):
    d = map_platform(df)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 左：三平台总体NCI
    left = d.groupby('platform')['negative_choice_index'].agg(['mean', 'std', 'count']).reindex(['P1', 'P2', 'P3'])
    x = np.arange(len(left))
    axes[0].bar(x, left['mean'], yerr=left['std'], capsize=5, color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(['P1', 'P2', 'P3'])
    axes[0].set_ylim(0, 4)
    axes[0].set_title('图1A 三平台平均NCI')
    axes[0].grid(axis='y', alpha=0.3)

    # 右：三种个性轨迹
    p = d.groupby(['persona_name', 'platform'])['negative_choice_index'].mean().reset_index()
    order = ['P1', 'P2', 'P3']
    for persona, g in p.groupby('persona_name'):
        gg = g.set_index('platform').reindex(order)
        axes[1].plot(order, gg['negative_choice_index'], marker='o', label=persona)
    axes[1].set_ylim(0, 4)
    axes[1].set_title('图1B 个性轨迹（P1→P2→P3）')
    axes[1].grid(alpha=0.3)
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(OUT / 'fig1_nci_platform_persona.png', dpi=300)
    plt.close()


def fig3_persona_heterogeneity(df: pd.DataFrame):
    d = map_platform(df)
    table = d.groupby(['persona_name', 'platform'])['negative_choice_index'].mean().unstack('platform').reindex(columns=['P1', 'P2', 'P3'])
    plt.figure(figsize=(8, 5))
    sns.heatmap(table, annot=True, fmt='.2f', cmap='RdYlGn_r', vmin=0, vmax=4, cbar_kws={'label': 'NCI'})
    plt.title('图3 个性类型异质性效应')
    plt.tight_layout()
    plt.savefig(OUT / 'fig3_persona_heterogeneity.png', dpi=300)
    plt.close()


def fig4_atmosphere_effect(df: pd.DataFrame):
    d = map_platform(df)
    order_atm = ['none', 'positive_leaning', 'negative_leaning']
    order_p = ['P1', 'P2', 'P3']
    g = d.groupby(['climate_type', 'platform'])['negative_choice_index'].mean().reset_index()

    plt.figure(figsize=(10, 5))
    width = 0.22
    x = np.arange(len(order_atm))
    for i, p in enumerate(order_p):
        vals = []
        for a in order_atm:
            m = g[(g['climate_type'] == a) & (g['platform'] == p)]['negative_choice_index']
            vals.append(float(m.iloc[0]) if len(m) else np.nan)
        plt.bar(x + (i - 1) * width, vals, width=width, label=p)

    plt.xticks(x, ['none', '正向氛围', '负向氛围'])
    plt.ylim(0, 4)
    plt.title('图4 不同氛围影响（平台内对比）')
    plt.ylabel('平均NCI')
    plt.grid(axis='y', alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT / 'fig4_atmosphere_platform.png', dpi=300)
    plt.close()


def fig6_platform_schematic():
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis('off')
    boxes = [
        (0.05, 0.2, 0.25, 0.6, 'P1\n独立决策\n无社交反馈'),
        (0.375, 0.2, 0.25, 0.6, 'P2\n静态快照\n少量评论+热度'),
        (0.70, 0.2, 0.25, 0.6, 'P3\n动态高阶互动\n多主体共在')
    ]
    for x, y, w, h, txt in boxes:
        rect = plt.Rectangle((x, y), w, h, fill=False, linewidth=2)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2, txt, ha='center', va='center', fontsize=12)
    ax.annotate('', xy=(0.365, 0.5), xytext=(0.31, 0.5), arrowprops=dict(arrowstyle='->', lw=2))
    ax.annotate('', xy=(0.69, 0.5), xytext=(0.635, 0.5), arrowprops=dict(arrowstyle='->', lw=2))
    plt.title('图6 平台结构示意图')
    plt.tight_layout()
    plt.savefig(OUT / 'fig6_platform_schematic.png', dpi=300)
    plt.close()


def fig7_theory_model():
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axis('off')
    nodes = {
        'Cognitive': (0.2, 0.8),
        'Social Proof': (0.5, 0.55),
        'Higher-order': (0.8, 0.3),
        'NCI': (0.5, 0.15)
    }
    for k, (x, y) in nodes.items():
        circ = plt.Circle((x, y), 0.1, fill=False, lw=2)
        ax.add_patch(circ)
        ax.text(x, y, k, ha='center', va='center', fontsize=10)
    def arrow(a, b):
        ax.annotate('', xy=nodes[b], xytext=nodes[a], arrowprops=dict(arrowstyle='->', lw=1.8))
    arrow('Cognitive', 'Social Proof')
    arrow('Social Proof', 'Higher-order')
    arrow('Cognitive', 'NCI')
    arrow('Social Proof', 'NCI')
    arrow('Higher-order', 'NCI')
    plt.title('图7 理论框架模型')
    plt.tight_layout()
    plt.savefig(OUT / 'fig7_theory_model.png', dpi=300)
    plt.close()


def missing_report(df: pd.DataFrame):
    needed = {
        '图2(GCR/SSA时间轨迹)': ['timestep', 'group_consensus_ratio', 'social_signal_asymmetry'],
        '图5(SSAF分布)': ['persuasion_effect_score', 'condition_name', 'persona_name'],
        '图8(CMT+ASI)': ['timestep', 'group_consensus_ratio', 'p3_is_higher_order_event', 'p3_copresence_size']
    }
    lines = ['# 缺失图表评估', '']
    cols = set(df.columns)
    for name, req in needed.items():
        miss = [c for c in req if c not in cols]
        if miss:
            lines.append(f'- {name}：当前缺字段 {miss}')
        else:
            lines.append(f'- {name}：字段齐全，可直接制图')
    lines += [
        '',
        '## 建议补充图（除既定图1-8外）',
        '- 图9：平台内氛围主效应 + 交互效应图（Atmosphere × Platform）',
        '- 图10：P3机制三联图（CMT分布、ASI分布、HO-Event比例）',
        '- 图11：persona分层的放大比R森林图（含95%CI）',
        '- 图12：STOP原因构成图（high_consensus / stalled / max_timestep）'
    ]
    (OUT / 'missing_figures_report.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    df = load_data()
    fig1_nci_platform_and_persona(df)
    fig3_persona_heterogeneity(df)
    fig4_atmosphere_effect(df)
    fig6_platform_schematic()
    fig7_theory_model()
    missing_report(df)
    print('done ->', OUT)


if __name__ == '__main__':
    main()
