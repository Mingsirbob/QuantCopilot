"""
MultiAgent 交互式终端对话器 (CLI Chat)
提供类似 Web 端/ChatGPT 的完整沉浸式交互体验：
1. 多轮持久对话与会话记忆 (基于 sessions.db)
2. 实时流式响应与工具调用动画 (ReAct 状态追踪)
3. 待办任务清单实时看板 (TodoListMiddleware 联动)
4. 安全审批围栏人机交互 (敏感工具中断拦截、批准、拒绝、不再询问)
5. 智能会话标题展示与多会话切换 (/new, /sessions, /switch)
"""

import os
import sys
import asyncio
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# 确保 backend 目录在 sys.path 中
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

load_dotenv(backend_dir.parent / ".env")
load_dotenv(backend_dir / ".env")
load_dotenv()

# 控制台 UTF-8 支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agents import load_agent, list_available_agents
from core.builder import StandaloneAgent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _print_banner(agent_name: str, thread_id: str):
    print("\n" + "=" * 76)
    print(f"🤖 MultiAgent 智能体对话控制台 (当前 Agent: \033[1;36m{agent_name}\033[0m)")
    print(f"🧵 当前会话 ID: \033[1;33m{thread_id}\033[0m")
    print("💡 快捷指令: /new (新建会话) | /sessions (会话列表) | /switch (切换会话)")
    print("            /todos (任务进度) | /history (查看历史) | /exit (退出)")
    print("=" * 76 + "\n")


def _print_todos(todos: List[Dict[str, Any]]):
    """美化渲染待办清单看板"""
    if not todos:
        return
    print("\n📋 \033[1;35m【待办任务规划看板】\033[0m")
    for idx, item in enumerate(todos, 1):
        content = item.get("content", "")
        status = item.get("status", "pending")
        if status == "completed":
            print(f"  \033[32m✔ [{idx}] {content} (已完成)\033[0m")
        elif status == "in_progress":
            print(f"  \033[33m▶ [{idx}] {content} (进行中...)\033[0m")
        else:
            print(f"  \033[90m⏳ [{idx}] {content} (待处理)\033[0m")
    print()


async def _handle_security_approval(agent: StandaloneAgent, thread_id: str) -> bool:
    """处理安全审批围栏拦截交互"""
    pending = await agent.aget_pending_approvals(thread_id)
    if not pending:
        return False

    print("\n" + "!" * 76)
    print("⚠️  \033[1;31m【安全审批围栏拦截】智能体请求执行敏感工具，需要您的人类审批！\033[0m")
    for idx, p in enumerate(pending, 1):
        print(f"  • 工具名称: \033[1;33m{p.get('tool_name')}\033[0m")
        print(f"  • 传参详情: {p.get('args')}")
        print(f"  • 安全描述: {p.get('description')}")
    print("!" * 76)

    while True:
        choice = input(
            "\n👉 请选择审批操作 [\033[32my:批准\033[0m / \033[31mn:拒绝\033[0m / \033[36ma:批准且记住选择不再询问\033[0m]: "
        ).strip().lower()

        if choice in ("y", "yes"):
            print("⏳ 正在批准并恢复执行...")
            await agent.aapprove(thread_id=thread_id, always_allow=False)
            return True
        elif choice in ("a", "always"):
            print("⏳ 正在批准并将该工具加入免审批白名单（不再询问）...")
            await agent.aapprove(thread_id=thread_id, always_allow=True)
            return True
        elif choice in ("n", "no"):
            reason = input("请输入拒绝原因 (回车使用默认原因): ").strip()
            if not reason:
                reason = "操作被用户手动拒绝，取消执行该敏感操作。"
            print(f"⏳ 正在拒绝操作并将原因反馈给智能体...")
            await agent.areject(thread_id=thread_id, reason=reason)
            return True
        else:
            print("无效选项，请输入 y、n 或 a。")


