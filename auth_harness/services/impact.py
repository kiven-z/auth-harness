"""L1 影响面 CLI 逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from auth_harness.config import HarnessConfig
from auth_harness.domain.impact import compare_user_sets, resolve_impacted_user_ids
from auth_harness.domain.paths import IMPACT_FIXTURES_PATH
from auth_harness.infrastructure import db as db_mod


def load_impact_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """加载影响面 fixture 用例表。"""
    fixture_path = path or IMPACT_FIXTURES_PATH
    data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError(f"无效 fixture: {fixture_path}")
    return cases


def run_impact_suite(config: HarnessConfig, fixture_path: Path | None = None) -> int:
    """执行全部 L1 fixture 用例，失败返回 1。"""
    cases = load_impact_cases(fixture_path)
    conn = db_mod.connect(config)
    failed = 0
    try:
        for case in cases:
            case_id = case.get("id", "?")
            kind = case["kind"]
            subject_ids = [int(x) for x in case.get("subject_ids") or []]
            role_codes = [str(x) for x in case.get("role_codes") or []]
            actual = resolve_impacted_user_ids(
                conn,
                kind,
                subject_ids=subject_ids or None,
                role_codes=role_codes or None,
            )
            if not _assert_case(case, case_id, actual):
                failed += 1
    finally:
        conn.close()

    if failed:
        print(f"\n[impact] {failed}/{len(cases)} 用例失败")
        return 1
    print(f"\n[impact] 全部 {len(cases)} 用例通过")
    return 0


def _assert_case(case: dict[str, Any], case_id: str, actual: set[int]) -> bool:
    """单条 fixture 断言。"""
    if case.get("expected_count") is not None:
        expected_count = int(case["expected_count"])
        if len(actual) != expected_count:
            print(f"[impact] FAIL {case_id}: count expected={expected_count} actual={len(actual)}")
            return False
        print(f"[impact] OK {case_id}: count={len(actual)}")
        return True

    if case.get("expected_count_min") is not None:
        minimum = int(case["expected_count_min"])
        if len(actual) < minimum:
            print(f"[impact] FAIL {case_id}: count expected>={minimum} actual={len(actual)}")
            return False
        print(f"[impact] OK {case_id}: count={len(actual)} (>={minimum})")
        return True

    expected = {int(x) for x in case.get("expected_user_ids") or []}
    diffs = compare_user_sets(expected, actual)
    if diffs:
        print(f"[impact] FAIL {case_id}: " + "; ".join(diffs))
        return False
    print(f"[impact] OK {case_id}: {len(actual)} users")
    return True
