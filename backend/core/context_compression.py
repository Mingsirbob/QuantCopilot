"""
智能上下文压缩模块 (Context Compression Module)

实现 5 大核心压缩策略：
1. SlidingWindowStrategy（滑动窗口）：只保留最近 N 组对话，过早的历史直接剔除（保留系统提示词）。
2. TruncationStrategy（硬截断）：按 Token 数或消息数对超标历史进行底线截断。
3. ToolResultCompactionStrategy（工具结果精简）：把历史中冗长的工具返回（如巨型 JSON/长文本）折叠成简短摘要。
4. SummarizationStrategy（大模型摘要）：用大模型/轻量模型将旧消息浓缩成一段精炼总结，既省 Token 又不失忆。
5. TokenBudgetComposedStrategy（预算组合拳）：设定目标 Token 预算，组合上述多种策略按优先级依次压缩，直到达标。

并提供 LangChain 原生 AgentMiddleware 扩展：
ContextCompressionMiddleware，无缝集成到 create_agent 与 LangGraph 智能体循环中。
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Union
import tiktoken
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)

logger = logging.getLogger("core.context_compression")

# 初始化 Token 计数器
try:
    _enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None


def count_tokens(messages: Sequence[BaseMessage]) -> int:
    """
    通用、鲁棒的 Token 计算器。
    优先采用 tiktoken (cl100k_base)，若未加载成功则按字符数比例安全回退。
    """
    if not messages:
        return 0

    total = 0
    for m in messages:
        content = getattr(m, "content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # 处理多模态或 content block 列表格式
            text = " ".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        else:
            text = str(content)

        if _enc is not None:
            try:
                total += len(_enc.encode(text)) + 4  # +4 为每条消息的角色元数据预留
            except Exception:
                total += len(text) // 3 + 4
        else:
            total += len(text) // 3 + 4

    return total


# =====================================================================
# 策略一：ToolResultCompactionStrategy（工具结果精简）
# =====================================================================
def compact_tool_messages(
    messages: Sequence[BaseMessage],
    max_tool_chars: int = 300,
) -> List[BaseMessage]:
    """
    将历史中过于冗长的 ToolMessage 结果进行精简折叠，
    同时严格保留 tool_call_id、name 等元信息，防止工具调用链断裂。
    """
    compacted: List[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content_str = str(msg.content)
            if len(content_str) > max_tool_chars:
                truncated_text = (
                    f"{content_str[:max_tool_chars]}\n"
                    f"... [工具结果已自动折叠: 原始共 {len(content_str)} 字符，保留前 {max_tool_chars} 字符]"
                )
                new_msg = ToolMessage(
                    content=truncated_text,
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None),
                    status=getattr(msg, "status", "success"),
                    artifact=getattr(msg, "artifact", None),
                    additional_kwargs=dict(getattr(msg, "additional_kwargs", {})),
                )
                compacted.append(new_msg)
            else:
                compacted.append(msg)
        else:
            compacted.append(msg)
    return compacted


# =====================================================================
# 策略二：SummarizationStrategy（大模型摘要）
# =====================================================================
SUMMARY_PROMPT_TEMPLATE = """请作为专业的对话记忆提炼助手，将以下较早的历史对话记录提炼成一段高度浓缩的中文核心摘要：

<历史对话>
{history_text}
</历史对话>

