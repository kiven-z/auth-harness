"""Redis 读取 auth:security:user:perm:{userId} 画像。"""

from __future__ import annotations

import json
from typing import Any

import redis

from auth_harness.config import HarnessConfig

PERM_KEY_PREFIX = "auth:security:user:perm:"


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


def load_profile(client: redis.Redis, user_id: int) -> dict[str, Any] | None:
    """读取 Redis 中的 AuthProfile JSON。"""
    raw = client.get(f"{PERM_KEY_PREFIX}{user_id}")
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """统一字段名便于对比。"""
    roles = sorted(profile.get("roles") or [])
    permissions = sorted(profile.get("permissions") or [])
    dept_scope = profile.get("deptScope") or profile.get("dept_scope")
    return {
        "userId": profile.get("userId") or profile.get("user_id"),
        "roles": roles,
        "permissions": permissions,
        "permVersion": profile.get("permVersion") or profile.get("perm_version"),
        "deptScope": dept_scope,
    }
