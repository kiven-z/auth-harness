"""单元测试：影响面反查与负向断言。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from auth_harness.domain.impact import compare_user_sets, resolve_impacted_user_ids
from auth_harness.services.impact import _assert_case


class ImpactCompareTest(unittest.TestCase):
    """compare_user_sets 差异检测。"""

    def test_identical_sets(self) -> None:
        self.assertEqual(compare_user_sets({1, 2}, {1, 2}), [])

    def test_missing_users(self) -> None:
        diffs = compare_user_sets({1, 2}, {1})
        self.assertTrue(any("缺少" in d for d in diffs))


class ImpactAssertCaseTest(unittest.TestCase):
    """fixture 用例断言模式。"""

    def test_expected_count_min(self) -> None:
        ok = _assert_case({"expected_count_min": 2}, "t", {1, 2, 3})
        self.assertTrue(ok)

    def test_expected_user_ids(self) -> None:
        ok = _assert_case({"expected_user_ids": [1]}, "t", {1})
        self.assertTrue(ok)


class ResolveImpactSqlTest(unittest.TestCase):
    """resolve_impacted_user_ids 委托 DB 查询。"""

    @patch("auth_harness.domain.impact.db_mod.fetch_all")
    def test_grant_user(self, fetch_mock) -> None:
        fetch_mock.return_value = [{"user_id": 9001001001}]
        conn = MagicMock()
        result = resolve_impacted_user_ids(conn, "GRANT_USER", subject_ids=[9001001001])
        self.assertEqual(result, {9001001001})


if __name__ == "__main__":
    unittest.main()
