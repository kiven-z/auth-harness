"""失效事件表断言。"""

from __future__ import annotations

from typing import Any

import pymysql

from auth_harness.infrastructure import db as db_mod

PROCESSING_PLACEHOLDER_COUNT = -1


def assert_event_counts(
    conn: pymysql.connections.Connection,
    event_id: str,
    spec: dict[str, Any],
) -> None:
    """断言 auth_authorization_invalidation_event 中的统计字段。"""
    row = db_mod.fetch_invalidation_event(conn, event_id)
    if not row:
        raise AssertionError(f"未找到失效事件 event_id={event_id}")

    impacted = int(row.get("impacted_user_count") or 0)
    if impacted == PROCESSING_PLACEHOLDER_COUNT:
        raise AssertionError(f"失效事件仍在处理中 event_id={event_id}")

    _assert_min("impacted_user_count", spec.get("impacted_user_count_min"), impacted, event_id)
    _assert_min(
        "profile_refreshed_count",
        spec.get("profile_refreshed_count_min"),
        int(row.get("profile_refreshed_count") or 0),
        event_id,
    )
    _assert_min(
        "version_bumped_count",
        spec.get("version_bumped_count_min"),
        int(row.get("version_bumped_count") or 0),
        event_id,
    )

    print(
        f"[assert] event {event_id}: impacted={impacted} "
        f"refreshed={row.get('profile_refreshed_count')}"
    )


def _assert_min(field: str, expected_min: Any, actual: int, event_id: str) -> None:
    if expected_min is None:
        return
    minimum = int(expected_min)
    if actual < minimum:
        raise AssertionError(
            f"event {event_id} {field} 未满足: expected>={minimum}, actual={actual}"
        )
