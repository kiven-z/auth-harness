"""system_paths 与后端 Controller 路径契约。"""

from __future__ import annotations

import unittest

from auth_harness.infrastructure import system_paths as paths


class SystemPathsTest(unittest.TestCase):
    """Admin API 路径须与 auth-server 一致。"""

    def test_dept_move_uses_body_id_not_path_param(self) -> None:
        self.assertEqual(paths.dept_move(), "/api/system/dept/move")
        self.assertNotIn("{", paths.dept_move())

    def test_dept_roles_uses_resource_id_in_path(self) -> None:
        self.assertEqual(paths.dept_roles(9000100001), "/api/system/dept/9000100001/roles")

    def test_user_dept_nested_path(self) -> None:
        self.assertEqual(
            paths.user_dept_item(9001002002, 9002002101),
            "/api/system/user-dept/9001002002/9002002101",
        )


if __name__ == "__main__":
    unittest.main()
