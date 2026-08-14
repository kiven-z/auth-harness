"""场景步骤执行上下文。"""

from __future__ import annotations

from dataclasses import dataclass
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
