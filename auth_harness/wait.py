"""轮询 sys_authorization_invalidation_outbox 直至 SUCCESS。"""

from __future__ import annotations

import time
from typing import Any

import pymysql

from auth_harness.config import HarnessConfig
from auth_harness import db as db_mod

SUCCESS = "SUCCESS"
TERMINAL_FAILURE = {"FAILED", "DEAD"}


def wait_outbox_success(
    conn: pymysql.connections.Connection,
    config: HarnessConfig,
    *,
    source_biz_id_contains: str | None = None,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """等待最新匹配 outbox 行进入 SUCCESS。"""
    wait_conf = config.wait
    interval = wait_conf["outbox_poll_interval_sec"]
    timeout = timeout_sec if timeout_sec is not None else wait_conf["outbox_timeout_sec"]
    deadline = time.time() + timeout
    last_row: dict[str, Any] | None = None

    while time.time() < deadline:
        row = _fetch_latest_outbox(conn, source_biz_id_contains)
        if row:
            last_row = row
            status = row.get("status")
            if status == SUCCESS:
                print(f"[wait] outbox SUCCESS id={row.get('id')} eventId={row.get('event_id')}")
                return row
            if status in TERMINAL_FAILURE:
                raise TimeoutError(
                    f"outbox 进入失败态 status={status} id={row.get('id')} error={row.get('last_error')}"
                )
            print(f"[wait] outbox status={status} id={row.get('id')}，继续轮询…")
        else:
            print("[wait] 尚未找到匹配 outbox 行，继续轮询…")
        time.sleep(interval)

    detail = f" last={last_row}" if last_row else ""
    raise TimeoutError(f"等待 outbox SUCCESS 超时 ({timeout}s){detail}")


def _fetch_latest_outbox(
    conn: pymysql.connections.Connection,
    source_biz_id_contains: str | None,
) -> dict[str, Any] | None:
    if source_biz_id_contains:
        return db_mod.fetch_one(
            conn,
            """
            SELECT id, event_id, status, source_biz_id, last_error, processed_at, create_time
            FROM sys_authorization_invalidation_outbox
            WHERE source_biz_id LIKE %s
            ORDER BY create_time DESC, id DESC
            LIMIT 1
            """,
            (f"%{source_biz_id_contains}%",),
        )
    return db_mod.fetch_one(
        conn,
        """
        SELECT id, event_id, status, source_biz_id, last_error, processed_at, create_time
        FROM sys_authorization_invalidation_outbox
        ORDER BY create_time DESC, id DESC
        LIMIT 1
        """,
    )