async def run_chat_loop(agent: StandaloneAgent, initial_thread_id: Optional[str] = None):
    """核心对话事件循环"""
    thread_id = initial_thread_id or f"session_{int(time.time())}"
    _print_banner(agent.config.name, thread_id)

    while True:
        try:
            user_input = input(f"\033[1;32m👤 您 [{thread_id}] > \033[0m").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 对话已退出，期待下次交流！")
            break

        if not user_input:
            continue

        # 快捷指令处理
        if user_input.startswith("/"):
            cmd = user_input.lower().split()
            c = cmd[0]

            if c in ("/exit", "/quit"):
                print("👋 对话已退出，再见！")
                break
            elif c == "/new":
                thread_id = f"session_{int(time.time())}"
                print(f"✨ 已创建并切换至新会话: \033[1;33m{thread_id}\033[0m")
                continue
            elif c == "/sessions":
                sessions = agent.list_sessions()
                print("\n📂 \033[1;36m【历史会话列表】\033[0m")
                if not sessions:
                    print("  (暂无历史会话记录)")
                for s in sessions:
                    sid = s.get("session_id")
                    title = s.get("title") or "未命名会话"
                    updated = s.get("updated_at", "")
                    cur_mark = " \033[1;32m(当前)\033[0m" if sid == thread_id else ""
                    print(f"  • ID: \033[33m{sid}\033[0m | 标题: \033[1m{title}\033[0m | 更新: {updated}{cur_mark}")
                print()
                continue
            elif c == "/switch":
                if len(cmd) > 1:
                    thread_id = cmd[1]
                    print(f"🔄 已切换至会话: \033[1;33m{thread_id}\033[0m")
                    title = agent.get_session_title(thread_id)
                    if title:
                        print(f"📌 会话标题: 【\033[1;36m{title}\033[0m】")
                else:
                    print("⚠️ 请提供会话 ID，例如: /switch session_123456")
                continue
            elif c == "/todos":
                todos = await agent.aget_todos(thread_id)
                if todos:
                    _print_todos(todos)
                else:
                    print("ℹ️ 当前会话暂无活跃的待办规划任务。\n")
                continue
            elif c == "/history":
                history = await agent.aget_history(thread_id)
                print(f"\n📜 \033[1;36m【会话历史记录 (共 {len(history)} 条)】\033[0m")
                for m in history:
                    r = type(m).__name__.replace("Message", "")
                    txt = str(getattr(m, "content", ""))[:120]
                    print(f"  [{r}]: {txt}")
                print()
                continue
            elif c in ("/agent", "/switch_agent"):
                available = list_available_agents()
                if len(cmd) > 1 and cmd[1] in available:
                    new_agent_name = cmd[1]
                    print(f"🔄 正在切换至智能体: \033[1;36m{new_agent_name}\033[0m ...")
                    agent = await load_agent(new_agent_name)
                    _print_banner(agent.config.name, thread_id)
                else:
                    print(f"💡 可选智能体列表: {available}，用法: /agent <名称>，例如: /agent data_scraper\n")
                continue
            elif c in ("/help", "/?"):
                print("💡 支持指令:")
                print("  /new              - 开启全新会话")
                print("  /sessions         - 列出所有历史会话及大模型生成的标题")
                print("  /switch <id>      - 切换到指定历史会话")
                print("  /agent <name>     - 切换智能体 (例如: /agent data_scraper 或 /agent data_analyst)")
                print("  /todos            - 查看当前长任务的待办清单进度")
                print("  /history          - 查看当前会话历史消息")
                print("  /exit 或 /quit    - 退出对话\n")
                continue
            else:
                print(f"❓ 未知指令 '{c}'，输入 /help 查看支持的命令。\n")
                continue

        # 执行 Agent 调用推进
        print("\n\033[1;34m🤖 智能体正在思考...\033[0m", flush=True)

        try:
            # 1. 确保标题生成
            if agent.session_manager:
                await agent.session_manager.ensure_session_title(
                    session_id=thread_id,
                    agent_name=agent.config.name,
                    first_user_message=user_input,
                    llm=agent.model,
                )

            # 2. 状态驱动流式推进
            namespaced_id = agent._get_namespaced_thread_id(thread_id)
            call_config = {"configurable": {"thread_id": namespaced_id}}
            payload = {"messages": [HumanMessage(content=user_input)]}

            async for chunk in agent.graph.astream(payload, config=call_config, stream_mode="updates"):
                if "model" in chunk:
                    msgs = chunk["model"].get("messages", [])
                    for m in msgs:
                        # 检查工具调用
                        if getattr(m, "tool_calls", None):
                            for tc in m.tool_calls:
                                t_name = tc.get("name")
                                t_args = tc.get("args")
                                if t_name == "write_todos":
                                    todos_list = t_args.get("todos", [])
                                    _print_todos(todos_list)
                                else:
                                    arg_preview = str(t_args)
                                    if len(arg_preview) > 100:
                                        arg_preview = arg_preview[:100] + "..."
                                    print(f"  \033[33m⚡ 调用工具: [{t_name}]\033[0m 参数: {arg_preview}", flush=True)
                        elif getattr(m, "content", None):
                            print(f"\n\033[1;36m🤖 {agent.config.name} >\033[0m")
                            print(f"{m.content}\n", flush=True)

                elif "tools" in chunk:
                    msgs = chunk["tools"].get("messages", [])
                    for m in msgs:
                        t_name = getattr(m, "name", "tool")
                        c = str(getattr(m, "content", ""))
                        if len(c) > 100:
                            c = c[:100] + "..."
                        print(f"  \033[32m✔ 工具 [{t_name}] 返回:\033[0m {c}", flush=True)

            # 3. 检查是否触发安全审批围栏拦截
            while await agent.ais_interrupted(thread_id=thread_id):
                approved = await _handle_security_approval(agent, thread_id)
                if not approved:
                    break
                # 恢复后继续提取更新并打印
                state = await agent.graph.aget_state(call_config)
                if state and state.values and state.values.get("messages"):
                    last_msg = state.values["messages"][-1]
                    if isinstance(last_msg, AIMessage) and last_msg.content:
                        print(f"\n\033[1;36m🤖 {agent.config.name} >\033[0m")
                        print(f"{last_msg.content}\n", flush=True)

            # 4. 轮次收尾：展示待办进度与自动命名结果
            active_todos = await agent.aget_todos(thread_id)
            if active_todos:
                _print_todos(active_todos)

            title = agent.get_session_title(thread_id)
            if title:
                print(f"\033[90m📌 当前会话已自动命名: 【{title}】\033[0m\n")

        except Exception as e:
            print(f"\n\033[1;31m❌ 运行时发生异常: {e}\033[0m\n")


async def main():
    available = list_available_agents()
    print("=" * 60)
    print("🚀 正在启动 MultiAgent 对话终端...")
    print(f"📦 可用智能体清单: {available}")

    # 默认选择 data_analyst 智能体（或由命令行参数传入）
    selected_agent = "data_analyst"
    if len(sys.argv) > 1 and sys.argv[1] in available:
        selected_agent = sys.argv[1]
    elif "data_analyst" not in available and available:
        selected_agent = available[0]

    print(f"🎯 正在加载目标智能体: \033[1;36m{selected_agent}\033[0m ...")
    agent = await load_agent(selected_agent)
    print(f"✅ 智能体加载就绪! (已装载沙箱、待办规划、安全审批与5级压缩中间件)")

    await run_chat_loop(agent)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
    finally:
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)
