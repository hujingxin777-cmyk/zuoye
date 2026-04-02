"""
数据输入输出工具模块 (io_utils.py)

负责实验结果的持久化、加载和分析
"""

import json
import csv
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import pandas as pd

from .schemas import ExperimentRecord


class ExperimentResultWriter:
    """实验结果写入器"""
    
    def __init__(self, output_dir: Path):
        """
        初始化结果写入器
        
        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSONL文件路径（追加模式）
        self.jsonl_file = self.output_dir / "results.jsonl"
        self.csv_file = self.output_dir / "results.csv"

        # 每次新实验启动时清理旧结果，避免新旧数据混合
        if self.jsonl_file.exists():
            self.jsonl_file.unlink()
        if self.csv_file.exists():
            self.csv_file.unlink()
        
        # 缓冲区
        self.buffer: List[ExperimentRecord] = []
        self.buffer_size = 100  # 每100条记录自动刷新一次
    
    def add_record(self, record: ExperimentRecord):
        """
        添加一条实验记录
        
        Args:
            record: 实验记录对象
        """
        self.buffer.append(record)
        
        # 缓冲区满时自动刷新
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def add_records(self, records: List[ExperimentRecord]):
        """
        批量添加实验记录
        
        Args:
            records: 实验记录列表
        """
        for record in records:
            self.add_record(record)
    
    def flush(self):
        """
        将缓冲区中的记录写入文件
        """
        if not self.buffer:
            return
        
        # 写入JSONL（追加模式）
        import json as json_module

        def _record_to_dict(record: ExperimentRecord) -> Dict[str, Any]:
            """稳定序列化：显式保留默认值与None字段，避免动态列丢失。"""
            # Pydantic v2
            if hasattr(record, "model_dump"):
                return record.model_dump(
                    mode="json",
                    exclude_none=False,
                    exclude_unset=False,
                    exclude_defaults=False,
                )
            # Pydantic v1
            return record.dict(
                exclude_none=False,
                exclude_unset=False,
            )

        with open(self.jsonl_file, 'a', encoding='utf-8') as f:
            for record in self.buffer:
                payload = _record_to_dict(record)
                json_str = json_module.dumps(payload, ensure_ascii=False)
                f.write(json_str + '\n')
        
        # 清空缓冲区
        self.buffer = []
    
    def finalize(self):
        """
        完成写入，转换为CSV并生成统计信息
        """
        # 先刷新缓冲区
        self.flush()
        
        # 检查JSONL文件是否存在
        if not self.jsonl_file.exists():
            print(f"⚠️  没有结果数据被写入，跳过CSV转换")
            return None
        
        # 读取JSONL并转换为CSV
        records = []
        with open(self.jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        
        if records:
            # 转换为DataFrame
            df = pd.DataFrame(records)

            # 对齐完整schema列，确保动态字段在CSV中保留（即使部分行为空值）
            try:
                schema_cols = list(ExperimentRecord.model_fields.keys())
            except AttributeError:
                schema_cols = list(getattr(ExperimentRecord, "__fields__", {}).keys())
            for col in schema_cols:
                if col not in df.columns:
                    df[col] = pd.NA
            df = df[schema_cols]
            
            # 按时间戳排序
            if 'timestamp' in df.columns:
                df = df.sort_values('timestamp')
            
            # 保存为CSV
            df.to_csv(self.csv_file, index=False, encoding='utf-8')
            
            print(f"✓ 已保存 {len(df)} 条结果记录")
            print(f"  - JSONL: {self.jsonl_file}")
            print(f"  - CSV: {self.csv_file}")
            
            return df
        
        return None


class ExperimentResultReader:
    """实验结果读取器"""
    
    def __init__(self, results_file: Path):
        """
        初始化结果读取器
        
        Args:
            results_file: 结果文件路径（支持JSONL或CSV）
        """
        self.results_file = Path(results_file)
        self.data = None
    
    def load_jsonl(self) -> pd.DataFrame:
        """
        从JSONL文件加载结果
        
        Returns:
            DataFrame: 加载的数据
        """
        records = []
        with open(self.results_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        
        self.data = pd.DataFrame(records)
        return self.data
    
    def load_csv(self) -> pd.DataFrame:
        """
        从CSV文件加载结果
        
        Returns:
            DataFrame: 加载的数据
        """
        self.data = pd.read_csv(self.results_file, encoding='utf-8')
        return self.data
    
    def load(self) -> pd.DataFrame:
        """
        自动检测文件格式并加载
        
        Returns:
            DataFrame: 加载的数据
        """
        if self.results_file.suffix == '.jsonl':
            return self.load_jsonl()
        elif self.results_file.suffix == '.csv':
            return self.load_csv()
        else:
            raise ValueError(f"Unsupported file format: {self.results_file.suffix}")
    
    def get_summary_by_condition(self) -> pd.DataFrame:
        """
        按实验条件统计汇总
        
        Returns:
            DataFrame: 条件汇总统计
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        summary = self.data.groupby('condition_name')['negative_choice_index'].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std'),
            ('min', 'min'),
            ('max', 'max'),
            ('median', 'median')
        ]).reset_index()
        
        # 条件名称映射
        condition_map = {
            'independent': 'P1',
            'low_feedback': 'P2',
            'high_interaction': 'P3'
        }
        summary['platform'] = summary['condition_name'].map(condition_map)
        
        return summary[['condition_name', 'platform', 'count', 'mean', 'std', 'min', 'max', 'median']]
    
    def get_summary_by_persona(self) -> pd.DataFrame:
        """
        按个性类型统计汇总
        
        Returns:
            DataFrame: 个性汇总统计
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        summary = self.data.groupby('persona_name')['negative_choice_index'].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std'),
            ('min', 'min'),
            ('max', 'max')
        ]).reset_index()
        
        return summary
    
    def get_summary_by_scenario(self) -> pd.DataFrame:
        """
        按场景统计汇总
        
        Returns:
            DataFrame: 场景汇总统计
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        summary = self.data.groupby('scenario_name')['negative_choice_index'].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std'),
            ('min', 'min'),
            ('max', 'max')
        ]).reset_index()
        
        return summary

    def get_summary_by_model(self) -> pd.DataFrame:
        """
        按模型统计汇总（用于快速比较不同LLM）。

        Returns:
            DataFrame: 模型汇总统计；若无模型字段则返回空表
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")

        if 'model_name_used' not in self.data.columns:
            return pd.DataFrame()

        data = self.data.copy()
        data['model_name_used'] = data['model_name_used'].fillna('unknown')
        if 'model_api_style_used' not in data.columns:
            data['model_api_style_used'] = 'unknown'
        else:
            data['model_api_style_used'] = data['model_api_style_used'].fillna('unknown')

        summary = data.groupby(['model_api_style_used', 'model_name_used'])['negative_choice_index'].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std'),
            ('min', 'min'),
            ('max', 'max'),
            ('median', 'median')
        ]).reset_index()

        return summary

    def get_summary_by_model_condition(self) -> pd.DataFrame:
        """
        按模型×条件统计（用于快速评估平台差异）。

        Returns:
            DataFrame: 模型×条件汇总；若无模型字段则返回空表
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")

        if 'model_name_used' not in self.data.columns:
            return pd.DataFrame()

        data = self.data.copy()
        data['model_name_used'] = data['model_name_used'].fillna('unknown')
        if 'model_api_style_used' not in data.columns:
            data['model_api_style_used'] = 'unknown'
        else:
            data['model_api_style_used'] = data['model_api_style_used'].fillna('unknown')

        condition_map = {
            'independent': 'P1',
            'low_feedback': 'P2',
            'high_interaction': 'P3'
        }
        data['platform'] = data['condition_name'].map(condition_map)

        summary = data.groupby(
            ['model_api_style_used', 'model_name_used', 'condition_name', 'platform']
        )['negative_choice_index'].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std')
        ]).reset_index()

        return summary
    
    def get_multidimensional_summary(self) -> pd.DataFrame:
        """
        多维度综合汇总（条件×个性×场景）
        
        Returns:
            DataFrame: 多维度汇总统计
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        # 条件名称映射
        condition_map = {
            'independent': 'P1',
            'low_feedback': 'P2',
            'high_interaction': 'P3'
        }
        data = self.data.copy()
        data['platform'] = data['condition_name'].map(condition_map)
        
        summary = data.groupby(['scenario_name', 'platform', 'persona_name'])['negative_choice_index'].agg([
            ('count', 'count'),
            ('mean', 'mean'),
            ('std', 'std'),
            ('n', 'count')
        ]).reset_index()
        
        # 计算95%置信区间
        summary['ci_95'] = 1.96 * summary['std'] / (summary['n'] ** 0.5)
        summary['ci_lower'] = summary['mean'] - summary['ci_95']
        summary['ci_upper'] = summary['mean'] + summary['ci_95']
        
        return summary[['scenario_name', 'platform', 'persona_name', 'count', 'mean', 'std', 'ci_lower', 'ci_upper']]

    def get_dynamic_metrics_summary(self) -> pd.DataFrame:
        """
        动态指标汇总（按条件×时间步）

        仅在数据包含对应列时输出：
        - group_consensus_ratio (GCR)
        - social_signal_asymmetry (SSA)
        - persuasion_effect_score (PES)
        - stance_change_magnitude (SCM)
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")

        required = [
            'condition_name', 'timestep',
            'group_consensus_ratio', 'social_signal_asymmetry',
            'persuasion_effect_score', 'stance_change_magnitude'
        ]
        if not all(col in self.data.columns for col in required):
            return pd.DataFrame()

        data = self.data.copy()
        # 关键口径：P2为静态反馈，不具备真实可观测的点赞/回复网络演化。
        # 因此 GCR/SSA/PES/SCM 的动态汇总仅在 P3（high_interaction）输出。
        data = data[data['condition_name'] == 'high_interaction'].copy()
        if data.empty:
            return pd.DataFrame()
        if 'p3_copresence_size' not in data.columns:
            data['p3_copresence_size'] = pd.NA
        if 'p3_is_higher_order_event' not in data.columns:
            data['p3_is_higher_order_event'] = pd.NA

        condition_map = {
            'independent': 'P1',
            'low_feedback': 'P2',
            'high_interaction': 'P3'
        }
        data['platform'] = data['condition_name'].map(condition_map)

        summary = data.groupby(['platform', 'condition_name', 'timestep']).agg(
            n=('negative_choice_index', 'count'),
            nci_mean=('negative_choice_index', 'mean'),
            gcr_mean=('group_consensus_ratio', 'mean'),
            ssa_mean=('social_signal_asymmetry', 'mean'),
            pes_mean=('persuasion_effect_score', 'mean'),
            scm_mean=('stance_change_magnitude', 'mean'),
            copresence_mean=('p3_copresence_size', 'mean'),
            copresence_max=('p3_copresence_size', 'max'),
        ).reset_index()

        if 'p3_is_higher_order_event' in data.columns:
            hoe_ratio = (
                data.groupby(['platform', 'condition_name', 'timestep'])['p3_is_higher_order_event']
                .mean()
                .reset_index(name='higher_order_event_ratio')
            )
            summary = summary.merge(
                hoe_ratio,
                on=['platform', 'condition_name', 'timestep'],
                how='left',
            )

        return summary

    def get_higher_order_mechanism_summary(
        self,
        cmt_threshold: float = 0.60,
        cmt_hold_steps: int = 2,
    ) -> pd.DataFrame:
        """
        计算高阶机制汇总（图8/表6口径）：CMT、ASI、HO-Event、共在规模、放大比R。

        仅在包含P3动态字段时输出；否则返回空表。
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")

        required = [
            'condition_name', 'scenario_name', 'persona_name', 'climate_type',
            'repeat_index', 'timestep', 'negative_choice_index',
            'group_consensus_ratio', 'p3_is_higher_order_event', 'p3_copresence_size'
        ]
        if not all(col in self.data.columns for col in required):
            return pd.DataFrame()

        data = self.data.copy()

        # 1) 计算分层单元放大比 R（scenario × persona × climate × repeat）
        unit_means = (
            data.groupby(
                ['scenario_name', 'persona_name', 'climate_type', 'repeat_index', 'condition_name'],
                dropna=False,
            )['negative_choice_index']
            .mean()
            .reset_index()
        )
        pivot = unit_means.pivot_table(
            index=['scenario_name', 'persona_name', 'climate_type', 'repeat_index'],
            columns='condition_name',
            values='negative_choice_index',
            aggfunc='mean',
        ).reset_index()

        for c in ['independent', 'low_feedback', 'high_interaction']:
            if c not in pivot.columns:
                pivot[c] = pd.NA

        pivot['delta_21'] = pivot['low_feedback'] - pivot['independent']
        pivot['delta_32'] = pivot['high_interaction'] - pivot['low_feedback']
        eps = 1e-9
        pivot['R'] = pivot.apply(
            lambda r: (r['delta_32'] / r['delta_21'])
            if pd.notna(r['delta_21']) and abs(float(r['delta_21'])) > eps else pd.NA,
            axis=1,
        )

        # 2) 仅P3做机制统计
        p3 = data[data['condition_name'] == 'high_interaction'].copy()
        if p3.empty:
            return pd.DataFrame()

        grp_keys = ['scenario_name', 'persona_name', 'climate_type', 'repeat_index']

        rows: List[Dict[str, Any]] = []
        for key_vals, g in p3.groupby(grp_keys, dropna=False):
            g = g.sort_values('timestep').copy()

            # CMT: 首次达到并连续保持阈值 cmt_hold_steps
            ts = (
                g.groupby('timestep', dropna=False)['negative_choice_index']
                .apply(lambda s: (s >= 3).mean())
                .sort_index()
            )
            cmt_val = pd.NA
            t_list = list(ts.index)
            for i in range(0, len(t_list) - cmt_hold_steps + 1):
                window = [ts.iloc[i + j] for j in range(cmt_hold_steps)]
                if all(pd.notna(v) and float(v) >= cmt_threshold for v in window):
                    cmt_val = t_list[i]
                    break

            # ASI: max |ΔGCR|
            gcr_ts = (
                g.groupby('timestep', dropna=False)['group_consensus_ratio']
                .mean()
                .sort_index()
            )
            if len(gcr_ts) >= 2:
                asi_val = gcr_ts.diff().abs().max()
            else:
                asi_val = pd.NA

            # HO事件占比、共在规模
            ho_ratio = pd.to_numeric(g['p3_is_higher_order_event'], errors='coerce').mean()
            cop_mean = pd.to_numeric(g['p3_copresence_size'], errors='coerce').mean()

            row = {
                'scenario_name': key_vals[0],
                'persona_name': key_vals[1],
                'climate_type': key_vals[2],
                'repeat_index': key_vals[3],
                'CMT': cmt_val,
                'ASI': asi_val,
                'HO_Event_Ratio': ho_ratio,
                'Copresence_Mean': cop_mean,
            }

            r_match = pivot[
                (pivot['scenario_name'] == key_vals[0])
                & (pivot['persona_name'] == key_vals[1])
                & (pivot['climate_type'] == key_vals[2])
                & (pivot['repeat_index'] == key_vals[3])
            ]
            row['R'] = r_match['R'].iloc[0] if not r_match.empty else pd.NA
            rows.append(row)

        unit_df = pd.DataFrame(rows)
        if unit_df.empty:
            return unit_df

        # 3) 聚合到表6口径（scenario × persona × climate）
        summary = (
            unit_df.groupby(['scenario_name', 'persona_name', 'climate_type'], dropna=False)
            .agg(
                CMT_median=('CMT', 'median'),
                CMT_not_reached_rate=('CMT', lambda s: s.isna().mean()),
                ASI_mean=('ASI', 'mean'),
                HO_Event_Ratio=('HO_Event_Ratio', 'mean'),
                Copresence_mean=('Copresence_Mean', 'mean'),
                R_mean=('R', 'mean'),
                N_cells=('repeat_index', 'count'),
            )
            .reset_index()
        )

        return summary

    def get_p3_individual_nci_trajectory(self) -> pd.DataFrame:
        """
        获取P3阶段个体NCI时间演化轨迹。

        输出粒度：scenario × climate × persona × repeat × agent × timestep。
        同时给出：
        - nci_delta_prev: 相比上一步变化
        - nci_delta_from_start: 相比该个体在P3的起点变化
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")

        required = [
            'condition_name', 'scenario_name', 'climate_type', 'persona_name',
            'repeat_index', 'agent_id', 'negative_choice_index'
        ]
        if not all(col in self.data.columns for col in required):
            return pd.DataFrame()

        p3 = self.data[self.data['condition_name'] == 'high_interaction'].copy()
        if p3.empty:
            return pd.DataFrame()

        if 'timestep' not in p3.columns:
            if 'round_index' in p3.columns:
                p3['timestep'] = p3['round_index']
            else:
                p3['timestep'] = 1

        p3['timestep'] = pd.to_numeric(p3['timestep'], errors='coerce')
        p3['negative_choice_index'] = pd.to_numeric(p3['negative_choice_index'], errors='coerce')
        p3 = p3.dropna(subset=['timestep', 'negative_choice_index'])
        if p3.empty:
            return pd.DataFrame()

        group_cols = [
            'scenario_name', 'climate_type', 'persona_name',
            'repeat_index', 'agent_id', 'timestep'
        ]
        traj = (
            p3.groupby(group_cols, dropna=False)['negative_choice_index']
            .mean()
            .reset_index(name='nci')
            .sort_values(group_cols)
        )

        id_cols = ['scenario_name', 'climate_type', 'persona_name', 'repeat_index', 'agent_id']
        traj['nci_delta_prev'] = traj.groupby(id_cols)['nci'].diff()
        traj['nci_start'] = traj.groupby(id_cols)['nci'].transform('first')
        traj['nci_delta_from_start'] = traj['nci'] - traj['nci_start']

        return traj[[
            'scenario_name', 'climate_type', 'persona_name', 'repeat_index', 'agent_id',
            'timestep', 'nci', 'nci_delta_prev', 'nci_delta_from_start'
        ]]

    def get_p3_nci_trajectory_summary(self) -> pd.DataFrame:
        """
        获取P3 NCI演化的群体摘要（按 timestep 聚合）。
        """
        traj = self.get_p3_individual_nci_trajectory()
        if traj.empty:
            return pd.DataFrame()

        summary = (
            traj.groupby(['scenario_name', 'climate_type', 'timestep'], dropna=False)
            .agg(
                count=('nci', 'count'),
                nci_mean=('nci', 'mean'),
                nci_std=('nci', 'std'),
                nci_delta_prev_mean=('nci_delta_prev', 'mean'),
                nci_delta_from_start_mean=('nci_delta_from_start', 'mean'),
            )
            .reset_index()
            .sort_values(['scenario_name', 'climate_type', 'timestep'])
        )
        return summary

    def get_final_nci_comparison_p1_p2_p3(self) -> pd.DataFrame:
        """
        对比最终NCI：P3终点 vs P2终点 vs P1。

        对齐键：scenario_name × persona_name × repeat_index × climate_type（P1无climate，仅作为基线并入）。
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")

        required = [
            'condition_name', 'scenario_name', 'persona_name', 'repeat_index',
            'climate_type', 'negative_choice_index'
        ]
        if not all(col in self.data.columns for col in required):
            return pd.DataFrame()

        data = self.data.copy()
        if 'timestep' not in data.columns:
            if 'round_index' in data.columns:
                data['timestep'] = data['round_index']
            else:
                data['timestep'] = 1
        data['timestep'] = pd.to_numeric(data['timestep'], errors='coerce')
        data['negative_choice_index'] = pd.to_numeric(data['negative_choice_index'], errors='coerce')
        data = data.dropna(subset=['timestep', 'negative_choice_index'])
        if data.empty:
            return pd.DataFrame()

        base_keys = ['scenario_name', 'persona_name', 'repeat_index']
        climate_keys = base_keys + ['climate_type']

        # P1基线（每个单元取最终步；通常只有t=1）
        p1 = data[data['condition_name'] == 'independent'].copy()
        if p1.empty:
            return pd.DataFrame()
        p1 = p1.sort_values('timestep').groupby(base_keys, dropna=False).tail(1)
        p1 = p1[base_keys + ['negative_choice_index']].rename(columns={'negative_choice_index': 'nci_p1'})

        # P2最终
        p2 = data[data['condition_name'] == 'low_feedback'].copy()
        if p2.empty:
            return pd.DataFrame()
        p2 = p2.sort_values('timestep').groupby(climate_keys, dropna=False).tail(1)
        p2 = p2[climate_keys + ['negative_choice_index']].rename(columns={'negative_choice_index': 'nci_p2_final'})

        # P3最终
        p3 = data[data['condition_name'] == 'high_interaction'].copy()
        if p3.empty:
            return pd.DataFrame()
        p3 = p3.sort_values('timestep').groupby(climate_keys, dropna=False).tail(1)
        p3 = p3[climate_keys + ['negative_choice_index']].rename(columns={'negative_choice_index': 'nci_p3_final'})

        merged = p3.merge(p2, on=climate_keys, how='left').merge(p1, on=base_keys, how='left')
        if merged.empty:
            return pd.DataFrame()

        merged['delta_p3_minus_p2'] = merged['nci_p3_final'] - merged['nci_p2_final']
        merged['delta_p2_minus_p1'] = merged['nci_p2_final'] - merged['nci_p1']
        merged['delta_p3_minus_p1'] = merged['nci_p3_final'] - merged['nci_p1']

        return merged[[
            'scenario_name', 'climate_type', 'persona_name', 'repeat_index',
            'nci_p1', 'nci_p2_final', 'nci_p3_final',
            'delta_p3_minus_p2', 'delta_p2_minus_p1', 'delta_p3_minus_p1'
        ]].sort_values(['scenario_name', 'climate_type', 'persona_name', 'repeat_index'])

    def get_final_nci_comparison_summary(self) -> pd.DataFrame:
        """
        最终NCI对比的摘要统计（scenario × climate）。
        """
        comp = self.get_final_nci_comparison_p1_p2_p3()
        if comp.empty:
            return pd.DataFrame()

        summary = (
            comp.groupby(['scenario_name', 'climate_type'], dropna=False)
            .agg(
                count=('nci_p3_final', 'count'),
                nci_p1_mean=('nci_p1', 'mean'),
                nci_p2_final_mean=('nci_p2_final', 'mean'),
                nci_p3_final_mean=('nci_p3_final', 'mean'),
                delta_p3_minus_p2_mean=('delta_p3_minus_p2', 'mean'),
                delta_p2_minus_p1_mean=('delta_p2_minus_p1', 'mean'),
                delta_p3_minus_p1_mean=('delta_p3_minus_p1', 'mean'),
            )
            .reset_index()
            .sort_values(['scenario_name', 'climate_type'])
        )
        return summary
    
    def save_summary_statistics(self, output_dir: Path):
        """
        生成并保存所有统计摘要
        
        Args:
            output_dir: 输出目录
        """
        if self.data is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存各类汇总
        self.get_summary_by_condition().to_csv(
            output_dir / 'summary_by_condition.csv',
            index=False, encoding='utf-8'
        )
        print("✓ 已保存: summary_by_condition.csv")
        
        self.get_summary_by_persona().to_csv(
            output_dir / 'summary_by_persona.csv',
            index=False, encoding='utf-8'
        )
        print("✓ 已保存: summary_by_persona.csv")
        
        self.get_summary_by_scenario().to_csv(
            output_dir / 'summary_by_scenario.csv',
            index=False, encoding='utf-8'
        )
        print("✓ 已保存: summary_by_scenario.csv")
        
        self.get_multidimensional_summary().to_csv(
            output_dir / 'summary_multidimensional.csv',
            index=False, encoding='utf-8'
        )
        print("✓ 已保存: summary_multidimensional.csv")

        dynamic_summary = self.get_dynamic_metrics_summary()
        if not dynamic_summary.empty:
            dynamic_summary.to_csv(
                output_dir / 'summary_dynamic_metrics.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: summary_dynamic_metrics.csv")

        mechanism_summary = self.get_higher_order_mechanism_summary()
        if not mechanism_summary.empty:
            mechanism_summary.to_csv(
                output_dir / 'summary_higher_order_mechanisms.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: summary_higher_order_mechanisms.csv")

        summary_by_model = self.get_summary_by_model()
        if not summary_by_model.empty:
            summary_by_model.to_csv(
                output_dir / 'summary_by_model.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: summary_by_model.csv")

        summary_by_model_condition = self.get_summary_by_model_condition()
        if not summary_by_model_condition.empty:
            summary_by_model_condition.to_csv(
                output_dir / 'summary_by_model_condition.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: summary_by_model_condition.csv")

        p3_traj = self.get_p3_individual_nci_trajectory()
        if not p3_traj.empty:
            p3_traj.to_csv(
                output_dir / 'p3_individual_nci_trajectory.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: p3_individual_nci_trajectory.csv")

        p3_traj_summary = self.get_p3_nci_trajectory_summary()
        if not p3_traj_summary.empty:
            p3_traj_summary.to_csv(
                output_dir / 'summary_p3_nci_trajectory_by_timestep.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: summary_p3_nci_trajectory_by_timestep.csv")

        final_comp = self.get_final_nci_comparison_p1_p2_p3()
        if not final_comp.empty:
            final_comp.to_csv(
                output_dir / 'final_nci_comparison_p1_p2_p3.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: final_nci_comparison_p1_p2_p3.csv")

        final_comp_summary = self.get_final_nci_comparison_summary()
        if not final_comp_summary.empty:
            final_comp_summary.to_csv(
                output_dir / 'summary_final_nci_comparison_p1_p2_p3.csv',
                index=False, encoding='utf-8'
            )
            print("✓ 已保存: summary_final_nci_comparison_p1_p2_p3.csv")


class ExperimentLogger:
    """实验日志记录器"""
    
    def __init__(self, log_file: Path):
        """
        初始化日志记录器
        
        Args:
            log_file: 日志文件路径
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log(self, level: str, message: str, details: Optional[Dict[str, Any]] = None):
        """
        记录日志
        
        Args:
            level: 日志级别（INFO, WARNING, ERROR, DEBUG）
            message: 日志消息
            details: 额外的详细信息字典
        """
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'message': message,
            'details': details or {}
        }
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录INFO级别日志"""
        self.log('INFO', message, details)
    
    def warning(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录WARNING级别日志"""
        self.log('WARNING', message, details)
    
    def error(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录ERROR级别日志"""
        self.log('ERROR', message, details)
    
    def debug(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录DEBUG级别日志"""
        self.log('DEBUG', message, details)


if __name__ == "__main__":
    # 示例用法
    
    # 1. 读取结果
    reader = ExperimentResultReader(Path("./outputs/results.jsonl"))
    reader.load()
    
    # 2. 生成汇总统计
    print("条件汇总:")
    print(reader.get_summary_by_condition())
    
    print("\n个性汇总:")
    print(reader.get_summary_by_persona())
    
    print("\n场景汇总:")
    print(reader.get_summary_by_scenario())
    
    # 3. 保存所有统计
    reader.save_summary_statistics(Path("./outputs/figures"))
