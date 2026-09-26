"""
基础通用内置工具 (Builtin Tools)
提供当前时间获取、简单算式计算等通用基础工具。
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
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        return f"计算失败: {e}"


BUILTIN_TOOLS = [get_current_time, calculate]
