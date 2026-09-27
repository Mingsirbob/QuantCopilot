"""
Pytest 全局配置文件
在运行单元测试和集成测试时，自动隔离网络与禁用第三方云端链路追踪，
确保 Mock FakeChatModel 具有确定性的离线测试行为。
"""

import os
import pytest

# 强制在测试期间禁用 LangSmith 上报，避免测试产生的 Mock 数据污染云端 Project
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""


