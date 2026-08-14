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
    """等待开始前记录的全局 outbox 游标（max id），避免匹配历史行。"""

    min_id: int


def snapshot_outbox_cursor(conn: pymysql.connections.Connection) -> OutboxCursor:
    """在触发变更前快照当前全局最大 outbox id。

    游标始终取全表 max(id)；`source_biz_id_contains` 仅用于等待时筛选行，
    不能用于游标，否则会把游标卡在旧 move:/update: 行上导致空转或误匹配。
    """
    return OutboxCursor(min_id=db_mod.fetch_max_outbox_id(conn))


def wait_outbox_success(
    conn: pymysql.connections.Connection,
    config: HarnessConfig,
    *,
    source_biz_id_contains: str | None = None,
    timeout_sec: float | None = None,
    cursor: OutboxCursor | None = None,
) -> dict[str, Any]:
    """等待游标之后、且匹配过滤条件的新 outbox 行进入 SUCCESS。"""
    wait_conf = config.wait
    interval = wait_conf["outbox_poll_interval_sec"]
    timeout = timeout_sec if timeout_sec is not None else wait_conf["outbox_timeout_sec"]
    active_cursor = cursor or snapshot_outbox_cursor(conn)
    deadline = time.time() + timeout
    last_row: dict[str, Any] | None = None
    last_log_at = 0.0
    log_interval = max(interval * 4, 2.0)
    filter_label = source_biz_id_contains or "*"

    print(
        f"[wait] 等待 outbox SUCCESS cursor>{active_cursor.min_id} "
        f"filter={filter_label!r} timeout={timeout}s"
    )

    while time.time() < deadline:
        row = db_mod.fetch_outbox_after_id(conn, active_cursor.min_id, source_biz_id_contains)
        if row:
            last_row = row
            status = row.get("status")
            if status == OUTBOX_STATUS_SUCCESS:
                print(
                    f"[wait] outbox SUCCESS id={row.get('id')} "
                    f"source={row.get('source_biz_id')} eventId={row.get('event_id')}"
                )
                return row
            if status in OUTBOX_TERMINAL_FAILURE:
                raise TimeoutError(
                    f"outbox 进入失败态 status={status} id={row.get('id')} "
                    f"error={row.get('last_error')}"
                )
            now = time.time()
            if now - last_log_at >= log_interval:
                print(
                    f"[wait] outbox status={status} id={row.get('id')} "
                    f"source={row.get('source_biz_id')}，继续轮询…"
                )
                last_log_at = now
        else:
            now = time.time()
            if now - last_log_at >= log_interval:
                print(
                    f"[wait] cursor>{active_cursor.min_id} filter={filter_label!r} "
                    f"尚无匹配 outbox（若 API 为 no-op 则不会写入），继续轮询…"
                )
                last_log_at = now
        time.sleep(interval)

    hint = (
        " 提示：确认上一步 API 已实际变更（如 dept move 父级未变则为 no-op）；"
        "过滤须与后端 operation 前缀一致"
        "（DELETE /{userId} 是 delete-dept: / delete-post:，"
        "DELETE /{userId}/all 才是 clear-dept: / clear-post:）；"
        "或先 make seed 重置 harness 数据。"
    )
    detail = f" last={last_row}" if last_row else ""
    raise TimeoutError(
        f"等待 outbox SUCCESS 超时 ({timeout}s) cursor>{active_cursor.min_id} "
        f"filter={filter_label!r}{detail}.{hint}"
    )
