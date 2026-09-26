"""
核心运行时引擎子系统 (Core Runtime Package)
提供 Agent 构建器 (builder)、配置定义 (config) 与大语言模型驱动连接器 (model)。
"""

from core.runtime.config import AgentConfig
from core.runtime.model import create_chat_model
from core.runtime.builder import build_agent, StandaloneAgent

__all__ = [
    "AgentConfig",
    "create_chat_model",
    "build_agent",
    "StandaloneAgent",
]
