"""
单元测试：AgentSandbox 独立沙箱工作空间与安全文件读写
纯本地测试，验证工作空间隔离、路径防穿越攻击以及文件工具。
"""

import sys
import tempfile
import pytest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.sandbox import AgentSandbox


def test_sandbox_path_jail_security():
    """测试沙箱路径防越界越权保护 (防目录遍历攻击)"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = AgentSandbox("SecureAgent", base_dir=tmp_dir)

        # 1. 正常子路径允许访问
        safe_path = sandbox._resolve_safe_path("reports/summary.md")
        assert safe_path.is_relative_to(sandbox.sandbox_dir)

        # 2. 尝试使用 ../ 逃逸沙箱目录应当被严厉抛出 PermissionError
        with pytest.raises(PermissionError):
            sandbox._resolve_safe_path("../../../etc/passwd")

        with pytest.raises(PermissionError):
            sandbox._resolve_safe_path("sub/../../outside.txt")


def test_sandbox_file_tools():
    """测试沙箱挂载的 write_file, read_file 与 list_files 工具功能"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = AgentSandbox("FileTestAgent", base_dir=tmp_dir)
        tools_dict = {t.name: t for t in sandbox.get_tools()}

        assert "write_file" in tools_dict
        assert "read_file" in tools_dict
        assert "list_files" in tools_dict
        assert "execute_python_code" in tools_dict

        write_tool = tools_dict["write_file"]
        read_tool = tools_dict["read_file"]
        list_tool = tools_dict["list_files"]

        # 1. 写入文件
        res_write = write_tool.invoke({"file_path": "data/output.txt", "content": "Hello Sandbox!"})
        assert "成功" in res_write

        # 2. 读取文件
        res_read = read_tool.invoke({"file_path": "data/output.txt"})
        assert res_read == "Hello Sandbox!"

        # 3. 列出文件
        res_list = list_tool.invoke({"sub_directory": "data"})
        assert "output.txt" in res_list
