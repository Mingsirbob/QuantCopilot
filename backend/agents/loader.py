"""
Agent 模板加载器模块
负责扫描并解析 agents/ 目录下的 Agent 模板，
包括解析 agent.yaml、组装 prompt/skills、连接 MCP 服务器，最终构建为可执行 Agent 实例。
"""

import os
import re
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from core.config import AgentConfig
from core.builder import build_agent, StandaloneAgent

# 确保向上查找并加载根目录与 backend 目录的 .env
_current_dir = Path(__file__).resolve().parent
load_dotenv(_current_dir.parent.parent / ".env")
load_dotenv(_current_dir.parent / ".env")
load_dotenv()


def _resolve_env_vars(text: str) -> str:
    """替换配置字符串中的环境变量占位符，例如 ${Financial-API-KEY}"""
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replace_match(match: re.Match) -> str:
        var_name = match.group(1)
        # 优先读取完全匹配的变量名，随后尝试下划线等兼容形式
        val = os.getenv(var_name)
        if val is None:
            val = os.getenv(var_name.replace("-", "_"))
        if val is None:
            val = os.getenv(var_name.upper())
        if val is None:
            return ""
        return val

    return pattern.sub(replace_match, text)


def _resolve_env_in_dict(data: Any) -> Any:
    """递归替换字典或列表中的环境变量占位符"""
    if isinstance(data, str):
        return _resolve_env_vars(data)
    elif isinstance(data, dict):
        return {k: _resolve_env_in_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_in_dict(item) for item in data]
    return data


class AgentTemplateLoader:
    """Agent 模板加载器"""

    def __init__(self, base_agents_dir: Optional[Union[str, Path]] = None):
        if base_agents_dir is None:
            # 默认指向当前项目下的 agents 目录
            self.base_agents_dir = Path(__file__).resolve().parent
        else:
            self.base_agents_dir = Path(base_agents_dir).resolve()

    def get_agent_path(self, agent_name: str) -> Path:
        """根据名称获取 Agent 目录路径"""
        agent_dir = self.base_agents_dir / agent_name
        if not agent_dir.exists() or not agent_dir.is_dir():
            raise FileNotFoundError(f"未找到 Agent 模板目录: {agent_dir}")
        return agent_dir

    def load_spec(self, agent_name: str) -> Dict[str, Any]:
        """读取 agent.yaml 清单规范"""
        agent_dir = self.get_agent_path(agent_name)
        spec_path = agent_dir / "agent.yaml"
        if not spec_path.exists():
            raise FileNotFoundError(f"Agent 清单配置文件缺失: {spec_path}")

        with open(spec_path, "r", encoding="utf-8") as f:
            raw_spec = yaml.safe_load(f)

        return _resolve_env_in_dict(raw_spec)

    def load_prompt_and_skills(self, agent_name: str, spec: Dict[str, Any]) -> str:
        """组装 Agent 的 prompt.md 和关联的 skills"""
        agent_dir = self.get_agent_path(agent_name)
        prompt_parts: List[str] = []

        # 1. 主人设 prompt.md
        prompt_path = agent_dir / "prompt.md"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_parts.append(f.read().strip())

        # 2. 附加 skills/*.md 文档
        declared_skills = spec.get("skills", [])
        for skill_rel_path in declared_skills:
            skill_file = (agent_dir / skill_rel_path).resolve()
            if skill_file.exists():
                with open(skill_file, "r", encoding="utf-8") as f:
                    skill_content = f.read().strip()
                    prompt_parts.append(
                        f"\n\n--- [附带技能参考: {skill_file.name}] ---\n{skill_content}"
                    )

        return "\n\n".join(prompt_parts)

    async def connect_mcp_servers_async(self, spec: Dict[str, Any]) -> List[BaseTool]:
        """根据 spec 配置连接对应的 MCP 服务端并拉取 tools"""
        mcp_configs = spec.get("mcp_servers", [])
        if not mcp_configs:
            return []

        connections: Dict[str, Any] = {}
        for mcp_item in mcp_configs:
            server_name = mcp_item["name"]
            transport = mcp_item.get("transport", "streamable_http")
            url = mcp_item["url"]
            headers = mcp_item.get("headers", {})

            connections[server_name] = {
                "transport": transport,
                "url": url,
                "headers": headers,
                "timeout": 30.0,
            }

        client = MultiServerMCPClient(connections=connections)
        tools = await client.get_tools()
        return list(tools)

    async def load_agent(
        self,
        agent_name: str,
        extra_tools: Optional[List[Any]] = None,
        override_config: Optional[Dict[str, Any]] = None,
    ) -> StandaloneAgent:
        """
        官方原生异步加载与构建独立 Agent。

        :param agent_name: agents/ 目录下的子文件夹名称（如 "data_scraper"）
        :param extra_tools: 额外附加的本地 Python 工具
        :param override_config: 覆盖默认的模型或推理参数
        """
        spec = self.load_spec(agent_name)

        # 检查所需环境变量
        required_env = spec.get("required_env", [])
        for env_var in required_env:
            val = os.getenv(env_var) or os.getenv(env_var.replace("-", "_"))
            if not val:
                raise ValueError(
                    f"Agent '{agent_name}' 缺少必需的环境变量: {env_var}，请在 .env 中设置。"
                )

        # 1. 组装 Prompt
        full_system_prompt = self.load_prompt_and_skills(agent_name, spec)

        # 2. 动态原生异步拉取 MCP 工具
        mcp_tools = await self.connect_mcp_servers_async(spec)

        # 3. 合并所有工具（MCP 工具 + Agent 专用 local tools + 外部传入 extra_tools）
        all_tools = list(mcp_tools)

        # 检查并加载 Agent 目录内的本地 tools.py (若存在)
        agent_dir = self.get_agent_path(agent_name)
        local_tools_path = agent_dir / "tools.py"
        if local_tools_path.exists():
            import importlib.util
            spec_module = importlib.util.spec_from_file_location(
                f"agents.{agent_name}.tools", local_tools_path
            )
            if spec_module and spec_module.loader:
                tools_module = importlib.util.module_from_spec(spec_module)
                spec_module.loader.exec_module(tools_module)
                if hasattr(tools_module, "LOCAL_TOOLS"):
                    all_tools.extend(tools_module.LOCAL_TOOLS)
                else:
                    for attr_name in dir(tools_module):
                        attr = getattr(tools_module, attr_name)
                        if isinstance(attr, BaseTool) and attr not in all_tools:
                            all_tools.append(attr)

        if extra_tools:
            all_tools.extend(extra_tools)

        # 4. 解析模型与参数配置
        model_spec = spec.get("model", {})
        agent_params = {
            "name": spec.get("name", agent_name),
            "system_prompt": full_system_prompt,
            "provider": model_spec.get("provider", "deepseek"),
            "model_name": model_spec.get("model_name"),
            "temperature": model_spec.get("temperature", 0.0),
            "tools": all_tools,
            "enable_memory": spec.get("enable_memory", True),
        }

        # 应用外部覆盖
        if override_config:
            agent_params.update(override_config)

        # 从环境创建基础配置，并在其上叠加模板参数
        config = AgentConfig.from_env(**agent_params)

        return build_agent(config)


# 便捷模块级加载函数
_default_loader = AgentTemplateLoader()


async def load_agent(
    agent_name: str,
    extra_tools: Optional[List[Any]] = None,
    override_config: Optional[Dict[str, Any]] = None,
) -> StandaloneAgent:
    """官方原生异步从 agents/ 目录加载构建 Agent"""
    return await _default_loader.load_agent(agent_name, extra_tools, override_config)
