"""批量 reconcile：DB oracle vs Redis。"""

from __future__ import annotations

import random
import time

import pymysql
import redis

from auth_harness.api import ApiClient
from auth_harness.config import HarnessConfig
from auth_harness import db as db_mod
from auth_harness import redis_client as redis_mod
from auth_harness.oracle import OracleMode, reconcile_user


def reconcile_many(
    config: HarnessConfig,
    user_ids: list[int],
    *,
    oracle_mode: str = OracleMode.API,
    retry: bool = True,
) -> int:
    """
    对比多个用户，首个不一致即返回退出码 1。
    返回 0 表示全部一致。
    """
    if not user_ids:
        print("[reconcile] 无用户需要检查")
        return 0

    conn = db_mod.connect(config)
    rds = redis_mod.connect(config)
    api = ApiClient(config)
    api.login()

    max_attempts = int(config.wait["reconcile_max_attempts"]) if retry else 1
    retry_sec = config.wait["reconcile_retry_sec"]

    try:
        for user_id in user_ids:
            diffs: list[str] = []
            for attempt in range(1, max_attempts + 1):
                diffs = reconcile_user(config, conn, rds, api, user_id, oracle_mode)
                if not diffs:
                    print(f"[reconcile] OK userId={user_id}")
                    break
                if attempt < max_attempts:
                    print(
                        f"[reconcile] userId={user_id} 第 {attempt} 次不一致，"
                        f"{retry_sec}s 后重试…"
                    )
                    time.sleep(retry_sec)
            if diffs:
                for line in diffs:
                    print(f"[reconcile] MISMATCH {line}")
                return 1
        return 0
    finally:
        conn.close()
        rds.close()


def resolve_user_ids(
    config: HarnessConfig,
    *,
    user_id: int | None,
    dept_code: str | None,
    sample: int | None,
) -> list[int]:
    """解析 reconcile 目标用户列表。"""
    conn = db_mod.connect(config)
    try:
        ids_cfg = config.test_ids
        if user_id is not None:
            return [user_id]
        if dept_code:
            dept_row = db_mod.fetch_one(
                conn,
                "SELECT id FROM sys_dept WHERE dept_code = %s AND is_deleted = 0",
                (dept_code,),
            )
            if not dept_row:
                raise ValueError(f"未找到部门 dept_code={dept_code}")
            members = db_mod.list_dept_user_ids(conn, int(dept_row["id"]))
            return _sample(members, sample)
        id_min = ids_cfg.get("id_min", 9001000001)
        id_max = ids_cfg.get("id_max", 9001001000)
        candidates = db_mod.list_active_users_in_range(conn, id_min, id_max)
        return _sample(candidates, sample or 10)
    finally:
        conn.close()


def _sample(items: list[int], sample: int | None) -> list[int]:
    if sample is None or sample >= len(items):
        return items
    if sample <= 0:
        return []
    return sorted(random.sample(items, sample))
