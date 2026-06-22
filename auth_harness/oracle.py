"""对比 DB oracle 与 Redis 画像。"""

from __future__ import annotations

from typing import Any

import pymysql
import redis

from auth_harness.api import ApiClient
from auth_harness.config import HarnessConfig
from auth_harness import db as db_mod
from auth_harness import redis_client as redis_mod


class OracleMode:
    API = "api"
    SQL = "sql"


def load_oracle(
    config: HarnessConfig,
    conn: pymysql.connections.Connection,
    api: ApiClient,
    user_id: int,
    mode: str = OracleMode.API,
) -> dict[str, Any]:
    """加载 DB 真值（优先 internal API，失败可回退 SQL）。"""
    if mode == OracleMode.SQL:
        return db_mod.query_db_oracle(conn, user_id)
    try:
        oracle = api.get_effective_codes(user_id)
        perm_version = db_mod.fetch_perm_version(conn, user_id)
        oracle["permVersion"] = perm_version
        return oracle
    except Exception as exc:
        print(f"[oracle] API 失败，回退 SQL: userId={user_id} ({exc})")
        return db_mod.query_db_oracle(conn, user_id)


def compare_profiles(oracle: dict[str, Any], redis_profile: dict[str, Any] | None) -> list[str]:
    """返回差异列表，空表示一致。"""
    diffs: list[str] = []
    if redis_profile is None:
        return [f"userId={oracle.get('userId')}: Redis 无画像"]

    redis_norm = redis_mod.normalize_profile(redis_profile)
    for field in ("roles", "permissions"):
        expected = sorted(oracle.get(field) or [])
        actual = sorted(redis_norm.get(field) or [])
        if expected != actual:
            diffs.append(
                f"userId={oracle.get('userId')}: {field} 不一致\n"
                f"  oracle: {expected}\n"
                f"  redis:  {actual}"
            )

    expected_pv = oracle.get("permVersion")
    actual_pv = redis_norm.get("permVersion")
    if expected_pv is not None and actual_pv is not None and int(expected_pv) != int(actual_pv):
        diffs.append(
            f"userId={oracle.get('userId')}: permVersion 不一致 "
            f"(oracle={expected_pv}, redis={actual_pv})"
        )
    return diffs


def reconcile_user(
    config: HarnessConfig,
    conn: pymysql.connections.Connection,
    rds: redis.Redis,
    api: ApiClient,
    user_id: int,
    mode: str = OracleMode.API,
) -> list[str]:
    oracle = load_oracle(config, conn, api, user_id, mode)
    redis_raw = redis_mod.load_profile(rds, user_id)
    return compare_profiles(oracle, redis_raw)
