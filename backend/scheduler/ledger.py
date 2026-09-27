"""
任务执行账本 (TaskLedger)
基于 aiosqlite 实现任务执行历史、状态追踪、耗时统计与错误记录的持久化。
默认存储于 workspace/runtime/scheduler/ledger.db
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite


class TaskLedger:
    """
    轻量级异步任务执行账本。
    记录每个任务的触发时间、完成时间、状态 (PENDING/RUNNING/SUCCESS/FAILED/SKIPPED)、输出摘要与报错。
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            env_ws = os.getenv("WORKSPACE_DIR")
            if env_ws:
                root_ws = Path(env_ws).resolve()
            else:
                project_root = Path(__file__).resolve().parents[2]
                root_ws = project_root / "workspace"

            scheduler_dir = root_ws / "runtime" / "scheduler"
            scheduler_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = (scheduler_dir / "ledger.db").resolve()

    async def init_db(self):
        """初始化账本数据表"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    run_id TEXT PRIMARY KEY,
                    task_name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_seconds REAL,
                    params_json TEXT,
                    result_summary TEXT,
                    error_message TEXT,
                    metadata_json TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_name ON task_runs(task_name)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_start_time ON task_runs(start_time)"
            )
            await db.commit()

    async def record_start(
        self,
        run_id: str,
        task_name: str,
        task_type: str,
        params: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """记录任务开始运行"""
        await self.init_db()
        now_str = datetime.now().isoformat()
        params_json = json.dumps(params or {}, ensure_ascii=False)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO task_runs 
                (run_id, task_name, task_type, status, start_time, params_json, metadata_json)
                VALUES (?, ?, ?, 'RUNNING', ?, ?, ?)
                """,
                (run_id, task_name, task_type, now_str, params_json, meta_json),
            )
            await db.commit()

    async def record_finish(
        self,
        run_id: str,
        status: str,
        result_data: Any = None,
        error_message: Optional[str] = None,
        duration_seconds: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """记录任务完成（成功或失败）"""
        now_str = datetime.now().isoformat()
        summary = ""
        if result_data is not None:
            if isinstance(result_data, str):
                summary = result_data[:500]
            else:
                try:
                    summary = json.dumps(result_data, ensure_ascii=False)[:500]
                except Exception:
                    summary = str(result_data)[:500]

        meta_json = json.dumps(metadata or {}, ensure_ascii=False) if metadata else None

        async with aiosqlite.connect(self.db_path) as db:
            if meta_json:
                await db.execute(
                    """
                    UPDATE task_runs
                    SET status = ?, end_time = ?, duration_seconds = ?,
                        result_summary = ?, error_message = ?, metadata_json = ?
                    WHERE run_id = ?
                    """,
                    (status, now_str, duration_seconds, summary, error_message, meta_json, run_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE task_runs
                    SET status = ?, end_time = ?, duration_seconds = ?,
                        result_summary = ?, error_message = ?
                    WHERE run_id = ?
                    """,
                    (status, now_str, duration_seconds, summary, error_message, run_id),
                )
            await db.commit()

    async def get_recent_runs(self, task_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近运行记录"""
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if task_name:
                cursor = await db.execute(
                    "SELECT * FROM task_runs WHERE task_name = ? ORDER BY start_time DESC LIMIT ?",
                    (task_name, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM task_runs ORDER BY start_time DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
