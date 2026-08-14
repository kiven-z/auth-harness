"""内置步骤处理器。"""

from __future__ import annotations

import time
from typing import Any

from auth_harness.domain.oracle import OracleMode, reconcile_user
from auth_harness.domain.outbox_ops import CREATE_POST, require_known_prefix
from auth_harness.infrastructure import db as db_mod
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


@register("put_post_roles")
def put_post_roles(ctx: StepContext, params: dict[str, Any]) -> None:
    """岗位角色全量覆盖。"""
    post_id = int(params["post_id"])
    role_ids = [int(x) for x in params["role_ids"]]
    ctx.api.put_post_roles(post_id, role_ids)
    print(f"[step] put_post_roles post={post_id} roles={role_ids}")


@register("post_role_permissions")
def post_role_permissions(ctx: StepContext, params: dict[str, Any]) -> None:
    """角色权限全量分配。"""
    role_id = int(params["role_id"])
    permission_ids = [int(x) for x in params["permission_ids"]]
    ctx.api.post_role_permissions(role_id, permission_ids)
    print(f"[step] post_role_permissions role={role_id}")


@register("post_user_dept")
def post_user_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户加入部门。"""
    user_id = int(params["user_id"])
    dept_id = int(params["dept_id"])
    ctx.api.post_user_dept(
        user_id,
        dept_id,
        status=int(params.get("status", 1)),
        is_primary=bool(params.get("is_primary", True)),
        remark=params.get("remark"),
    )
    print(f"[step] post_user_dept user={user_id} dept={dept_id}")


@register("put_user_dept")
def put_user_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """更新用户部门关联（含换部门）。"""
    user_id = int(params["user_id"])
    relation_id = int(params["relation_id"])
    dept_id = int(params["dept_id"])
    ctx.api.put_user_dept(
        user_id,
        relation_id,
        dept_id,
        status=int(params.get("status", 1)),
        is_primary=bool(params.get("is_primary", True)),
        remark=params.get("remark"),
    )
    print(f"[step] put_user_dept user={user_id} relation={relation_id} dept={dept_id}")


@register("delete_user_dept")
def delete_user_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户移出部门。"""
    user_id = int(params["user_id"])
    relation_ids = [int(x) for x in params["relation_ids"]]
    ctx.api.delete_user_depts(user_id, relation_ids)
    print(f"[step] delete_user_dept user={user_id} relations={relation_ids}")


