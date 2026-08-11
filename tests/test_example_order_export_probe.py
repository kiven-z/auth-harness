"""example_order 异步导出探针纯逻辑测试。"""

from __future__ import annotations

import unittest

from auth_harness.services.example_order_export_probe import is_terminal_status


class ExampleOrderExportProbeTest(unittest.TestCase):
    """终态判断。"""

    def test_terminal_statuses(self) -> None:
        self.assertTrue(is_terminal_status("SUCCESS"))
        self.assertTrue(is_terminal_status("failed"))
        self.assertTrue(is_terminal_status("CANCELLED"))
        self.assertTrue(is_terminal_status("EXPIRED"))

    def test_non_terminal_statuses(self) -> None:
        self.assertFalse(is_terminal_status("PENDING"))
        self.assertFalse(is_terminal_status("RUNNING"))
        self.assertFalse(is_terminal_status(None))
        self.assertFalse(is_terminal_status(""))
