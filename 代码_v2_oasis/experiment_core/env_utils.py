"""
环境变量加载与管理。
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def load_env_file(env_path: Path | str) -> bool:
    """
    加载 .env 文件。

    Args:
        env_path: .env 文件路径

    Returns:
        bool: 是否成功加载
    """
    env_path = Path(env_path)
    if env_path.exists():
        load_dotenv(env_path)
        return True
    return False


def get_api_key(provider: str, key_name: str | None = None) -> str:
    """
    获取 API Key。

    Args:
        provider: 提供商名称 ("zhipu", "openai", "qwen" 等)
        key_name: 自定义环境变量名，如不指定则使用默认

    Returns:
        str: API Key

    Raises:
        ValueError: 如果找不到 API Key
    """
    if key_name:
        api_key = os.getenv(key_name)
    else:
        # 使用约定的环境变量名
        provider_upper = provider.upper()
        api_key = os.getenv(f"{provider_upper}_API_KEY")

    if not api_key:
        raise ValueError(
            f"未找到 {provider} 的 API Key。"
            f"请在 .env 文件中设置 {key_name or f'{provider.upper()}_API_KEY'}"
        )

    return api_key
