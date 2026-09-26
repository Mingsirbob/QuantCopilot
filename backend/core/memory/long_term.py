"""
长期记忆管理核心模块 (Long-Term Memory Manager)
提供基于实体键值档案 (SQLite) 与用户偏好画像 (Markdown) 的分层长期记忆体系：
1. User Profile: 全局持久化用户偏好与投资风格 (workspace/runtime/memory/user_profile.md)
2. Entity Archives: 标的/股票历史研报与关键支撑位档案 (workspace/runtime/memory/entity_archives.db)
"""

import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


DEFAULT_USER_PROFILE_TEMPLATE = """# 用户长期投资画像与分析偏好 (User Profile)

## 1. 基础投资偏好与风格
- **风险承受度**: 稳健偏进取，注重回撤控制与确定性
- **交易周期偏好**: 短线至中短期波段 (5~20个交易日)
- **重点关注板块**: 新能源产业链、算力芯片半导体、高端制造

## 2. 量化技术分析习惯
- **常用指标偏好**: 优先参考 5日均线 (MA5) 及均线偏离度 (Bias5)，重视成交量与量价配合矩阵
- **多空研判底线**: 严谨基于真实 K 线数据计算，拒绝主观臆断与过度乐观

## 3. 报告输出规范
- **结构偏好**: 结论置顶 (先明确定性走势)，数据以 Markdown 表格对比展示，必须附带量化归因与关键支撑压力位
"""


class LongTermMemoryManager:
    """长期记忆管理中枢 (单例模式)"""

    _instance: Optional["LongTermMemoryManager"] = None

    def __init__(self, memory_dir: Optional[Path] = None):
        if memory_dir is not None:
            self.memory_dir = Path(memory_dir).resolve()
        else:
            # 默认定位 workspace/runtime/memory
            env_ws = os.getenv("WORKSPACE_DIR")
            if env_ws:
                root_ws = Path(env_ws).resolve()
            else:
                project_root = Path(__file__).resolve().parents[3]
                root_ws = project_root / "workspace"
            self.memory_dir = (root_ws / "runtime" / "memory").resolve()

        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.memory_dir / "user_profile.md"
        self.db_path = self.memory_dir / "entity_archives.db"

        # 确保初始化用户画像模板
        if not self.profile_file.exists():
            with open(self.profile_file, "w", encoding="utf-8") as f:
                f.write(DEFAULT_USER_PROFILE_TEMPLATE)

        # 初始化标的档案表
        self._init_db()

    @classmethod
    def get_instance(cls, memory_dir: Optional[Path] = None) -> "LongTermMemoryManager":
        if cls._instance is None:
            cls._instance = cls(memory_dir)
        return cls._instance

    def _init_db(self):
        """初始化实体长期记忆 SQLite 架构"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entity_memories (
                    entity_id TEXT PRIMARY KEY,
                    entity_name TEXT NOT NULL,
                    last_trend TEXT,
                    key_levels TEXT,
                    latest_summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ==================== 用户画像 (User Profile) ====================

    def get_user_profile(self) -> str:
        """获取用户画像与全局偏好内容"""
        if self.profile_file.exists():
            with open(self.profile_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return DEFAULT_USER_PROFILE_TEMPLATE.strip()

    def update_user_profile(self, new_content: str) -> None:
        """全量覆盖或更新用户画像文件"""
        with open(self.profile_file, "w", encoding="utf-8") as f:
            f.write(new_content.strip() + "\n")

    def append_user_preference(self, note: str) -> None:
        """向用户画像中追加一条偏好笔记"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n- [{now_str}] {note.strip()}"
        with open(self.profile_file, "a", encoding="utf-8") as f:
            f.write(entry)

    # ==================== 标的档案 (Entity Archives) ====================

    def save_entity_archive(
        self,
        entity_id: str,
        entity_name: str,
        latest_summary: str,
        last_trend: Optional[str] = None,
        key_levels: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """沉淀或更新某个标的/实体的研报档案"""
        clean_id = entity_id.strip().lower()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        levels_json = json.dumps(key_levels or {}, ensure_ascii=False)

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT INTO entity_memories (entity_id, entity_name, last_trend, key_levels, latest_summary, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    entity_name=excluded.entity_name,
                    last_trend=excluded.last_trend,
                    key_levels=excluded.key_levels,
                    latest_summary=excluded.latest_summary,
                    updated_at=excluded.updated_at;
                """,
                (clean_id, entity_name.strip(), last_trend or "", levels_json, latest_summary.strip(), now_str),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "entity_id": clean_id,
            "entity_name": entity_name,
            "status": "saved",
            "updated_at": now_str,
        }

    def recall_entity(self, query: str) -> Optional[Dict[str, Any]]:
        """
        根据标的代码或名称召回历史长期记忆档案。
        支持模糊匹配（例如输入 '宁德时代' 或 '300750' 均可匹配 'stock:300750'）
        """
        clean_q = query.strip().lower()
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entity_id, entity_name, last_trend, key_levels, latest_summary, updated_at
                FROM entity_memories
                WHERE entity_id = ? OR entity_id LIKE ? OR entity_name LIKE ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (clean_q, f"%{clean_q}%", f"%{clean_q}%"),
            )
            row = cursor.fetchone()
            if not row:
                return None

            key_levels_parsed = {}
            if row[3]:
                try:
                    key_levels_parsed = json.loads(row[3])
                except Exception:
                    pass

            return {
                "entity_id": row[0],
                "entity_name": row[1],
                "last_trend": row[2],
                "key_levels": key_levels_parsed,
                "latest_summary": row[4],
                "updated_at": row[5],
            }
        finally:
            conn.close()

    def list_all_entities(self) -> List[Dict[str, Any]]:
        """列出记忆库中所有已建档的标的与最新状态"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entity_id, entity_name, last_trend, updated_at
                FROM entity_memories
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "entity_id": r[0],
                    "entity_name": r[1],
                    "last_trend": r[2],
                    "updated_at": r[3],
                }
                for r in rows
            ]
        finally:
            conn.close()
