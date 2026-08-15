"""内置步骤处理器。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from auth_harness.domain.oracle import OracleMode, reconcile_user
from auth_harness.domain.outbox_ops import (
    CREATE_DEPT,
    CREATE_POST,
    DELETE_DEPT,
    DELETE_POST,
    MOVE,
    UPDATE_DEPT,
    require_known_prefix,
)
from auth_harness.infrastructure import db as db_mod
from auth_harness.steps.context import StepContext
from auth_harness.steps.registry import DEFAULT_REGISTRY
from auth_harness.wait.outbox import snapshot_outbox_cursor, wait_outbox_success

register = DEFAULT_REGISTRY.register


def _mutate_and_wait(
    ctx: StepContext,
    mutate: Callable[[], None],
    prefix: str,
    *,
    wait: bool,
    timeout: float | int | None = 60,
) -> None:
    """变更前快照游标；仅在确有写入时等待 outbox。"""
    cursor = snapshot_outbox_cursor(ctx.conn)
    mutate()
    if not wait:
        return
    ctx.last_outbox_row = wait_outbox_success(
        ctx.conn,
        ctx.config,
        source_biz_id_contains=require_known_prefix(prefix),
        timeout_sec=timeout,
        cursor=cursor,
    )


def _user_dept_relation_ids(ctx: StepContext, params: dict[str, Any]) -> list[int]:
    if params.get("relation_ids"):
        return [int(x) for x in params["relation_ids"]]
    if params.get("dept_id") is None:
        return []
    found = db_mod.find_user_dept_id(ctx.conn, int(params["user_id"]), int(params["dept_id"]))
    return [found] if found is not None else []


def _user_post_relation_ids(ctx: StepContext, params: dict[str, Any]) -> list[int]:
    if params.get("relation_ids"):
        return [int(x) for x in params["relation_ids"]]
    if params.get("post_id") is None:
        return []
    found = db_mod.find_user_post_id(ctx.conn, int(params["user_id"]), int(params["post_id"]))
    return [found] if found is not None else []


def _resolve_put_user_dept_relation_id(ctx: StepContext, params: dict[str, Any]) -> int:
    if params.get("relation_id") is not None:
        return int(params["relation_id"])
    user_id = int(params["user_id"])
    from_dept_id = int(params.get("from_dept_id") or 0)
    if from_dept_id:
        found = db_mod.find_user_dept_id(ctx.conn, user_id, from_dept_id)
        if found is not None:
            return found
    other = db_mod.find_any_user_dept(ctx.conn, user_id)
    if other:
        return int(other["id"])
    raise RuntimeError(f"用户 {user_id} 没有可更新的部门关联")


def _relation_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_primary": bool(params.get("is_primary", True)),
        "remark": params.get("remark"),
    }


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
    ctx.api.post_user_dept(user_id, dept_id, **_relation_kwargs(params))
    print(f"[step] post_user_dept user={user_id} dept={dept_id}")


@register("put_user_dept")
def put_user_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """更新用户部门关联（含换部门）。"""
    user_id = int(params["user_id"])
    dept_id = int(params["dept_id"])
    relation_id = _resolve_put_user_dept_relation_id(ctx, params)
    ctx.api.put_user_dept(user_id, relation_id, dept_id, **_relation_kwargs(params))
    print(f"[step] put_user_dept user={user_id} relation={relation_id} dept={dept_id}")


@register("delete_user_dept")
def delete_user_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户移出部门。无关联时跳过（避免 wait 空转）。"""
    user_id = int(params["user_id"])
    relation_ids = _user_dept_relation_ids(ctx, params)
    if not relation_ids:
        print(f"[step] delete_user_dept user={user_id} skip（无匹配关联）")
        return
    _mutate_and_wait(
        ctx,
        lambda: ctx.api.delete_user_depts(user_id, relation_ids),
        DELETE_DEPT,
        wait=bool(params.get("wait_outbox")),
        timeout=params.get("timeout_sec", 60),
    )
    print(f"[step] delete_user_dept user={user_id} relations={relation_ids}")


