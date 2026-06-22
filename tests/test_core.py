"""单元测试：纯逻辑（oracle 对比、步骤注册、outbox 游标）。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from auth_harness.domain.oracle import compare_profiles
from auth_harness.steps.context import StepContext
from auth_harness.steps.registry import StepRegistry
from auth_harness.wait.outbox import OutboxCursor, wait_outbox_success


class CompareProfilesTest(unittest.TestCase):
    """compare_profiles 差异检测。"""

    def test_matching_profiles(self) -> None:
        # 角色与权限一致时应无差异
        oracle = {"userId": 1, "roles": ["R_A"], "permissions": ["p:a"], "permVersion": 2}
        redis_profile = {"userId": 1, "roles": ["R_A"], "permissions": ["p:a"], "permVersion": 2}
        self.assertEqual(compare_profiles(oracle, redis_profile), [])

    def test_missing_redis_profile(self) -> None:
        oracle = {"userId": 42, "roles": [], "permissions": []}
        diffs = compare_profiles(oracle, None)
        self.assertEqual(len(diffs), 1)
        self.assertIn("Redis 无画像", diffs[0])

    def test_perm_version_mismatch(self) -> None:
        oracle = {"userId": 1, "roles": [], "permissions": [], "permVersion": 3}
        redis_profile = {"userId": 1, "roles": [], "permissions": [], "permVersion": 2}
        diffs = compare_profiles(oracle, redis_profile)
        self.assertTrue(any("permVersion" in d for d in diffs))


class StepRegistryTest(unittest.TestCase):
    """步骤注册表解析。"""

    def test_register_and_execute(self) -> None:
        registry = StepRegistry()
        seen: list[str] = []

        @registry.register("echo")
        def echo_step(ctx: StepContext, params: dict) -> None:
            seen.append(params["msg"])

        ctx = MagicMock(spec=StepContext)
        registry.execute(ctx, {"echo": {"msg": "hello"}})
        self.assertEqual(seen, ["hello"])

    def test_unknown_step_raises(self) -> None:
        registry = StepRegistry()
        ctx = MagicMock(spec=StepContext)
        with self.assertRaises(ValueError):
            registry.execute(ctx, {"missing": {}})


class WaitOutboxCursorTest(unittest.TestCase):
    """wait_outbox 游标避免陈旧 SUCCESS。"""

    @patch("auth_harness.wait.outbox.time.sleep")
    @patch("auth_harness.wait.outbox.db_mod.fetch_outbox_after_id")
    def test_waits_for_row_after_cursor(self, fetch_mock, _sleep_mock) -> None:
        config = MagicMock()
        config.wait = {
            "outbox_poll_interval_sec": 0.01,
            "outbox_timeout_sec": 1,
        }
        conn = MagicMock()
        cursor = OutboxCursor(min_id=10)
        fetch_mock.side_effect = [
            None,
            {"id": 11, "status": "PENDING", "event_id": "e1"},
            {"id": 11, "status": "SUCCESS", "event_id": "e1"},
        ]

        row = wait_outbox_success(conn, config, cursor=cursor)

        self.assertEqual(row["id"], 11)
        first_call = fetch_mock.call_args_list[0]
        self.assertEqual(first_call.args[1], 10)


if __name__ == "__main__":
    unittest.main()
