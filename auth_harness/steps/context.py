"""场景步骤执行上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pymysql
import redis

from auth_harness.config import HarnessConfig
from auth_harness.infrastructure.api import ApiClient
from auth_harness.wait.outbox import OutboxCursor


@dataclass
class StepContext:
    """步骤执行共享状态。"""

    config: HarnessConfig
    conn: pymysql.connections.Connection
    rds: redis.Redis
    api: ApiClient
    last_outbox_row: dict[str, Any] | None = None
    step_entry_cursor: OutboxCursor | None = None
    previous_step_cursor: OutboxCursor | None = None
    pending_outbox_cursors: dict[str, OutboxCursor] = field(default_factory=dict)

    def cursor_key(self, source_biz_id_contains: str | None) -> str:
        """生成 outbox 游标缓存键。"""
        return source_biz_id_contains or "__global__"

    def remember_outbox_cursor(self, source_biz_id_contains: str | None, cursor: OutboxCursor) -> None:
        """缓存显式 prepare_outbox_wait 记录的游标。"""
        self.pending_outbox_cursors[self.cursor_key(source_biz_id_contains)] = cursor

    def resolve_outbox_cursor(self, source_biz_id_contains: str | None) -> OutboxCursor | None:
        """解析 wait_outbox 应使用的游标（显式 > 上一步边界 > 无）。"""
        explicit = self.pending_outbox_cursors.pop(self.cursor_key(source_biz_id_contains), None)
        if explicit is not None:
            return explicit
        if self.previous_step_cursor is not None:
            return self.previous_step_cursor
        return None
