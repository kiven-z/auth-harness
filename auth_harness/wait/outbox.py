"""Outbox 轮询等待。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pymysql

from auth_harness.config import HarnessConfig
from auth_harness.infrastructure import db as db_mod

OUTBOX_STATUS_SUCCESS = "SUCCESS"
OUTBOX_TERMINAL_FAILURE = frozenset({"FAILED", "DEAD"})


@dataclass(frozen=True)
class OutboxCursor:
    """等待开始前记录的 outbox 游标，避免匹配到历史 SUCCESS 行。"""

    min_id: int


def snapshot_outbox_cursor(
    conn: pymysql.connections.Connection,
    source_biz_id_contains: str | None,
) -> OutboxCursor:
    """在触发变更或开始等待前快照当前最大 outbox id。"""
    return OutboxCursor(min_id=db_mod.fetch_max_outbox_id(conn, source_biz_id_contains))


def wait_outbox_success(
    conn: pymysql.connections.Connection,
    config: HarnessConfig,
    *,
    source_biz_id_contains: str | None = None,
    timeout_sec: float | None = None,
    cursor: OutboxCursor | None = None,
) -> dict[str, Any]:
    """等待游标之后的新 outbox 行进入 SUCCESS。"""
    wait_conf = config.wait
    interval = wait_conf["outbox_poll_interval_sec"]
    timeout = timeout_sec if timeout_sec is not None else wait_conf["outbox_timeout_sec"]
    active_cursor = cursor or snapshot_outbox_cursor(conn, source_biz_id_contains)
    deadline = time.time() + timeout
    last_row: dict[str, Any] | None = None

    while time.time() < deadline:
        row = db_mod.fetch_outbox_after_id(conn, active_cursor.min_id, source_biz_id_contains)
        if row:
            last_row = row
            status = row.get("status")
            if status == OUTBOX_STATUS_SUCCESS:
                print(f"[wait] outbox SUCCESS id={row.get('id')} eventId={row.get('event_id')}")
                return row
            if status in OUTBOX_TERMINAL_FAILURE:
                raise TimeoutError(
                    f"outbox 进入失败态 status={status} id={row.get('id')} "
                    f"error={row.get('last_error')}"
                )
            print(f"[wait] outbox status={status} id={row.get('id')}，继续轮询…")
        else:
            print(f"[wait] id>{active_cursor.min_id} 尚无新 outbox 行，继续轮询…")
        time.sleep(interval)

    detail = f" last={last_row}" if last_row else ""
    raise TimeoutError(f"等待 outbox SUCCESS 超时 ({timeout}s){detail}")
