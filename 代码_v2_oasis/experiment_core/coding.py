"""
决策编码模块 (coding.py)

负责将Agent的结构化决策转换为实验指标(NCI、SCM、PES等)

论文公式系统:
- Stance = ContentScore + SocialScore + GroupScore
- NCI(主指标) = 四维负向选择计数和 [范围: 0-4]
- NCI_intensity(辅指标) = 2.0 + Stance × (4/3)  [范围: 0-4]
- PES = |SocialScore + GroupScore|
- SCM = |NCI_t - NCI_{t-1}|（与主指标同口径）
"""

from typing import Dict, Tuple, Optional
import json
from datetime import datetime, timezone

from .schemas import (
    DecisionResponse,
    ExperimentRecord,
    ChoiceBinary,
    ChoiceTernary,
    CommentChoice,
)


class DecisionEncoder:
    """决策编码器，将四维决策转换为量化指标"""
    
    @staticmethod
    def encode_choice(choice: str, is_negative: bool = True) -> float:
        """
        编码单个选择为数值
        
        Args:
            choice: 选择值
            is_negative: 是否计算负面选择
            
        Returns:
            float: 编码值 (-1 ~ +1)
        """
        if choice == "none" or choice == "neutral":
            return 0.0
        
        if is_negative:
            if choice == "negative" or choice == "support_negative":
                return 1.0
            elif choice == "positive" or choice == "support_positive":
                return -1.0
        else:
            if choice == "positive" or choice == "support_positive":
                return 1.0
            elif choice == "negative" or choice == "support_negative":
                return -1.0
        
        return 0.0
    
    @staticmethod
    def compute_scores(
        decision: DecisionResponse,
    ) -> Tuple[float, float, float]:
        """
        从四维决策计算三个分量分数
        
        论文公式: Stance = ContentScore + SocialScore + GroupScore
        
        Args:
            decision: 四维决策
            
        Returns:
            Tuple[float, float, float]: (ContentScore, SocialScore, GroupScore)
        """
        # ContentScore: 基于credible_choice
        content_score = DecisionEncoder.encode_choice(decision.credible_choice, is_negative=True)
        
        # SocialScore: 平均like_choice和share_choice
        like_score = DecisionEncoder.encode_choice(decision.like_choice, is_negative=True)
        share_score = DecisionEncoder.encode_choice(decision.share_choice, is_negative=True)
        social_score = (like_score + share_score) / 2.0
        
        # GroupScore: 基于comment_choice
        group_score = DecisionEncoder.encode_choice(decision.comment_choice, is_negative=True)
        
        return content_score, social_score, group_score
    
    @staticmethod
    def compute_nci(
        content_score: float,
        social_score: float,
        group_score: float,
    ) -> float:
        """
        计算连续强度型 NCI（辅指标）
        
        论文公式:
        Stance = ContentScore + SocialScore + GroupScore
        NCI = 2.0 + Stance × (4/3)
        
        范围: 0-4
        - 0: 完全选择正面信息
        - 2: 中立，无偏好
        - 4: 完全选择负面信息
        
        Args:
            content_score: 内容倾向分数 (-1 ~ +1)
            social_score: 社交倾向分数 (-1 ~ +1)
            group_score: 群体倾向分数 (-1 ~ +1)
            
        Returns:
            float: NCI值 (0-4)
        """
        # 计算总体立场
        stance = content_score + social_score + group_score
        
        # 转换为NCI值
        nci = 2.0 + stance * (4.0 / 3.0)
        
        # 限制在0-4范围内
        nci = max(0.0, min(4.0, nci))
        
        return nci

    @staticmethod
    def compute_nci_binary(decision: DecisionResponse) -> int:
        """计算离散主指标 NCI（0-4）。"""

        credibility_negative = int(decision.credible_choice == "negative")
        like_negative = int(decision.like_choice == "negative")
        share_negative = int(decision.share_choice == "negative")
        comment_negative = int(decision.comment_choice == "support_negative")
        return (
            credibility_negative
            + like_negative
            + share_negative
            + comment_negative
        )
    
    @staticmethod
    def compute_pes(
        social_score: float,
        group_score: float,
    ) -> float:
        """
        计算说服效应强度 (PES)
        
        论文公式: PES = |SocialScore + GroupScore|
        
        Args:
            social_score: 社交倾向分数
            group_score: 群体倾向分数
            
        Returns:
            float: PES值 (0-2)
        """
        combined_social_effect = abs(social_score + group_score)
        return combined_social_effect
    
    @staticmethod
    def encode_decision(
        decision: DecisionResponse,
        previous_nci: float = 2.0,
    ) -> Dict:
        """
        完整的决策编码流程
        
        Args:
            decision: Agent的四维决策响应
            previous_nci: 上一时刻的NCI(用于计算SCM)
            
        Returns:
            Dict: 包含所有指标的字典
        """
        # 计算三个分量分数
        content_score, social_score, group_score = DecisionEncoder.compute_scores(decision)
        
        # 计算总体立场
        stance = content_score + social_score + group_score
        
        # 计算NCI：主指标(离散) + 辅指标(连续强度)
        nci = DecisionEncoder.compute_nci_binary(decision)
        nci_intensity = DecisionEncoder.compute_nci(
            content_score,
            social_score,
            group_score,
        )
        
        # 计算PES
        pes = DecisionEncoder.compute_pes(social_score, group_score)
        
        # 计算SCM
        scm = abs(float(nci) - float(previous_nci))

        credibility_negative = int(decision.credible_choice == "negative")
        like_negative = int(decision.like_choice == "negative")
        share_negative = int(decision.share_choice == "negative")
        comment_negative = int(decision.comment_choice == "support_negative")
        
        return {
            "negative_choice_index": nci,
            "negative_choice_intensity": nci_intensity,
            "content_score": content_score,
            "social_score": social_score,
            "group_score": group_score,
            "stance": stance,
            "persuasion_effect_score": pes,
            "stance_change_magnitude": scm,
            "credibility_negative": credibility_negative,
            "like_negative": like_negative,
            "share_negative": share_negative,
            "comment_negative": comment_negative,
        }