@register("post_user_post")
def post_user_post(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户加入岗位。"""
    user_id = int(params["user_id"])
    post_id = int(params["post_id"])
    ctx.api.post_user_post(
        user_id,
        post_id,
        status=int(params.get("status", 1)),
        is_primary=bool(params.get("is_primary", True)),
        remark=params.get("remark"),
    )
    print(f"[step] post_user_post user={user_id} post={post_id}")


@register("ensure_user_post")
def ensure_user_post(ctx: StepContext, params: dict[str, Any]) -> None:
    """确保用户岗位关联存在；新建时可选等待 outbox。"""
    user_id = int(params["user_id"])
    post_id = int(params["post_id"])
    row = db_mod.fetch_one(
        ctx.conn,
        """
        SELECT id FROM user_post
        WHERE user_id = %s AND post_id = %s AND status IN (1, 2)
        LIMIT 1
        """,
        (user_id, post_id),
    )
    if row:
        print(
            f"[step] ensure_user_post user={user_id} post={post_id} "
            f"already linked id={row['id']}"
        )
        return

    ctx.api.post_user_post(
        user_id,
        post_id,
        status=int(params.get("status", 1)),
        is_primary=bool(params.get("is_primary", True)),
        remark=params.get("remark"),
    )
    print(f"[step] ensure_user_post user={user_id} post={post_id} created")

    if params.get("wait_outbox"):
        wait_outbox_step(
            ctx,
            {
                "source_biz_id_contains": params.get("outbox_source_contains", CREATE_POST),
                "timeout_sec": params.get("timeout_sec", 60),
            },
        )


@register("delete_user_post")
def delete_user_post(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户离开岗位。"""
    user_id = int(params["user_id"])
    relation_ids = [int(x) for x in params["relation_ids"]]
    ctx.api.delete_user_posts(user_id, relation_ids)
    print(f"[step] delete_user_post user={user_id} relations={relation_ids}")


@register("update_dept_meta")
def update_dept_meta(ctx: StepContext, params: dict[str, Any]) -> None:
    """更新部门元数据（仅名称/备注等，或显式 parent/status）。"""
    dept_id = int(params["dept_id"])
    changes = {k: v for k, v in params.items() if k != "dept_id"}
    ctx.api.update_dept_meta(dept_id, **changes)
    print(f"[step] update_dept_meta dept={dept_id} changes={list(changes)}")


@register("move_dept")
def move_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """移动部门父节点。"""
    dept_id = int(params["dept_id"])
    parent_id = int(params["parent_id"])
    ctx.api.move_dept(dept_id, parent_id)
    print(f"[step] move_dept dept={dept_id} parent={parent_id}")


@register("update_role_meta")
def update_role_meta(ctx: StepContext, params: dict[str, Any]) -> None:
    """更新角色元数据。"""
    role_id = int(params["role_id"])
    changes = {k: v for k, v in params.items() if k != "role_id"}
    ctx.api.update_role_meta(role_id, **changes)
    print(f"[step] update_role_meta role={role_id} changes={list(changes)}")


@register("update_permission_meta")
def update_permission_meta(ctx: StepContext, params: dict[str, Any]) -> None:
    """更新权限元数据。"""
    permission_id = int(params["permission_id"])
    changes = {k: v for k, v in params.items() if k != "permission_id"}
    ctx.api.update_permission_meta(permission_id, **changes)
    print(f"[step] update_permission_meta permission={permission_id} changes={list(changes)}")


@register("update_post_meta")
def update_post_meta(ctx: StepContext, params: dict[str, Any]) -> None:
    """更新岗位元数据。"""
    post_id = int(params["post_id"])
    changes = {k: v for k, v in params.items() if k != "post_id"}
    ctx.api.update_post_meta(post_id, **changes)
    print(f"[step] update_post_meta post={post_id} changes={list(changes)}")


@register("batch_update_user_status")
def batch_update_user_status(ctx: StepContext, params: dict[str, Any]) -> None:
    """批量更新用户状态。"""
    user_ids = [int(x) for x in params["user_ids"]]
    status = int(params["status"])
    ctx.api.batch_update_user_status(user_ids, status)
    print(f"[step] batch_update_user_status users={user_ids} status={status}")


@register("delete_users")
def delete_users(ctx: StepContext, params: dict[str, Any]) -> None:
    """批量逻辑删除用户。"""
    user_ids = [int(x) for x in params["user_ids"]]
    ctx.api.delete_users(user_ids)
    print(f"[step] delete_users users={user_ids}")


@register("wait_outbox")
def wait_outbox_step(ctx: StepContext, params: dict[str, Any]) -> None:
    """轮询 outbox 直至 SUCCESS。"""
    source_contains = require_known_prefix(params.get("source_biz_id_contains"))
    cursor = ctx.resolve_outbox_cursor(source_contains)
    if cursor is None:
        cursor = snapshot_outbox_cursor(ctx.conn)
    row = wait_outbox_success(
        ctx.conn,
        ctx.config,
        source_biz_id_contains=source_contains,
        timeout_sec=params.get("timeout_sec"),
        cursor=cursor,
    )
    ctx.last_outbox_row = row


@register("assert_no_outbox")
def assert_no_outbox(ctx: StepContext, params: dict[str, Any]) -> None:
    """断言指定时间窗内未产生新 outbox 行（负向用例）。"""
    source_contains = require_known_prefix(params.get("source_biz_id_contains"))
    cursor = ctx.resolve_outbox_cursor(source_contains)
    if cursor is None and ctx.previous_step_cursor is not None:
        cursor = ctx.previous_step_cursor
    if cursor is None:
        cursor = snapshot_outbox_cursor(ctx.conn)
    grace_sec = float(params.get("grace_sec", 2))
    time.sleep(grace_sec)
    row = db_mod.fetch_outbox_after_id(ctx.conn, cursor.min_id, source_contains)
    if row is not None:
        raise AssertionError(
            f"不应产生 outbox，但发现 id={row['id']} status={row.get('status')} "
            f"source={row.get('source_biz_id')}"
        )
    print(f"[step] assert_no_outbox OK (grace={grace_sec}s)")


@register("verify_subject_roles")
def verify_subject_roles(ctx: StepContext, params: dict[str, Any]) -> None:
    """校验 grant_table 主体角色与期望一致（在 wait_outbox 之后、用户断言之前）。"""
    subject_type = str(params["subject_type"]).upper()
    subject_id = int(params["subject_id"])
    expected = sorted(str(code) for code in params["role_codes"])
    actual = sorted(db_mod.query_subject_role_codes(ctx.conn, subject_type, subject_id))
    if actual != expected:
        raise AssertionError(
            f"grant_table {subject_type} {subject_id} 角色不一致\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}"
        )
    print(f"[step] verify_subject_roles {subject_type} {subject_id} OK roles={actual}")


@register("prepare_outbox_wait")
def prepare_outbox_wait(ctx: StepContext, params: dict[str, Any]) -> None:
    """在 API 变更前记录全局 outbox 游标（与 wait_outbox 配对）。"""
    source_contains = require_known_prefix(params.get("source_biz_id_contains"))
    cursor = snapshot_outbox_cursor(ctx.conn)
    ctx.remember_outbox_cursor(source_contains, cursor)
    print(f"[step] prepare_outbox_wait cursor min_id={cursor.min_id} filter={source_contains!r}")


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
