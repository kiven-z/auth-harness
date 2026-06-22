"""用户角色/权限码断言。"""

from __future__ import annotations

from typing import Any

from auth_harness.domain.oracle import OracleMode, reconcile_user
from auth_harness.steps.context import StepContext


def assert_user_codes(ctx: StepContext, user_id: int, spec: dict[str, Any]) -> None:
    """triple assert 的用户码部分：oracle/redis 一致 + 角色/权限包含关系。"""
    diffs = reconcile_user(ctx.config, ctx.conn, ctx.rds, ctx.api, user_id, OracleMode.API)
    if diffs:
        raise AssertionError("\n".join(diffs))

    oracle = ctx.api.get_effective_codes(user_id)
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
