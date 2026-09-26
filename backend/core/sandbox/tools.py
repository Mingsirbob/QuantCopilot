"""
沙箱工具工厂模块
为 AgentSandbox 动态构建 execute_python_code、read_file、write_file、list_files 工具。
"""

import sys
import subprocess
from pathlib import Path
from typing import List, TYPE_CHECKING
from langchain_core.tools import BaseTool, tool

if TYPE_CHECKING:
    from core.sandbox.executor import AgentSandbox


def create_sandbox_tools(sandbox: "AgentSandbox") -> List[BaseTool]:
    """生成并返回一组绑定到当前沙箱上下文的 LangChain 动态工具"""

    @tool
    def execute_python_code(code: str) -> str:
        """
        在当前 Agent 的专属隔离工作空间中执行 Python 代码。
        工作目录(CWD)已锁定为当前沙箱，可自由使用 Python 运行数学计算、数据处理（如 pandas/numpy）以及读写本目录文件。
        :param code: 待执行的完整 Python 代码字符串
        :return: 标准输出(stdout)或错误堆栈(stderr)
        """
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(sandbox.sandbox_dir),
                capture_output=True,
                text=True,
                timeout=sandbox.timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
            output = proc.stdout or ""
            if proc.stderr:
                output += f"\n[Stderr/错误信息]:\n{proc.stderr}"
            if proc.returncode != 0:
                output += f"\n[进程退出码]: {proc.returncode}"
            return output if output.strip() else "[代码执行成功，无终端标准输出]"
        except subprocess.TimeoutExpired:
            return f"执行失败: 代码执行超时 (超过 {sandbox.timeout_seconds} 秒)，已被系统强制终止。"
        except Exception as e:
            return f"执行失败: {e}"

    @tool
    def write_file(file_path: str, content: str) -> str:
        """
        在当前 Agent 的专属工作空间内创建或覆盖写入文件。
        :param file_path: 相对沙箱目录的文件路径，例如 'result.json' 或 'reports/summary.md'
        :param content: 文件内容
        """
        try:
            safe_p = sandbox._resolve_safe_path(file_path)
            safe_p.parent.mkdir(parents=True, exist_ok=True)
            with open(safe_p, "w", encoding="utf-8") as f:
                f.write(content)
            return f"文件写入成功: {file_path} (大小: {len(content)} 字符)"
        except Exception as e:
            return f"写入文件失败: {e}"

    @tool
    def read_file(file_path: str) -> str:
        """
        读取当前 Agent 专属工作空间内的文件内容。
        :param file_path: 相对沙箱目录的文件路径
        """
        try:
            safe_p = sandbox._resolve_safe_path(file_path)
            if not safe_p.exists():
                return f"读取失败: 文件不存在 '{file_path}'"
            with open(safe_p, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"读取文件失败: {e}"

    @tool
    def list_files(sub_directory: str = ".") -> str:
        """
        列出当前 Agent 专属工作空间内的文件与子文件夹结构。
        :param sub_directory: 相对沙箱目录的子路径，默认根目录 '.'
        """
        try:
            safe_p = sandbox._resolve_safe_path(sub_directory)
            if not safe_p.exists() or not safe_p.is_dir():
                return f"目录不存在: '{sub_directory}'"
            items = []
            for item in sorted(safe_p.iterdir()):
                item_type = "目录" if item.is_dir() else "文件"
                size_str = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
                items.append(f"[{item_type}] {item.name}{size_str}")
            return "\n".join(items) if items else "当前目录为空。"
        except Exception as e:
            return f"列出目录失败: {e}"

    return [execute_python_code, write_file, read_file, list_files]
