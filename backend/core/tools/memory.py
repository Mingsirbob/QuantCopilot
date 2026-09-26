"""
长期记忆操作工具包 (Long-Term Memory Tools)
为 Agent 提供直接查询、更新用户偏好与标的历史档案的显式工具能力。
"""

import json
from langchain_core.tools import tool
from core.memory.long_term import LongTermMemoryManager


@tool
def recall_entity_memory(query: str) -> str:
    """
    根据股票代码（如 '300750'）或股票/板块名称（如 '宁德时代'）检索该标的的长期历史分析档案。
    如果找到了历史档案，将返回上次分析的趋势定性、关键支撑压力位及核心归因；如果未找到，则提示暂无建档。
    在启动对某个标的的分析或响应用户连续提问前，建议先调用本工具查阅历史记忆。
    """
    manager = LongTermMemoryManager.get_instance()
    result = manager.recall_entity(query)
    if not result:
        return f"💡 长期记忆库中暂无关于标的 '{query}' 的历史档案记录（属于首次分析或尚未归档）。"

    levels_str = json.dumps(result.get("key_levels", {}), ensure_ascii=False)
    return (
        f"📚 【标的长期记忆档案召回成功】\n"
        f"• 标的标识: {result['entity_id']} ({result['entity_name']})\n"
        f"• 上期走势判定: {result['last_trend']}\n"
        f"• 关键技术点位: {levels_str}\n"
        f"• 上期归因摘要: {result['latest_summary']}\n"
        f"• 建档/更新时间: {result['updated_at']}\n"
        f"请基于上述历史基准，结合本次最新获取的数据进行对比与增量研判。"
    )


@tool
def save_entity_memory(
    entity_id: str,
    entity_name: str,
    last_trend: str,
    key_levels_json: str,
    latest_summary: str,
) -> str:
    """
    沉淀或更新某个标的/实体的长期研报档案。
    在完成对某个标的的深度研判并向用户输出报告后，请调用本工具将核心结论归档，以便未来会话跟踪。

    :param entity_id: 统一标的标识（例如 'stock:300750' 或 'stock:600519'）
    :param entity_name: 标的名称（例如 '宁德时代' 或 '贵州茅台'）
    :param last_trend: 研判结论（例如 '向下，冲高回落转弱' 或 '向上，放量突破'）
    :param key_levels_json: 关键支撑压力位（JSON 字符串，例如 '{"support": 295.5, "resistance": 305.0}'）
    :param latest_summary: 核心归因与风险提示摘要（150字以内精炼概括）
    """
    manager = LongTermMemoryManager.get_instance()
    try:
        parsed_levels = json.loads(key_levels_json) if key_levels_json else {}
    except Exception:
        parsed_levels = {"raw": key_levels_json}

    res = manager.save_entity_archive(
        entity_id=entity_id,
        entity_name=entity_name,
        latest_summary=latest_summary,
        last_trend=last_trend,
        key_levels=parsed_levels,
    )
    return f"✅ 标的 '{entity_name}' ({entity_id}) 的长期研报档案已成功沉淀归档 (更新时间: {res['updated_at']})。"


@tool
def append_user_preference(preference_note: str) -> str:
    """
    当用户在交互中明确表达了持久性的投资偏好、习惯或要求时，调用本工具将其沉淀到用户长期画像中。
    例如：“我以后不看创业板股票”、“研报默认只要 300 字精简版”、“默认使用 MA5 和 MA20”。

    :param preference_note: 用户表达的偏好要点（简洁明了）
    """
    manager = LongTermMemoryManager.get_instance()
    manager.append_user_preference(preference_note)
    return f"✅ 已成功将用户新偏好记录至全局长期画像: '{preference_note}'"


MEMORY_TOOLS = [recall_entity_memory, save_entity_memory, append_user_preference]
