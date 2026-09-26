"""
模型初始化模块 (Runtime Model Loader)
根据 AgentConfig 参数实例化标准 LangChain ChatModel。
"""

import os
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from core.runtime.config import AgentConfig


def create_chat_model(config: AgentConfig) -> BaseChatModel:
    """
    根据配置创建并返回对应的 BaseChatModel 实例。
    统一基于 OpenAI 兼容协议支持 DeepSeek、OpenAI 及各类兼容端点。
    """
    provider = config.provider.lower()

    # 确定 model_name
    model_name = config.model_name
    if not model_name:
        if provider == "deepseek":
            model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        elif provider == "openai":
            model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
        else:
            model_name = "gpt-4o"

    # 确定 api_key
    api_key = config.api_key
    if not api_key:
        if provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            f"未找到 Provider '{config.provider}' 对应的 API Key。请在 AgentConfig 中传入或在 .env 中设置。"
        )

    # 确定 base_url
    base_url = config.base_url
    if not base_url:
        if provider == "deepseek":
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        elif provider == "openai":
            base_url = os.getenv("OPENAI_BASE_URL")

    def _clean_str(val: Optional[str]) -> Optional[str]:
        if val is not None and isinstance(val, str):
            return val.strip().strip('"').strip("'")
        return val

    model_name = _clean_str(model_name)
    api_key = _clean_str(api_key)
    base_url = _clean_str(base_url)

    # 实例化 ChatOpenAI（支持 DeepSeek 及任意 OpenAI 兼容接口）
    model_kwargs = {
        "model": model_name,
        "api_key": api_key,
        "temperature": config.temperature,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
    }
    if base_url:
        model_kwargs["base_url"] = base_url

    return ChatOpenAI(**model_kwargs)
