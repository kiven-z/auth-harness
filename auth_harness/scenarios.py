"""YAML 场景执行器。"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pymysql
import redis
import yaml

from auth_harness.api import ApiClient
from auth_harness.config import HARNESS_ROOT, HarnessConfig
from auth_harness import db as db_mod
from auth_harness import redis_client as redis_mod
from auth_harness.oracle import OracleMode, reconcile_user
from auth_harness.reconcile import reconcile_many
from auth_harness.wait import wait_outbox_success

SCENARIOS_DIR = HARNESS_ROOT / "scenarios"


def run_scenario(config: HarnessConfig, scenario_path: Path) -> int:
    """执行单个 YAML 场景，失败返回 1。"""
    try:
        return _run_scenario_inner(config, scenario_path)
    except (AssertionError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"[scenario] FAILED: {exc}")
        return 1


def _run_scenario_inner(config: HarnessConfig, scenario_path: Path) -> int:
    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    name = data.get("name", scenario_path.stem)
    print(f"\n[scenario] === {name} ===")

    api = ApiClient(config)
    api.login()
    conn = db_mod.connect(config)
    rds = redis_mod.connect(config)

    try:
        for block_name in ("setup", "steps"):
            steps = data.get(block_name) or []
            for step in steps:
                _run_step(config, conn, rds, api, step)

        assert_block = data.get("assert")
        if assert_block:
            return _run_assert(config, conn, rds, api, assert_block)
        return 0
    finally:
        conn.close()
        rds.close()


def _run_step(
    config: HarnessConfig,
    conn: pymysql.connections.Connection,
    rds: redis.Redis,
    api: ApiClient,
    step: dict[str, Any],
) -> None:
    if not isinstance(step, dict) or len(step) != 1:
        raise ValueError(f"无效 step: {step}")

    action, params = next(iter(step.items()))
    params = params or {}

    if action == "put_dept_roles":
        api.put_dept_roles(int(params["dept_id"]), [int(x) for x in params["role_ids"]])
        print(f"[step] put_dept_roles dept={params['dept_id']} roles={params['role_ids']}")
        return

    if action == "put_user_roles":
        api.put_user_roles(int(params["user_id"]), [int(x) for x in params["role_ids"]])
        print(f"[step] put_user_roles user={params['user_id']} roles={params['role_ids']}")
        return

    if action == "post_role_permissions":
        api.post_role_permissions(
            int(params["role_id"]),
            [int(x) for x in params["permission_ids"]],
        )
        print(f"[step] post_role_permissions role={params['role_id']}")
        return

    if action == "wait_outbox":
        wait_outbox_success(
            conn,
            config,
            source_biz_id_contains=params.get("source_biz_id_contains"),
            timeout_sec=params.get("timeout_sec"),
        )
        return

    if action == "reconcile_user":
        user_id = int(params["user_id"])
        diffs = reconcile_user(config, conn, rds, api, user_id, OracleMode.API)
        if diffs:
            raise AssertionError("\n".join(diffs))
        return

    raise ValueError(f"未知 step 类型: {action}")


def _run_assert(
    config: HarnessConfig,
    conn: pymysql.connections.Connection,
    rds: redis.Redis,
    api: ApiClient,
    block: dict[str, Any],
) -> int:
    min_count = block.get("impacted_user_count_min")
    if min_count is not None:
        dept_id = int(block.get("dept_id") or config.test_ids.get("dept_fanout", 9000100001))
        actual = db_mod.count_dept_members(conn, dept_id)
        if actual < int(min_count):
            raise AssertionError(f"impacted_user_count_min 未满足: expected>={min_count}, actual={actual}")
        print(f"[assert] dept {dept_id} 成员数 {actual} >= {min_count}")

    for user_spec in block.get("users") or []:
        user_id = int(user_spec["user_id"])
        _assert_user_codes(config, conn, rds, api, user_id, user_spec)

    sample_spec = block.get("sample_from_dept")
    if sample_spec:
        dept_id = int(sample_spec["dept_id"])
        sample_size = int(sample_spec.get("sample_size", 5))
        members = db_mod.list_dept_user_ids(conn, dept_id)
        picked = sorted(random.sample(members, min(sample_size, len(members))))
        print(f"[assert] sample_from_dept dept={dept_id} users={picked}")
        for user_id in picked:
            _assert_user_codes(config, conn, rds, api, user_id, sample_spec)

    return 0


def _assert_user_codes(
    config: HarnessConfig,
    conn: pymysql.connections.Connection,
    rds: redis.Redis,
    api: ApiClient,
    user_id: int,
    spec: dict[str, Any],
) -> None:
    diffs = reconcile_user(config, conn, rds, api, user_id, OracleMode.API)
    if diffs:
        raise AssertionError("\n".join(diffs))

    oracle = api.get_effective_codes(user_id)
    roles = set(oracle.get("roles") or [])
    perms = set(oracle.get("permissions") or [])

    for code in spec.get("roles_contain") or []:
        if code not in roles:
            raise AssertionError(f"userId={user_id} 缺少角色 {code}")
    for code in spec.get("roles_not_contain") or []:
        if code in roles:
            raise AssertionError(f"userId={user_id} 不应包含角色 {code}")
    for code in spec.get("permissions_contain") or []:
        if code not in perms:
            raise AssertionError(f"userId={user_id} 缺少权限 {code}")
    for code in spec.get("permissions_not_contain") or []:
        if code in perms:
            raise AssertionError(f"userId={user_id} 不应包含权限 {code}")

    print(f"[assert] userId={user_id} OK")


def run_smoke(config: HarnessConfig) -> int:
    """依次运行三个关键场景。"""
    scenarios = [
        SCENARIOS_DIR / "grant-dept-remove.yml",
        SCENARIOS_DIR / "grant-dept-assign.yml",
        SCENARIOS_DIR / "role-permission-replace.yml",
    ]
    for path in scenarios:
        code = run_scenario(config, path)
        if code != 0:
            return code
    print("\n[smoke] 全部场景通过")
    return 0