要求：
1. 提取用户核心意图、讨论的关键问题与关键决策。
2. 明确提及执行过哪些工具或查询操作及其核心结论（如有生成文件/指标，请记录名称）。
3. 语言简练精要，严禁包含多余客套话，字数控制在 200 字以内。
"""


def _format_messages_for_summary(messages: Sequence[BaseMessage]) -> str:
    lines = []
    for m in messages:
        role = "System"
        if isinstance(m, HumanMessage):
            role = "User"
        elif isinstance(m, AIMessage):
            role = "Assistant"
        elif isinstance(m, ToolMessage):
            role = f"Tool({getattr(m, 'name', 'tool')})"
        content = str(getattr(m, "content", ""))
        # 摘要输入时限制单条超长消息
        if len(content) > 400:
            content = content[:400] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _heuristic_summary(messages: Sequence[BaseMessage]) -> str:
    """未配置大模型或模型调用降级时的启发式要点摘要"""
    points = []
    for m in messages:
        if isinstance(m, HumanMessage):
            txt = str(m.content).strip()
            if txt:
                points.append(f"- 用户提问: {txt[:80]}")
        elif isinstance(m, ToolMessage):
            points.append(f"- 工具执行: {getattr(m, 'name', 'tool')}")
        elif isinstance(m, AIMessage) and m.content:
            txt = str(m.content).strip()
            if txt:
                points.append(f"- 助手回复: {txt[:80]}")
    return "早期对话主要互动要点：\n" + "\n".join(points[:6])


def summarize_messages_sync(
    messages: Sequence[BaseMessage],
    keep_recent_messages: int = 6,
    summary_model: Optional[BaseChatModel] = None,
) -> List[BaseMessage]:
    """同步大模型摘要策略"""
    if len(messages) <= keep_recent_messages + 1:
        return list(messages)

    early_messages = messages[:-keep_recent_messages]
    recent_messages = list(messages[-keep_recent_messages:])

    # 确保 recent_messages 起始于 HumanMessage，防止孤立的 ToolMessage/AIMessage
    while recent_messages and not isinstance(recent_messages[0], HumanMessage):
        early_messages = list(early_messages) + [recent_messages.pop(0)]

    if not early_messages:
        return recent_messages

    summary_text = ""
    if summary_model is not None:
        try:
            formatted = _format_messages_for_summary(early_messages)
            prompt = SUMMARY_PROMPT_TEMPLATE.format(history_text=formatted)
            resp = summary_model.invoke(prompt)
            summary_text = resp.content if isinstance(resp.content, str) else str(resp.content)
        except Exception as e:
            logger.warning(f"大模型同步摘要执行失败，降级为启发式摘要: {e}")
            summary_text = _heuristic_summary(early_messages)
    else:
        summary_text = _heuristic_summary(early_messages)

    summary_msg = SystemMessage(
        content=f"[早期历史对话记忆摘要]:\n{summary_text.strip()}"
    )
    return [summary_msg] + recent_messages


async def summarize_messages_async(
    messages: Sequence[BaseMessage],
    keep_recent_messages: int = 6,
    summary_model: Optional[BaseChatModel] = None,
) -> List[BaseMessage]:
    """异步大模型摘要策略"""
    if len(messages) <= keep_recent_messages + 1:
        return list(messages)

    early_messages = messages[:-keep_recent_messages]
    recent_messages = list(messages[-keep_recent_messages:])

    while recent_messages and not isinstance(recent_messages[0], HumanMessage):
        early_messages = list(early_messages) + [recent_messages.pop(0)]

    if not early_messages:
        return recent_messages

    summary_text = ""
    if summary_model is not None:
        try:
            formatted = _format_messages_for_summary(early_messages)
            prompt = SUMMARY_PROMPT_TEMPLATE.format(history_text=formatted)
            resp = await summary_model.ainvoke(prompt)
            summary_text = resp.content if isinstance(resp.content, str) else str(resp.content)
        except Exception as e:
            logger.warning(f"大模型异步摘要执行失败，降级为启发式摘要: {e}")
            summary_text = _heuristic_summary(early_messages)
    else:
        summary_text = _heuristic_summary(early_messages)

    summary_msg = SystemMessage(
        content=f"[早期历史对话记忆摘要]:\n{summary_text.strip()}"
    )
    return [summary_msg] + recent_messages


# =====================================================================
# 策略三 & 策略四：SlidingWindowStrategy & TruncationStrategy
# =====================================================================
def trim_history(
    messages: Sequence[BaseMessage],
    max_tokens: int,
    start_on: str = "human",
    include_system: bool = True,
) -> List[BaseMessage]:
    """
    基于 LangChain 原生 trim_messages 实现滑动窗口与硬截断。
    - strategy='last': 保留最新交互
    - start_on='human': 确保截断后的首条消息为 HumanMessage，防止孤立工具消息
    """
    if not messages:
        return []

    try:
        trimmed = trim_messages(
            list(messages),
            max_tokens=max_tokens,
            token_counter=count_tokens,
            strategy="last",
            start_on=start_on,
            include_system=include_system,
            allow_partial=False,
        )
        return trimmed
    except Exception as e:
        logger.warning(f"trim_messages 执行异常，采用安全切片回退: {e}")
        # 回退：直接截取最近 4 条
        return list(messages[-4:])


# =====================================================================
# 策略五：TokenBudgetComposedStrategy（预算组合拳）
# =====================================================================
class TokenBudgetComposedCompressor:
    """
    预算组合拳压缩器：
    设定目标 Token 预算，按优先级阶梯式应用压缩策略：
    - 阶段 0: 预算达标检查
    - 阶段 1 (ToolResultCompaction): 压缩历史冗长工具返回
    - 阶段 2 (Summarization): 触发大模型/结构化摘要并保留最近窗口
    - 阶段 3 (Sliding Window & Hard Truncation): 原生 trim_messages 兜底硬截断
    """

    def __init__(
        self,
        token_budget: int = 4000,
        max_tool_chars: int = 300,
        keep_recent_messages: int = 6,
        summary_model: Optional[BaseChatModel] = None,
    ):
        self.token_budget = token_budget
        self.max_tool_chars = max_tool_chars
        self.keep_recent_messages = keep_recent_messages
        self.summary_model = summary_model

    def compress(self, messages: Sequence[BaseMessage]) -> List[BaseMessage]:
        """同步执行多级压缩流程"""
        if not messages:
            return []

        msgs = list(messages)
        # 阶段 0: 达标检查
        if count_tokens(msgs) <= self.token_budget:
            return msgs

        # 阶段 1: 工具结果精简
        msgs = compact_tool_messages(msgs, max_tool_chars=self.max_tool_chars)
        if count_tokens(msgs) <= self.token_budget:
            return msgs

        # 阶段 2: 大模型/结构化摘要
        if len(msgs) > self.keep_recent_messages:
            msgs = summarize_messages_sync(
                msgs,
                keep_recent_messages=self.keep_recent_messages,
                summary_model=self.summary_model,
            )
            if count_tokens(msgs) <= self.token_budget:
                return msgs

        # 阶段 3: 兜底硬截断 (保留最近并在 HumanMessage 对齐)
        msgs = trim_history(
            msgs,
            max_tokens=self.token_budget,
            start_on="human",
            include_system=True,
        )
        return msgs

    async def acompress(self, messages: Sequence[BaseMessage]) -> List[BaseMessage]:
        """异步执行多级压缩流程"""
        if not messages:
            return []

        msgs = list(messages)
        # 阶段 0: 达标检查
        if count_tokens(msgs) <= self.token_budget:
            return msgs

        # 阶段 1: 工具结果精简
        msgs = compact_tool_messages(msgs, max_tool_chars=self.max_tool_chars)
        if count_tokens(msgs) <= self.token_budget:
            return msgs

        # 阶段 2: 异步大模型/结构化摘要
        if len(msgs) > self.keep_recent_messages:
            msgs = await summarize_messages_async(
                msgs,
                keep_recent_messages=self.keep_recent_messages,
                summary_model=self.summary_model,
            )
            if count_tokens(msgs) <= self.token_budget:
                return msgs

        # 阶段 3: 兜底硬截断
        msgs = trim_history(
            msgs,
            max_tokens=self.token_budget,
            start_on="human",
            include_system=True,
        )
        return msgs


# =====================================================================
# LangChain 原生 AgentMiddleware 扩展
# =====================================================================
class ContextCompressionMiddleware(AgentMiddleware):
    """
    基于 LangChain AgentMiddleware 的无缝上下文压缩中间件。
    在智能体决策循环的每次模型调用前，拦截 request.messages，
    透明应用 5 大压缩机制，在维持模型语义与工具调用的同时极大削减 Token 消耗。
    """

    def __init__(self, compressor: TokenBudgetComposedCompressor):
        super().__init__()
        self.compressor = compressor

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
        """同步拦截并执行上下文压缩"""
        original_msgs = request.messages
        compressed_msgs = self.compressor.compress(original_msgs)
        new_request = request.override(messages=compressed_msgs)
        return handler(new_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """异步拦截并执行上下文压缩"""
        original_msgs = request.messages
        compressed_msgs = await self.compressor.acompress(original_msgs)
        new_request = request.override(messages=compressed_msgs)
        return await handler(new_request)
