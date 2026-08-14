"""Outbox source_biz_id 操作前缀，与后端 AuthorizationInvalidationSourceBizIds.of(operation) 对齐。

格式：operation:xxxxxxxx（8 位短 UUID）。场景过滤只用「operation:」，禁止再拼业务 ID。
"""

from __future__ import annotations

REPLACE_ROLES = "replace-roles:"
ASSIGN_PERMISSIONS = "assign-permissions:"
CREATE_DEPT = "create-dept:"
UPDATE_DEPT = "update-dept:"
DELETE_DEPT = "delete-dept:"
CLEAR_DEPT = "clear-dept:"
CREATE_POST = "create-post:"
UPDATE_POST = "update-post:"
DELETE_POST = "delete-post:"
CLEAR_POST = "clear-post:"
MOVE = "move:"
UPDATE = "update:"
DELETE = "delete:"

KNOWN_PREFIXES = frozenset(
    {
        REPLACE_ROLES,
        ASSIGN_PERMISSIONS,
        CREATE_DEPT,
        UPDATE_DEPT,
        DELETE_DEPT,
        CLEAR_DEPT,
        CREATE_POST,
        UPDATE_POST,
        DELETE_POST,
        CLEAR_POST,
        MOVE,
        UPDATE,
        DELETE,
    }
)


def require_known_prefix(value: str | None) -> str | None:
    """校验过滤串是已知 operation 前缀；未知或带业务 ID 时立刻失败。"""
    if value is None:
        return None
    if value not in KNOWN_PREFIXES:
        known = ", ".join(sorted(KNOWN_PREFIXES))
        raise ValueError(
            f"未知 outbox 过滤 {value!r}。须为后端 operation 前缀之一（operation:）：{known}"
        )
    return value
