"""Redis 读取 auth:security:user:perm:{userId} 画像。"""

from __future__ import annotations

import json
from typing import Any

import redis

from auth_harness.config import HarnessConfig

PERM_KEY_PREFIX = "auth:security:user:perm:"
HARNESS_PERM_KEY_PATTERN = f"{PERM_KEY_PREFIX}9001*"


def connect(config: HarnessConfig) -> redis.Redis:
    """创建 Redis 客户端。"""
    rconf = config.redis
    return redis.Redis(
        host=rconf["host"],
        port=int(rconf.get("port", 6379)),
        db=int(rconf.get("db", 0)),
        password=rconf.get("password") or None,
        decode_responses=True,
    )


def delete_harness_profiles(client: redis.Redis) -> int:
    """删除 9001* harness 用户的 Redis 画像（SQL seed 不会刷新缓存）。"""
    keys = list(client.scan_iter(match=HARNESS_PERM_KEY_PATTERN, count=500))
    if not keys:
        return 0
    return int(client.delete(*keys))


def flush_harness_profiles(config: HarnessConfig) -> int:
    """连接 Redis 并清理 harness 画像，返回删除 key 数。"""
    client = connect(config)
    try:
        deleted = delete_harness_profiles(client)
        print(f"[redis] 已删除 harness 画像 {deleted} 个 ({HARNESS_PERM_KEY_PATTERN})")
        return deleted
    finally:
        client.close()


def load_profile(client: redis.Redis, user_id: int) -> dict[str, Any] | None:
    """读取 Redis 中的 AuthProfile JSON。"""
    raw = client.get(f"{PERM_KEY_PREFIX}{user_id}")
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return _unwrap_profile_payload(json.loads(raw))
    if isinstance(raw, dict):
        return _unwrap_profile_payload(raw)
    return None


def _unwrap_profile_payload(payload: Any) -> dict[str, Any]:
    """兼容 GenericJackson 类型包装：[className, {...}] 或带 @class 的对象。"""
    if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[1], dict):
        return payload[1]
    if isinstance(payload, dict):
        return payload
    raise TypeError(f"无法解析 AuthProfile Redis 载荷: {type(payload).__name__}")


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """统一字段名便于对比。"""
    roles = sorted(_unwrap_typed_list(profile.get("roles")))
    permissions = sorted(_unwrap_typed_list(profile.get("permissions")))
    dept_scope = profile.get("deptScope") or profile.get("dept_scope")
    if isinstance(dept_scope, list) and len(dept_scope) == 2 and isinstance(dept_scope[1], dict):
        dept_scope = dept_scope[1]
    return {
        "userId": profile.get("userId") or profile.get("user_id"),
        "roles": roles,
        "permissions": permissions,
        "permVersion": profile.get("permVersion") or profile.get("perm_version"),
        "deptScope": dept_scope,
    }


def _unwrap_typed_list(value: Any) -> list[Any]:
    """兼容 GenericJackson 列表包装：[ListClass, [...]]。"""
    if value is None:
        return []
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], list):
        return list(value[1])
    if isinstance(value, list):
        return list(value)
    return []
