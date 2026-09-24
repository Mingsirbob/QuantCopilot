"""
会话持久化与管理模块 (集中存储于 workspace/sessions.db)
原生异步架构：
1. 采用 aiosqlite + AsyncSqliteSaver，完美适配 LangGraph ainvoke / arun 原生异步链路
2. 集中维护 sessions_meta 业务元数据表 (会话标题、创建时间、最后更新时间)
3. 参考 OpenAI 网页端机制：用户首次输入自动调用大模型提炼压缩为 4~12 字精炼中文标题
"""

import os
import aiosqlite
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class SessionManager:
    """
    全局会话持久化与标题管理器。
    默认集中管理 workspace/sessions.db 文件。
    """

    _instance: Optional["SessionManager"] = None

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            env_ws = os.getenv("WORKSPACE_DIR")
            if env_ws:
                root_ws = Path(env_ws).resolve()
            else:
                project_root = Path(__file__).resolve().parent.parent.parent
                root_ws = project_root / "workspace"

            runtime_sessions_dir = root_ws / "runtime" / "sessions"
            runtime_sessions_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = (runtime_sessions_dir / "sessions.db").resolve()

            # 平滑兼容：若旧位置 workspace/sessions.db 存在而新位置尚未建立，自动安全迁移
            old_db_path = (root_ws / "sessions.db").resolve()
            if old_db_path.exists() and not self.db_path.exists():
                import shutil
                shutil.move(str(old_db_path), str(self.db_path))
                # 同时迁移关联的 wal/shm 临时文件
                for suffix in ["-wal", "-shm"]:
                    old_sub = old_db_path.with_name(old_db_path.name + suffix)
                    if old_sub.exists():
                        shutil.move(str(old_sub), str(self.db_path.with_name(self.db_path.name + suffix)))
        self.async_conn: Optional[aiosqlite.Connection] = None
        self.checkpointer: Optional[AsyncSqliteSaver] = None

    @classmethod
    async def get_instance(cls, db_path: Optional[str] = None) -> "SessionManager":
        """异步单例工厂方法"""
        if cls._instance is None:
            cls._instance = cls(db_path)
            await cls._instance.initialize()
        return cls._instance

    async def initialize(self):
        """异步初始化连接与表结构"""
        if self.async_conn is not None:
            return

        self.async_conn = await aiosqlite.connect(str(self.db_path))
        self.checkpointer = AsyncSqliteSaver(self.async_conn)
        await self.checkpointer.setup()

        # 初始化业务元数据表 sessions_meta
        await self.async_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions_meta (
                session_id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        await self.async_conn.commit()

    def get_checkpointer(self) -> AsyncSqliteSaver:
        if self.checkpointer is None:
            raise RuntimeError("SessionManager 尚未初始化，请先调用 await session_manager.initialize()")
        return self.checkpointer

    async def close(self):
        """异步关闭数据库连接并重置实例状态，释放 Windows 文件句柄"""
        if self.async_conn is not None:
            await self.async_conn.close()
            self.async_conn = None
            self.checkpointer = None
        if SessionManager._instance is self:
            SessionManager._instance = None

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """异步获取指定会话的元数据"""
        async with aiosqlite.connect(str(self.db_path)) as conn:
            cursor = await conn.execute(
                "SELECT session_id, agent_name, title, created_at, updated_at FROM sessions_meta WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "session_id": row[0],
                "agent_name": row[1],
                "title": row[2],
                "created_at": row[3],
                "updated_at": row[4],
            }

    def list_sessions_sync(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """同步查询全部会话列表（供前端 API 或展示使用）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            if agent_name:
                cursor.execute(
                    "SELECT session_id, agent_name, title, created_at, updated_at "
                    "FROM sessions_meta WHERE agent_name = ? ORDER BY updated_at DESC",
                    (agent_name,),
                )
            else:
                cursor.execute(
                    "SELECT session_id, agent_name, title, created_at, updated_at "
                    "FROM sessions_meta ORDER BY updated_at DESC"
                )
            rows = cursor.fetchall()
            return [
                {
                    "session_id": r[0],
                    "agent_name": r[1],
                    "title": r[2],
                    "created_at": r[3],
                    "updated_at": r[4],
                }
                for r in rows
            ]

    async def list_sessions_async(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """异步查询全部会话列表"""
        async with aiosqlite.connect(str(self.db_path)) as conn:
            if agent_name:
                cursor = await conn.execute(
                    "SELECT session_id, agent_name, title, created_at, updated_at "
                    "FROM sessions_meta WHERE agent_name = ? ORDER BY updated_at DESC",
                    (agent_name,),
                )
            else:
                cursor = await conn.execute(
                    "SELECT session_id, agent_name, title, created_at, updated_at "
                    "FROM sessions_meta ORDER BY updated_at DESC"
                )
            rows = await cursor.fetchall()
            return [
                {
                    "session_id": r[0],
                    "agent_name": r[1],
                    "title": r[2],
                    "created_at": r[3],
                    "updated_at": r[4],
                }
                for r in rows
            ]

    async def ensure_session_title(
        self,
        session_id: str,
        agent_name: str,
        first_user_message: str,
        llm: Optional[Any] = None,
    ) -> str:
        """
        确保会话拥有标题。
        若为全新会话，调用大模型将用户输入内容智能压缩提炼为精炼标题（参考 OpenAI 网页端机制），并持久化到 SQLite。
        """
        existing = await self.get_session(session_id)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if existing:
            # 存量会话：更新最后活跃时间
            async with aiosqlite.connect(str(self.db_path)) as conn:
                await conn.execute(
                    "UPDATE sessions_meta SET updated_at = ? WHERE session_id = ?",
                    (now_str, session_id),
                )
                await conn.commit()
            return existing["title"]

        # 新会话：通过大模型提炼压缩标题
        generated_title = None
        if llm:
            try:
                system_prompt = (
                    "你是一个会话标题提炼专家。请阅读用户的输入内容，提炼为一个4到12个字的极简中文标题。\n"
                    "要求：\n"
                    "1. 不要标点符号、不要引号、不要出现'标题：'等任何前缀或解释；\n"
                    "2. 紧扣主题的核心动作与标的名称；\n"
                    "示例：'请帮我查询股票贵州茅台的实时行情快照，告诉我最新价格' -> '贵州茅台行情快照'\n"
                    "示例：'读取5个交易日K线研判走势' -> '5日K线走势研判'\n"
                )
                response = await llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=first_user_message[:300]),
                ])
                raw_text = response.content
                if isinstance(raw_text, str):
                    clean = raw_text.strip().replace('"', '').replace("'", "").replace("。", "")
                    if clean:
                        generated_title = clean[:16]
            except Exception:
                pass

        if not generated_title:
            clean = first_user_message.strip().replace("\n", " ")
            generated_title = clean[:12] + "..." if len(clean) > 12 else clean

        # 写入 sessions_meta 表
        async with aiosqlite.connect(str(self.db_path)) as conn:
            await conn.execute(
                "INSERT INTO sessions_meta (session_id, agent_name, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, agent_name, generated_title, now_str, now_str),
            )
            await conn.commit()
        return generated_title
