"""
任务委派与编排工具 (Delegation Tool)
支持上级主控智能体（如 master / supervisor）向专业子智能体下发任务并获取审查交付成果。
"""

import uuid
from typing import Dict, Any
from langchain_core.tools import tool

# 内存单例缓存池，避免重复读磁盘解析与重复建立 MCP 连接
_agent_cache: Dict[str, Any] = {}


@tool
async def delegate_to_subagent(
    agent_type: str,
    task_description: str,
    context: str = "",
    expected_output_format: str = "",
) -> str:
    """
    通用子智能体任务委派工具。
    当主任务需要拆解、超出自身专业职能，或需要其他领域专家智能体协同（例如调用 'data_scraper' 抓取行情、调用其他专家等）时使用此工具。

    :param agent_type: 目标子智能体类型名称，必须是系统中已注册的 Agent（例如 'data_scraper'）
    :param task_description: 指派给子智能体的具体任务描述与执行指令
    :param context: 提供给子智能体的必要背景信息或上下文参数（例如标的代码、时间区间、数据保存要求等）
    :param expected_output_format: 期望子智能体交付的成果形式（例如 '获取最近5日K线数据，以标准JSON格式返回，并使用 write_file 落地保存到 workspace/data/'）
    :return: 子智能体执行后的最终输出报告或错误信息
    """
    from agents import load_agent, list_available_agents

    available = list_available_agents()
    if agent_type not in available:
        return f"❌ 委派失败: 智能体类型 '{agent_type}' 不存在，当前系统中可用的智能体清单为: {available}"

    # 1. 内存单例池：首次加载初始化 MCP 与模型，后续调用零冷启动
    if agent_type not in _agent_cache:
        _agent_cache[agent_type] = await load_agent(agent_type)

    subagent = _agent_cache[agent_type]

    # 2. 组装规范化委派 Prompt
    prompt_payload = (
        f"【上级主智能体委派任务】\n"
        f"任务目标: {task_description}\n"
        f"背景上下文: {context or '无额外上下文'}\n"
        f"交付要求: {expected_output_format or '请给出详细执行结果与产物说明'}"
    )

    # 3. 隔离会话 Thread ID：防止子任务的中间历史污染主会话
    subtask_id = f"subtask_{agent_type}_{uuid.uuid4().hex[:6]}"
    print(f"\n🚀 [Supervisor 委派触发] -> 正在唤醒子智能体 [{agent_type}] 执行任务: {task_description[:60]}...", flush=True)

    try:
        result = await subagent.arun(prompt_payload, thread_id=subtask_id)
        print(f"🎯 [Sub-Agent 交付] <- 子智能体 [{agent_type}] 成功完成任务，交付成果给主智能体进行审查。", flush=True)
        return (
            f"✅ [子智能体 {agent_type} 交付成果 (TaskID: {subtask_id})]:\n"
            f"{result}"
        )
    except Exception as e:
        print(f"❌ [Sub-Agent 异常] <- 子智能体 [{agent_type}] 报错: {e}", flush=True)
        return f"⚠️ [子智能体 {agent_type} 执行异常]: {str(e)}"
