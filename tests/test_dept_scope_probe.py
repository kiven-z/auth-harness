"""部门维画像解析：dataScopes.DEPT，缺维按 SELF。"""

from __future__ import annotations

import unittest

from auth_harness.services.dept_scope_probe import dept_grant


class DeptGrantTest(unittest.TestCase):
    """从 /me 画像取出部门维授权。"""

    def test_reads_dept_dimension(self) -> None:
        profile = {
            "userId": 4,
            "dataScopes": {
                "DEPT": {
                    "scopeType": "IDS_AND_CHILD",
                    "values": [110, 111, 112],
                }
            },
        }
        scope_type, values = dept_grant(profile)
        self.assertEqual(scope_type, "IDS_AND_CHILD")
        self.assertEqual(values, {110, 111, 112})

    def test_missing_dimension_is_self(self) -> None:
        for profile in ({}, {"dataScopes": {}}, {"dataScopes": None}, {"dataScopes": {"PROJECT": {}}}):
            with self.subTest(profile=profile):
                scope_type, values = dept_grant(profile)
                self.assertEqual(scope_type, "SELF")
                self.assertEqual(values, set())
