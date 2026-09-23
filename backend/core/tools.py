"""
Agent 工具库模块
提供内置常用工具以及工具定义支持。
"""

from datetime import datetime
from langchain_core.tools import tool


@tool
def get_current_time() -> str:
    """获取当前的系统日期和时间（北京时间/本地时间格式）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def calculate(expression: str) -> str:
    """
    计算简单的数学算式。
    示例输入: "125 * 34 + 500"
    """
    allowed_chars = set("0123456789+-*/(). %")
    if not all(c in allowed_chars for c in expression):
        return "错误: 表达式包含不支持的字符，仅允许基础数学算式。"
    try:
        # 安全计算数学表达式
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        return f"计算失败: {e}"


# 默认内置工具列表
DEFAULT_TOOLS = [get_current_time, calculate]
