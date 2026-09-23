"""
Agent 配置定义模块
提供 AgentConfig 类，支持通过参数灵活配置模型、工具、提示词与运行策略。
"""

import os
from typing import Any, Callable, List, Optional, Union
from pydantic import BaseModel, Field
from pathlib import Path
from dotenv import load_dotenv

# 加载当前与上级目录的 .env 环境变量
_config_dir = Path(__file__).resolve().parent
load_dotenv(_config_dir.parent.parent / ".env")
load_dotenv(_config_dir.parent / ".env")
load_dotenv()


class AgentConfig(BaseModel):
    """Agent 配置参数类"""

    name: str = Field(default="AssistantAgent", description="Agent 名称")
    system_prompt: str = Field(
        default="你是一个专业且乐于助人的 AI 助理，能够根据需要调用工具解决问题。",
        description="系统角色提示词",
    )

    # 模型服务商与模型名称
    provider: str = Field(
        default="deepseek",
        description="模型提供商，如 'deepseek', 'openai', 或 'custom'",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="模型名称，如果不传则自动根据 provider 从环境变量获取",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API Key，如果不传则自动根据 provider 从环境变量获取",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="API 接口基础地址，如果不传则自动根据 provider 从环境变量获取",
    )

    # 推理参数
    temperature: float = Field(default=0.0, description="采样温度，0.0-1.0")
    timeout: float = Field(default=120.0, description="请求超时时间（秒）")
    max_retries: int = Field(default=2, description="失败重试次数")

    # 工具配置
    tools: List[Union[Callable[..., Any], Any]] = Field(
        default_factory=list,
        description="赋给 Agent 的工具列表（可为 @tool 装饰的函数或 BaseTool 实例）",
    )

    # 记忆与调试
    enable_memory: bool = Field(default=True, description="是否启用短期对话记忆")
    debug: bool = Field(default=False, description="是否开启调试输出")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_env(
        cls,
        provider: str = "deepseek",
        name: str = "AssistantAgent",
        system_prompt: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> "AgentConfig":
        """从环境变量中自动提取对应 provider 的配置并创建 AgentConfig"""
        provider_lower = provider.lower()

        if provider_lower == "deepseek":
            model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        elif provider_lower == "openai":
            model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")
        else:
            model_name = os.getenv("LANGCHAIN_MODEL_NAME")
            api_key = os.getenv("LANGCHAIN_API_KEY")
            base_url = None

        def _clean_str(val: Optional[str]) -> Optional[str]:
            if val is not None and isinstance(val, str):
                return val.strip().strip('"').strip("'")
            return val

        api_key = _clean_str(api_key)
        base_url = _clean_str(base_url)
        model_name = _clean_str(model_name)

        config_data = {
            "name": name,
            "provider": provider_lower,
            "model_name": model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": float(os.getenv("LANGCHAIN_TEMPERATURE", "0.0")),
            "timeout": float(os.getenv("TIMEOUT_SECONDS", "120")),
            "max_retries": int(os.getenv("MAX_RETRIES", "2")),
            "tools": tools or [],
        }

        if system_prompt:
            config_data["system_prompt"] = system_prompt

        config_data.update(kwargs)
        return cls(**config_data)
