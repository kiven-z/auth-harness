"""单元测试：纯逻辑（oracle 对比、步骤注册、outbox 游标）。"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from auth_harness.domain.oracle import compare_profiles
from auth_harness.domain.outbox_ops import CREATE_POST, DELETE_DEPT, KNOWN_PREFIXES, require_known_prefix
from auth_harness.domain.paths import SCENARIOS_DIR
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

    def test_missing_redis_skipped_when_not_required(self) -> None:
        oracle = {"userId": 42, "roles": ["R_A"], "permissions": []}
        self.assertEqual(compare_profiles(oracle, None, require_redis=False), [])

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
    """wait_outbox 游标与轮询。"""

    @patch("auth_harness.wait.outbox.time.sleep")
    @patch("auth_harness.wait.outbox.db_mod.fetch_outbox_after_id")
    @patch("auth_harness.wait.outbox.db_mod.fetch_max_outbox_id")
    def test_uses_global_cursor_when_not_provided(self, max_id_mock, fetch_mock, _sleep_mock) -> None:
        config = MagicMock()
        config.wait = {"outbox_poll_interval_sec": 0.01, "outbox_timeout_sec": 1}
        conn = MagicMock()
        max_id_mock.return_value = 99
        fetch_mock.side_effect = [
            None,
            {"id": 100, "status": "SUCCESS", "event_id": "e1", "source_biz_id": "move:deadbeef"},
        ]

        row = wait_outbox_success(conn, config, source_biz_id_contains="move:")

        self.assertEqual(row["id"], 100)
        max_id_mock.assert_called_once_with(conn)
        first_call = fetch_mock.call_args_list[0]
        self.assertEqual(first_call.args[1], 99)
        self.assertEqual(first_call.args[2], "move:")

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
            {"id": 11, "status": "PENDING", "event_id": "e1", "source_biz_id": "update:abcd1234"},
            {"id": 11, "status": "SUCCESS", "event_id": "e1", "source_biz_id": "update:abcd1234"},
        ]

        row = wait_outbox_success(conn, config, cursor=cursor)

        self.assertEqual(row["id"], 11)
        first_call = fetch_mock.call_args_list[0]
        self.assertEqual(first_call.args[1], 10)


class OutboxOpsTest(unittest.TestCase):
    """outbox 过滤前缀须与后端 operation 对齐。"""

    def test_accepts_known_prefix(self) -> None:
        self.assertEqual(require_known_prefix(DELETE_DEPT), DELETE_DEPT)
        self.assertEqual(require_known_prefix(CREATE_POST), CREATE_POST)
        self.assertIsNone(require_known_prefix(None))

    def test_rejects_legacy_id_embedded_filter(self) -> None:
        with self.assertRaises(ValueError):
            require_known_prefix("create-post:9001002003")

    def test_rejects_unknown_prefix(self) -> None:
        with self.assertRaises(ValueError):
            require_known_prefix("wipe-dept:")
        with self.assertRaises(ValueError):
            require_known_prefix("clear-dept:9001002002")

    def test_scenario_yaml_filters_are_known_prefixes(self) -> None:
        unknown: list[str] = []
        for path in sorted(SCENARIOS_DIR.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for block_name in ("setup", "steps"):
                for step in data.get(block_name) or []:
                    if not isinstance(step, dict):
                        continue
                    params = next(iter(step.values()), {})
                    if not isinstance(params, dict):
                        continue
                    for key in ("source_biz_id_contains", "outbox_source_contains"):
                        value = params.get(key)
                        if value is not None and value not in KNOWN_PREFIXES:
                            unknown.append(f"{path.name}: {key}={value!r}")
        self.assertEqual(unknown, [])

    def test_scenario_yaml_has_no_prepare_outbox_wait(self) -> None:
        leftover: list[str] = []
        for path in sorted(SCENARIOS_DIR.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for block_name in ("setup", "steps"):
                for step in data.get(block_name) or []:
                    if isinstance(step, dict) and "prepare_outbox_wait" in step:
                        leftover.append(path.name)
        self.assertEqual(leftover, [])

    def test_relation_steps_have_no_status(self) -> None:
        relation_steps = {
            "post_user_dept",
            "put_user_dept",
            "ensure_user_dept",
            "post_user_post",
            "ensure_user_post",
        }
        leftover: list[str] = []
        for path in sorted(SCENARIOS_DIR.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for block_name in ("setup", "steps"):
                for step in data.get(block_name) or []:
                    if not isinstance(step, dict):
                        continue
                    name, params = next(iter(step.items()))
                    if name in relation_steps and isinstance(params, dict) and "status" in params:
                        leftover.append(f"{path.name}:{name}")
        self.assertEqual(leftover, [])


class SeedSqlContractTest(unittest.TestCase):
    """种子任职 INSERT 不得带关联 status 列。"""

    def test_user_org_inserts_drop_status_column(self) -> None:
        from auth_harness.domain.paths import SQL_DIR

        leftover: list[str] = []
        for name in ("seed_users_bulk.sql", "seed_anchors.sql"):
            text = (SQL_DIR / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip().upper()
                if stripped.startswith("INSERT INTO USER_DEPT") or stripped.startswith("INSERT INTO USER_POST"):
                    if "STATUS" in stripped:
                        leftover.append(f"{name}: {line.strip()}")
        self.assertEqual(leftover, [])


class EffectiveMembershipSqlContractTest(unittest.TestCase):
    """oracle 走有效 view；查任职行打基表。"""

    def test_oracle_sql_uses_effective_views(self) -> None:
        from auth_harness.infrastructure.db import ORACLE_PERMISSIONS_SQL, ORACLE_ROLES_SQL

        for sql in (ORACLE_ROLES_SQL, ORACLE_PERMISSIONS_SQL):
            self.assertIn("v_user_dept_effective", sql)
            self.assertIn("v_user_post_effective", sql)
            self.assertNotIn("status IN", sql)

    def test_lookup_sql_hits_base_tables(self) -> None:
        from auth_harness.infrastructure import db as db_mod

        source = Path(db_mod.__file__).read_text(encoding="utf-8")
        self.assertIn("FROM user_dept", source)
        self.assertIn("FROM user_post", source)
        self.assertNotIn("status IN (1, 2)", source)


class FlushHarnessProfilesTest(unittest.TestCase):
    """seed 只清 9001* 画像。"""

    def test_deletes_matching_keys(self) -> None:
        from auth_harness.infrastructure.redis_client import (
            HARNESS_PERM_KEY_PATTERN,
            delete_harness_profiles,
        )

        client = MagicMock()
        client.scan_iter.return_value = [
            "auth:security:user:perm:9001000171",
            "auth:security:user:perm:9001002001",
        ]
        client.delete.return_value = 2
        self.assertEqual(delete_harness_profiles(client), 2)
        client.scan_iter.assert_called_once_with(match=HARNESS_PERM_KEY_PATTERN, count=500)
        client.delete.assert_called_once()

    def test_noop_when_empty(self) -> None:
        from auth_harness.infrastructure.redis_client import delete_harness_profiles

        client = MagicMock()
        client.scan_iter.return_value = []
        self.assertEqual(delete_harness_profiles(client), 0)
        client.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
