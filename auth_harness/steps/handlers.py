"""内置步骤处理器。"""

from __future__ import annotations

from typing import Any

from auth_harness.domain.oracle import OracleMode, reconcile_user
from auth_harness.steps.context import StepContext
from auth_harness.steps.registry import DEFAULT_REGISTRY
from auth_harness.wait.outbox import snapshot_outbox_cursor, wait_outbox_success

register = DEFAULT_REGISTRY.register


@register("put_dept_roles")
def put_dept_roles(ctx: StepContext, params: dict[str, Any]) -> None:
    """部门角色全量覆盖。"""
    dept_id = int(params["dept_id"])
    role_ids = [int(x) for x in params["role_ids"]]
    ctx.api.put_dept_roles(dept_id, role_ids)
    print(f"[step] put_dept_roles dept={dept_id} roles={role_ids}")


@register("put_user_roles")
def put_user_roles(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户直连角色全量覆盖。"""
    user_id = int(params["user_id"])
    role_ids = [int(x) for x in params["role_ids"]]
    ctx.api.put_user_roles(user_id, role_ids)
    print(f"[step] put_user_roles user={user_id} roles={role_ids}")


@register("post_role_permissions")
def post_role_permissions(ctx: StepContext, params: dict[str, Any]) -> None:
    """角色权限全量分配。"""
    role_id = int(params["role_id"])
    permission_ids = [int(x) for x in params["permission_ids"]]
    ctx.api.post_role_permissions(role_id, permission_ids)
    print(f"[step] post_role_permissions role={role_id}")


@register("wait_outbox")
def wait_outbox_step(ctx: StepContext, params: dict[str, Any]) -> None:
    """轮询 outbox 直至 SUCCESS。"""
    source_contains = params.get("source_biz_id_contains")
    cursor = ctx.resolve_outbox_cursor(source_contains)
    if cursor is None:
        cursor = snapshot_outbox_cursor(ctx.conn, source_contains)
    row = wait_outbox_success(
        ctx.conn,
        ctx.config,
        source_biz_id_contains=source_contains,
        timeout_sec=params.get("timeout_sec"),
        cursor=cursor,
    )
    ctx.last_outbox_row = row


@register("prepare_outbox_wait")
def prepare_outbox_wait(ctx: StepContext, params: dict[str, Any]) -> None:
    """在 API 变更前记录 outbox 游标（可与 wait_outbox 配对，避免陈旧 SUCCESS）。"""
    source_contains = params.get("source_biz_id_contains")
    cursor = snapshot_outbox_cursor(ctx.conn, source_contains)
    ctx.remember_outbox_cursor(source_contains, cursor)
    print(f"[step] prepare_outbox_wait cursor min_id={cursor.min_id}")


@register("reconcile_user")
def reconcile_user_step(ctx: StepContext, params: dict[str, Any]) -> None:
    """单用户 oracle vs Redis 对账（无重试）。"""
    user_id = int(params["user_id"])
    diffs = reconcile_user(ctx.config, ctx.conn, ctx.rds, ctx.api, user_id, OracleMode.API)
    if diffs:
        raise AssertionError("\n".join(diffs))


@register("assert")
def assert_step(ctx: StepContext, params: dict[str, Any]) -> None:
    """场景断言块（含 reconcile 重试）。"""
    from auth_harness.assertions.runner import AssertRunner

    AssertRunner(ctx).run(params)