@register("ensure_user_dept")
def ensure_user_dept(ctx: StepContext, params: dict[str, Any]) -> None:
    """确保用户在指定部门；已在则跳过，在其他部门则改挂。"""
    user_id = int(params["user_id"])
    dept_id = int(params["dept_id"])
    wait = bool(params.get("wait_outbox"))
    timeout = params.get("timeout_sec", 60)
    kwargs = _relation_kwargs(params)
    existing = db_mod.find_user_dept_id(ctx.conn, user_id, dept_id)
    if existing is not None:
        print(f"[step] ensure_user_dept user={user_id} dept={dept_id} already linked id={existing}")
        return
    other = db_mod.find_any_user_dept(ctx.conn, user_id)
    if other:
        _mutate_and_wait(
            ctx,
            lambda: ctx.api.put_user_dept(user_id, int(other["id"]), dept_id, **kwargs),
            UPDATE_DEPT,
            wait=wait,
            timeout=timeout,
        )
        print(f"[step] ensure_user_dept user={user_id} moved relation={other['id']} -> dept={dept_id}")
        return
    _mutate_and_wait(
        ctx,
        lambda: ctx.api.post_user_dept(user_id, dept_id, **kwargs),
        CREATE_DEPT,
        wait=wait,
        timeout=timeout,
    )
    print(f"[step] ensure_user_dept user={user_id} dept={dept_id} created")


@register("post_user_post")
def post_user_post(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户加入岗位。"""
    user_id = int(params["user_id"])
    post_id = int(params["post_id"])
    ctx.api.post_user_post(user_id, post_id, **_relation_kwargs(params))
    print(f"[step] post_user_post user={user_id} post={post_id}")


@register("ensure_user_post")
def ensure_user_post(ctx: StepContext, params: dict[str, Any]) -> None:
    """确保用户岗位关联存在；新建时可选等待 outbox。"""
    user_id = int(params["user_id"])
    post_id = int(params["post_id"])
    existing = db_mod.find_user_post_id(ctx.conn, user_id, post_id)
    if existing is not None:
        print(f"[step] ensure_user_post user={user_id} post={post_id} already linked id={existing}")
        return
    _mutate_and_wait(
        ctx,
        lambda: ctx.api.post_user_post(user_id, post_id, **_relation_kwargs(params)),
        params.get("outbox_source_contains", CREATE_POST),
        wait=bool(params.get("wait_outbox")),
        timeout=params.get("timeout_sec", 60),
    )
    print(f"[step] ensure_user_post user={user_id} post={post_id} created")


@register("delete_user_post")
def delete_user_post(ctx: StepContext, params: dict[str, Any]) -> None:
    """用户离开岗位。无关联时跳过。"""
    user_id = int(params["user_id"])
    relation_ids = _user_post_relation_ids(ctx, params)
    if not relation_ids:
        print(f"[step] delete_user_post user={user_id} skip（无匹配关联）")
        return
    _mutate_and_wait(
        ctx,
        lambda: ctx.api.delete_user_posts(user_id, relation_ids),
        DELETE_POST,
        wait=bool(params.get("wait_outbox")),
        timeout=params.get("timeout_sec", 60),
    )
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


@register("ensure_dept_parent")
def ensure_dept_parent(ctx: StepContext, params: dict[str, Any]) -> None:
    """确保部门父节点；已是目标则跳过。"""
    dept_id = int(params["dept_id"])
    parent_id = int(params["parent_id"])
    detail = ctx.api.get_dept_detail(dept_id)
    current = int(detail.get("parentId") or 0)
    if current == parent_id:
        print(f"[step] ensure_dept_parent dept={dept_id} already parent={parent_id}")
        return
    _mutate_and_wait(
        ctx,
        lambda: ctx.api.move_dept(dept_id, parent_id),
        MOVE,
        wait=bool(params.get("wait_outbox")),
        timeout=params.get("timeout_sec", 60),
    )
    print(f"[step] ensure_dept_parent dept={dept_id} parent {current} -> {parent_id}")


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
    """轮询 outbox 直至 SUCCESS（游标取上一步入口快照）。"""
    source_contains = require_known_prefix(params.get("source_biz_id_contains"))
    cursor = ctx.previous_step_cursor or snapshot_outbox_cursor(ctx.conn)
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
    cursor = ctx.previous_step_cursor or snapshot_outbox_cursor(ctx.conn)
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
