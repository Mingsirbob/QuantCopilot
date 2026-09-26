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

from core import AgentConfig, build_agent, StandaloneAgent

# 确保向上查找并加载根目录与 backend 目录的 .env
_current_dir = Path(__file__).resolve().parent
load_dotenv(_current_dir.parent.parent / ".env")
load_dotenv(_current_dir.parent / ".env")
load_dotenv()

from mcp.types import CallToolResult, TextContent
from langchain_mcp_adapters.interceptors import ToolCallInterceptor, MCPToolCallRequest


class SafeMCPToolCallInterceptor(ToolCallInterceptor):
    """
    LangChain 官方标准 MCP 工具调用拦截器。
    用于接管第三方 MCP 服务端协议不严格（如休市时返回 null 与其声明的 schema 冲突）、网络抖动等异常，
    将其转化为友好的结构化说明反馈给大模型，避免因外部服务协议偏差导致 Agent 进程中断崩溃。
    """

    async def __call__(self, request: MCPToolCallRequest, handler):
        try:
            return await handler(request)
        except Exception as e:
            err_msg = str(e)
            if "Invalid structured content returned by tool" in err_msg:
                # 典型场景：同花顺等服务端在周末/非交易日返回了 null，但其 schema 未声明 null 类型
                desc = (
                    f"工具 '{request.name}' 执行完毕，但服务端返回的数据字段为 null 或未满足其声明的 Schema。"
                    f" 若当前查询的是周末/法定休市日，属于该日期区间无交易行情的正常现象。"
                )
            else:
                desc = f"工具 '{request.name}' 调用时发生外部服务端异常: {err_msg}"

            return CallToolResult(
                content=[TextContent(type="text", text=desc)],
                isError=False,
            )


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
    """Agent 工作区加载器，负责从用户工作区 (workspace/agents) 加载已配置的 Agent 资产"""

    def __init__(self, base_agents_dir: Optional[Union[str, Path]] = None):
        if base_agents_dir is not None:
            self.base_agents_dir = Path(base_agents_dir).resolve()
        else:
            # 1. 优先读取环境变量指定的路径
            env_ws = os.getenv("WORKSPACE_AGENTS_DIR") or os.getenv("WORKSPACE_DIR")
            if env_ws:
                p = Path(env_ws).resolve()
                self.base_agents_dir = p if p.name == "agents" else p / "agents"
            else:
                # 2. 默认定位项目根目录下的 workspace/agents
                project_root = Path(__file__).resolve().parent.parent.parent
                ws_dir = project_root / "workspace" / "agents"
                if ws_dir.exists():
                    self.base_agents_dir = ws_dir
                else:
                    self.base_agents_dir = Path("workspace/agents").resolve()

    def list_available_agents(self) -> List[str]:
        """列出当前工作区中所有已配置的 Agent 名称"""
        if not self.base_agents_dir.exists():
            return []
        agents = []
        for p in self.base_agents_dir.iterdir():
            if p.is_dir() and (p / "agent.yaml").exists():
                agents.append(p.name)
        return sorted(agents)

    def get_agent_path(self, agent_name: str) -> Path:
        """根据名称获取 Agent 目录路径"""
        agent_dir = self.base_agents_dir / agent_name
        if not agent_dir.exists() or not agent_dir.is_dir():
            available = self.list_available_agents()
            raise FileNotFoundError(
                f"在工作区 '{self.base_agents_dir}' 中未找到 Agent: '{agent_name}'。"
                f" 当前可用 Agent: {available if available else '无(空工作区)'}"
            )
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

        # 0. 若开启长期记忆，自动预载用户画像偏好并注入顶部
        if spec.get("enable_long_term_memory"):
            from core.memory import LongTermMemoryManager
            mem_mgr = LongTermMemoryManager.get_instance()
            user_profile = mem_mgr.get_user_profile()
            prompt_parts.append(
                f"========================================\n"
                f"【核心长期记忆：用户投资画像与全局偏好】\n"
                f"{user_profile}\n"
                f"========================================"
            )

        # 1. 主人设 prompt.md
        prompt_path = agent_dir / "prompt.md"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_parts.append(f.read().strip())

        # 2. 附加技能包（支持目录即技能、公共/私有仓库寻址、二次披露 references）
        declared_skills = spec.get("skills", [])
        workspace_root = agent_dir.parent.parent  # workspace 根目录
        shared_skills_repo = (workspace_root / "skills").resolve()
        agent_private_skills_dir = (agent_dir / "skills").resolve()

        for skill_ref in declared_skills:
            if not isinstance(skill_ref, str) or not skill_ref.strip():
                continue
            skill_ref = skill_ref.strip()

            target_skill_dir: Optional[Path] = None
            direct_file: Optional[Path] = None

            # 寻址规则 1：以 "@skills/" 或 "@shared/" 开头 -> 显式指定公共技能仓库
            if skill_ref.startswith("@skills/") or skill_ref.startswith("@shared/"):
                sub_path = skill_ref.split("/", 1)[1]
                cand = (shared_skills_repo / sub_path).resolve()
                if cand.is_dir():
                    target_skill_dir = cand
                elif cand.is_file():
                    direct_file = cand

            # 寻址规则 2：以 "./" 开头 -> 显式指定当前 Agent 专属私有目录
            elif skill_ref.startswith("./"):
                cand = (agent_dir / skill_ref).resolve()
                if cand.is_dir():
                    target_skill_dir = cand
                elif cand.is_file():
                    direct_file = cand

            # 寻址规则 3：简写名称（例如 "trend_analysis" 或 "trend_analysis_sop.md"）
            # 优先级：公共技能仓库优先，其次查找 Agent 私有技能目录
            else:
                cand_shared_dir = shared_skills_repo / skill_ref
                cand_shared_file = shared_skills_repo / f"{skill_ref}.md"
                cand_local_dir = agent_private_skills_dir / skill_ref
                cand_local_file = agent_private_skills_dir / skill_ref

                if cand_shared_dir.is_dir():
                    target_skill_dir = cand_shared_dir.resolve()
                elif cand_shared_file.is_file():
                    direct_file = cand_shared_file.resolve()
                elif cand_local_dir.is_dir():
                    target_skill_dir = cand_local_dir.resolve()
                elif cand_local_file.is_file():
                    direct_file = cand_local_file.resolve()

            # 解析执行：若定位到标准 Skill 目录（包含 SKILL.md / skill.md）
            if target_skill_dir and target_skill_dir.exists():
                skill_entry = target_skill_dir / "SKILL.md"
                if not skill_entry.exists():
                    skill_entry = target_skill_dir / "skill.md"

                skill_text_blocks = []
                skill_name = target_skill_dir.name

                if skill_entry.exists():
                    with open(skill_entry, "r", encoding="utf-8") as f:
                        entry_content = f.read().strip()
                        skill_text_blocks.append(entry_content)

                # 二次披露 (Progressive Disclosure)：自动加载 references/ 深度参考手册
                references_dir = target_skill_dir / "references"
                if references_dir.exists() and references_dir.is_dir():
                    ref_files = sorted(references_dir.glob("*.md"))
                    for ref_f in ref_files:
                        with open(ref_f, "r", encoding="utf-8") as rf:
                            ref_content = rf.read().strip()
                            skill_text_blocks.append(
                                f"\n\n--- [技能二次披露/深度参考: {ref_f.name}] ---\n{ref_content}"
                            )

                if skill_text_blocks:
                    joined_skill = "\n\n".join(skill_text_blocks)
                    prompt_parts.append(
                        f"\n\n========================================\n"
                        f"【装载专业技能包: {skill_name}】\n"
                        f"{joined_skill}\n"
                        f"========================================"
                    )

            # 兼容执行：若为单个老版 .md 技能文件
            elif direct_file and direct_file.exists():
                with open(direct_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    prompt_parts.append(
                        f"\n\n--- [技能参考: {direct_file.name}] ---\n{content}"
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

        max_retries = 3
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                client = MultiServerMCPClient(
                    connections=connections,
                    tool_interceptors=[SafeMCPToolCallInterceptor()],
                )
                tools = await client.get_tools()
                return list(tools)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    print(f"⚠️ 连接 MCP 服务失败 (第 {attempt} 次尝试): {e}，2秒后重试...")
                    await asyncio.sleep(2)
                else:
                    print(f"❌ 连接 MCP 服务重试 {max_retries} 次后失败: {e}")
                    raise last_error
        return []

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
        local_tool_map = {}
        if local_tools_path.exists():
            import importlib.util
            spec_module = importlib.util.spec_from_file_location(
                f"agents.{agent_name}.tools", local_tools_path
            )
            if spec_module and spec_module.loader:
                tools_module = importlib.util.module_from_spec(spec_module)
                spec_module.loader.exec_module(tools_module)
                if hasattr(tools_module, "LOCAL_TOOLS"):
                    for t in tools_module.LOCAL_TOOLS:
                        if isinstance(t, BaseTool):
                            local_tool_map[getattr(t, "name", str(t))] = t
                for attr_name in dir(tools_module):
                    attr = getattr(tools_module, attr_name)
                    if isinstance(attr, BaseTool):
                        local_tool_map[getattr(attr, "name", attr_name)] = attr

        # 检查核心通用内置工具映射 (core.tools)
        from core.tools import DEFAULT_TOOLS
        builtin_tool_map = {getattr(t, "name", str(t)): t for t in DEFAULT_TOOLS}

        # 如果 agent.yaml 显式配置了 tools 列表，按配置选配；否则默认加入所有本地发现的工具
        declared_tool_names = spec.get("tools")
        if declared_tool_names is not None and isinstance(declared_tool_names, list):
            for t_name in declared_tool_names:
                if t_name in local_tool_map and local_tool_map[t_name] not in all_tools:
                    all_tools.append(local_tool_map[t_name])
                elif t_name in builtin_tool_map and builtin_tool_map[t_name] not in all_tools:
                    all_tools.append(builtin_tool_map[t_name])
        else:
            # 兼容默认行为：注入该 Agent 的所有 local tools
            for t in local_tool_map.values():
                if t not in all_tools:
                    all_tools.append(t)

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
            "enable_code_sandbox": spec.get("enable_code_sandbox", False),
            "sandbox_dir": spec.get("sandbox_dir"),
        }

        # 解析上下文压缩参数（支持 context_compression 字典或顶层字段）
        comp_spec = spec.get("context_compression", {})
        if "enable_context_compression" in spec:
            agent_params["enable_context_compression"] = spec["enable_context_compression"]
        elif "enable" in comp_spec:
            agent_params["enable_context_compression"] = comp_spec["enable"]

        if "token_budget" in comp_spec:
            agent_params["context_token_budget"] = comp_spec["token_budget"]
        if "max_tool_chars" in comp_spec:
            agent_params["context_tool_max_len"] = comp_spec["max_tool_chars"]
        if "keep_recent_messages" in comp_spec:
            agent_params["context_window_keep_messages"] = comp_spec["keep_recent_messages"]

        # 解析待办任务清单开关
        if "enable_todo_list" in spec:
            agent_params["enable_todo_list"] = spec["enable_todo_list"]

        # 解析长期记忆开关
        if "enable_long_term_memory" in spec:
            agent_params["enable_long_term_memory"] = spec["enable_long_term_memory"]

        # 解析安全审批围栏开关与敏感工具
        if "enable_tool_approval" in spec:
            agent_params["enable_tool_approval"] = spec["enable_tool_approval"]
        if "sensitive_tools" in spec:
            agent_params["sensitive_tools"] = spec["sensitive_tools"]
        if "approval_whitelist" in spec:
            agent_params["approval_whitelist"] = spec["approval_whitelist"]

        # 应用外部覆盖
        if override_config:
            agent_params.update(override_config)

        # 从环境创建基础配置，并在其上叠加模板参数
        config = AgentConfig.from_env(**agent_params)

        # 5. 如果启用了记忆，异步获取并初始化持久化 SessionManager
        session_manager = None
        checkpointer = None
        if config.enable_memory:
            from core.memory import SessionManager
            session_manager = await SessionManager.get_instance(config.session_db_path)
            checkpointer = session_manager.get_checkpointer()

        return build_agent(config, session_manager=session_manager, checkpointer=checkpointer)


# 便捷模块级加载函数
_default_loader = AgentTemplateLoader()


async def load_agent(
    agent_name: str,
    extra_tools: Optional[List[Any]] = None,
    override_config: Optional[Dict[str, Any]] = None,
) -> StandaloneAgent:
    """官方原生异步从 agents/ 目录加载构建 Agent"""
    return await _default_loader.load_agent(agent_name, extra_tools, override_config)
