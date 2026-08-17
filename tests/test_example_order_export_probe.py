"""example_order 异步导出探针纯逻辑测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from auth_harness.services.example_order_export_probe import (
    ExportCaseRun,
    any_execution_windows_overlap,
    execution_windows_overlap,
    is_terminal_status,
    parse_instant,
    _evaluate_parallel_overlap,
)


def _utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


class ExampleOrderExportProbeTest(unittest.TestCase):
    """终态判断、时间解析与并行窗口。"""

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

    def test_parse_instant_iso_z(self) -> None:
        parsed = parse_instant("2026-08-17T11:16:15.123Z")
        self.assertEqual(parsed, _utc(2026, 8, 17, 11, 16, 15, 123000))

    def test_parse_instant_offset(self) -> None:
        parsed = parse_instant("2026-08-17T19:16:15.123+08:00")
        self.assertEqual(parsed, _utc(2026, 8, 17, 11, 16, 15, 123000))

    def test_parse_instant_epoch_millis(self) -> None:
        parsed = parse_instant(1_755_400_575_123)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_parse_instant_empty(self) -> None:
        self.assertIsNone(parse_instant(None))
        self.assertIsNone(parse_instant(""))

    def test_windows_overlap(self) -> None:
        start_a = _utc(2026, 8, 17, 11, 16, 15, 0)
        end_a = _utc(2026, 8, 17, 11, 16, 16, 200000)
        start_b = _utc(2026, 8, 17, 11, 16, 15, 50000)
        end_b = _utc(2026, 8, 17, 11, 16, 16, 180000)
        self.assertTrue(execution_windows_overlap(start_a, end_a, start_b, end_b))

    def test_windows_contiguous_do_not_overlap(self) -> None:
        start_a = _utc(2026, 8, 17, 11, 16, 15, 0)
        end_a = _utc(2026, 8, 17, 11, 16, 16, 200000)
        start_b = end_a
        end_b = _utc(2026, 8, 17, 11, 16, 17, 400000)
        self.assertFalse(execution_windows_overlap(start_a, end_a, start_b, end_b))
        self.assertFalse(any_execution_windows_overlap([(start_a, end_a), (start_b, end_b)]))

    def test_evaluate_parallel_overlap_pass_on_windows(self) -> None:
        runs = [
            ExportCaseRun(
                username="Administrator",
                note="",
                expect_min_rows=1,
                task_id=1,
                detail={
                    "startedAt": "2026-08-17T11:16:15.000Z",
                    "finishedAt": "2026-08-17T11:16:16.200Z",
                },
            ),
            ExportCaseRun(
                username="north_chen",
                note="",
                expect_min_rows=1,
                task_id=2,
                detail={
                    "startedAt": "2026-08-17T11:16:15.050Z",
                    "finishedAt": "2026-08-17T11:16:16.180Z",
                },
            ),
        ]
        ok, detail = _evaluate_parallel_overlap(runs, max_running=0)
        self.assertTrue(ok)
        self.assertIn("overlap=True", detail)

    def test_evaluate_parallel_overlap_fail_when_serial(self) -> None:
        runs = [
            ExportCaseRun(
                username="Administrator",
                note="",
                expect_min_rows=1,
                task_id=1,
                detail={
                    "startedAt": "2026-08-17T11:16:15.000Z",
                    "finishedAt": "2026-08-17T11:16:16.200Z",
                },
            ),
            ExportCaseRun(
                username="north_chen",
                note="",
                expect_min_rows=1,
                task_id=2,
                detail={
                    "startedAt": "2026-08-17T11:16:16.200Z",
                    "finishedAt": "2026-08-17T11:16:17.400Z",
                },
            ),
        ]
        ok, detail = _evaluate_parallel_overlap(runs, max_running=1)
        self.assertFalse(ok)
        self.assertIn("全局串行", detail)

    def test_evaluate_parallel_overlap_pass_on_live_running(self) -> None:
        runs = [
            ExportCaseRun(
                username="Administrator",
                note="",
                expect_min_rows=1,
                task_id=1,
                detail={
                    "startedAt": "2026-08-17T11:16:15.000Z",
                    "finishedAt": "2026-08-17T11:16:16.200Z",
                },
            ),
            ExportCaseRun(
                username="north_chen",
                note="",
                expect_min_rows=1,
                task_id=2,
                detail={
                    "startedAt": "2026-08-17T11:16:16.200Z",
                    "finishedAt": "2026-08-17T11:16:17.400Z",
                },
            ),
        ]
        ok, _detail = _evaluate_parallel_overlap(runs, max_running=2)
        self.assertTrue(ok)
