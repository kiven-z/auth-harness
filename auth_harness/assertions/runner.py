"""场景断言执行器（含 reconcile 重试）。"""

from __future__ import annotations

import random
import time
from typing import Any

from auth_harness.assertions.event import assert_event_counts
from auth_harness.assertions.user_codes import assert_user_codes
from auth_harness.infrastructure import db as db_mod
from auth_harness.steps.context import StepContext


class AssertRunner:
    """执行 YAML assert 块：部门扇出、事件统计、用户抽样与码断言。"""

    def __init__(self, ctx: StepContext) -> None:
        self._ctx = ctx

    def run(self, block: dict[str, Any]) -> None:
        """运行断言块，失败时按 config.wait 重试。"""
        wait_conf = self._ctx.config.wait
        max_attempts = int(wait_conf["reconcile_max_attempts"])
        retry_sec = wait_conf["reconcile_retry_sec"]

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                self._run_once(block)
                return
            except AssertionError as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                print(f"[assert] 第 {attempt} 次失败，{retry_sec}s 后重试… ({exc})")
                time.sleep(retry_sec)

        raise AssertionError(str(last_error))

    def _run_once(self, block: dict[str, Any]) -> None:
        self._assert_dept_fanout(block)
        self._assert_event(block)

        for user_spec in block.get("users") or []:
            assert_user_codes(self._ctx, int(user_spec["user_id"]), user_spec)

        sample_spec = block.get("sample_from_dept")
        if sample_spec:
            self._assert_dept_sample(sample_spec)

    def _assert_dept_fanout(self, block: dict[str, Any]) -> None:
        """impacted_user_count_min：部门子树成员数下限（扇出规模校验）。"""
        min_count = block.get("impacted_user_count_min")
        if min_count is None:
            return
        dept_id = int(block.get("dept_id") or self._ctx.config.test_ids.get("dept_fanout", 9000100001))
        actual = db_mod.count_dept_members(self._ctx.conn, dept_id)
        if actual < int(min_count):
            raise AssertionError(f"impacted_user_count_min 未满足: expected>={min_count}, actual={actual}")
        print(f"[assert] dept {dept_id} 成员数 {actual} >= {min_count}")

    def _assert_event(self, block: dict[str, Any]) -> None:
        """可选事件表断言（仅 `event:` 块）。"""
        event_spec = block.get("event")
        if not event_spec:
            return

        event_id = event_spec.get("event_id")
        if not event_id and self._ctx.last_outbox_row:
            event_id = self._ctx.last_outbox_row.get("event_id")
        if not event_id:
            raise AssertionError("事件断言需要 event_id 或前置 wait_outbox 产生的 outbox 行")

        assert_event_counts(self._ctx.conn, str(event_id), event_spec)

    def _assert_dept_sample(self, sample_spec: dict[str, Any]) -> None:
        dept_id = int(sample_spec["dept_id"])
        sample_size = int(sample_spec.get("sample_size", 5))
        members = db_mod.list_dept_user_ids(self._ctx.conn, dept_id)
        picked = sorted(random.sample(members, min(sample_size, len(members))))
        print(f"[assert] sample_from_dept dept={dept_id} users={picked}")
        for user_id in picked:
            assert_user_codes(self._ctx, user_id, sample_spec)