class LLMResponseParser:
    """LLM响应解析器"""
    
    @staticmethod
    def parse_json_response(response_text: str) -> Optional[DecisionResponse]:
        """
        从LLM的JSON响应解析出DecisionResponse
        
        根据论文设计（4.2 测量维度），credible_choice应该允许positive/neutral/negative
        
        Args:
            response_text: LLM返回的文本
            
        Returns:
            Optional[DecisionResponse]: 解析成功返回DecisionResponse
        """
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    return None
            else:
                return None
        
        try:
            # 数据修正：将不合法的值转换为合法值
            # credible_choice: 如果是 'none'，转换为 'neutral'
            if data.get('credible_choice') == 'none':
                data['credible_choice'] = 'neutral'
            
            # like_choice, share_choice: 如果不在允许的值中，设置为 'none'
            valid_ternary = {'positive', 'negative', 'none'}
            if data.get('like_choice') and data['like_choice'] not in valid_ternary:
                data['like_choice'] = 'none'
            if data.get('share_choice') and data['share_choice'] not in valid_ternary:
                data['share_choice'] = 'none'
            
            # comment_choice: 如果不是允许的值，默认为 'neutral'
            valid_comment = {'support_positive', 'support_negative', 'neutral'}
            if data.get('comment_choice') and data['comment_choice'] not in valid_comment:
                data['comment_choice'] = 'neutral'
            
            decision = DecisionResponse(**data)
            return decision
        except Exception as e:
            # 降级方案：当验证失败时尝试修正
            print(f"解析DecisionResponse失败: {e}")
            
            # 不再进行修正，直接返回None，让上层处理器使用默认值
            return None


def code_negative_index(response: DecisionResponse) -> dict[str, int]:
    """
    [已弃用] 旧的编码函数，保留向后兼容性
    
    使用新的DecisionEncoder.encode_decision()代替
    """
    # 单项编码（0 或 1）
    credibility_negative = int(response.credible_choice == "negative")
    like_negative = int(response.like_choice == "negative")
    share_negative = int(response.share_choice == "negative")
    comment_negative = int(response.comment_choice == "support_negative")

    # 计算负面信息选择指数（0-4 分）
    negative_choice_index = (
        credibility_negative
        + like_negative
        + share_negative
        + comment_negative
    )

    # 分类指标
    belief_negative = credibility_negative  # 信念维度
    propagation_negative = like_negative + share_negative  # 传播维度（0-2）
    expression_negative = comment_negative  # 表达维度

    return {
        # 单项指标
        "credibility_negative": credibility_negative,
        "like_negative": like_negative,
        "share_negative": share_negative,
        "comment_negative": comment_negative,
        # 综合指标
        "negative_choice_index": negative_choice_index,
        # 分类指标
        "belief_negative": belief_negative,
        "propagation_negative": propagation_negative,
        "expression_negative": expression_negative,
    }


def code_positive_index(response: DecisionResponse) -> dict[str, int]:
    """
    将决策响应编码为正向信息选择指标（与负面互补）。

    Args:
        response: 模型的结构化决策输出

    Returns:
        dict: 包含各项编码指标的字典
    """
    # 单项编码（0 或 1）
    credibility_positive = int(response.credible_choice == "positive")
    like_positive = int(response.like_choice == "positive")
    share_positive = int(response.share_choice == "positive")
    comment_positive = int(response.comment_choice == "support_positive")

    # 计算正向信息选择指数（0-4 分）
    positive_choice_index = (
        credibility_positive
        + like_positive
        + share_positive
        + comment_positive
    )

    return {
        "credibility_positive": credibility_positive,
        "like_positive": like_positive,
        "share_positive": share_positive,
        "comment_positive": comment_positive,
        "positive_choice_index": positive_choice_index,
    }


def code_neutrality(response: DecisionResponse) -> dict[str, int]:
    """
    计算决策中的中立程度。

    Args:
        response: 模型的结构化决策输出

    Returns:
        dict: 包含中立相关指标的字典
    """
    like_none = int(response.like_choice == "none")
    share_none = int(response.share_choice == "none")
    comment_neutral = int(response.comment_choice == "neutral")

    return {
        "like_none": like_none,
        "share_none": share_none,
        "comment_neutral": comment_neutral,
        "avoidance_index": like_none + share_none + comment_neutral,  # 0-3
    }


def compute_all_indices(response: DecisionResponse) -> dict[str, int]:
    """
    计算所有编码指标。

    Args:
        response: 模型的结构化决策输出

    Returns:
        dict: 所有编码指标的综合字典
    """
    negative = code_negative_index(response)
    positive = code_positive_index(response)
    neutral = code_neutrality(response)

    return {**negative, **positive, **neutral}
