"""启动前连通性检查：MySQL、Redis、服务、管理账号。"""

from __future__ import annotations

import requests

from auth_harness.config import HarnessConfig
from auth_harness.infrastructure.api import ApiClient
from auth_harness.infrastructure import db as db_mod
from auth_harness.infrastructure import redis_client as redis_mod

_SERVICE_OK_STATUS_CODES = frozenset({200, 401, 403})


def run_preflight(config: HarnessConfig) -> int:
    """检查依赖是否就绪，全部通过返回 0。"""
    failures: list[str] = []

    _check_mysql(config, failures)
    _check_redis(config, failures)
    _check_service("auth", config.auth_base_url, failures)
    _check_service("system", config.system_base_url, failures)
    _check_admin_login(config, failures)

    if failures:
        for message in failures:
            print(f"[preflight] FAIL: {message}")
        return 1

    print("[preflight] 全部通过")
    return 0


def _check_mysql(config: HarnessConfig, failures: list[str]) -> None:
    try:
        conn = db_mod.connect(config)
        try:
            row = db_mod.fetch_one(conn, "SELECT 1 AS ok")
            if not row:
                raise RuntimeError("查询无结果")
        finally:
            conn.close()
        print(f"[preflight] MySQL ({config.mysql['database']}): OK")
    except Exception as exc:
        failures.append(f"MySQL: {exc}")


def _check_redis(config: HarnessConfig, failures: list[str]) -> None:
    try:
        client = redis_mod.connect(config)
        client.ping()
        db_index = config.redis.get("db", 0)
        print(f"[preflight] Redis (db {db_index}): OK")
    except Exception as exc:
        failures.append(f"Redis: {exc}")


def _check_service(name: str, base_url: str, failures: list[str]) -> None:
    health_url = f"{base_url.rstrip('/')}/actuator/health"
    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code in _SERVICE_OK_STATUS_CODES:
            print(f"[preflight] {name} service: OK")
            return
        failures.append(f"{name} service: {health_url} 返回 {response.status_code}")
    except requests.RequestException as exc:
        failures.append(f"{name} service: 无法访问 {health_url} ({exc})")


def _check_admin_login(config: HarnessConfig, failures: list[str]) -> None:
    try:
        ApiClient(config).login()
        print(f"[preflight] Admin login ({config.admin['username']}): OK")
    except Exception as exc:
        failures.append(f"Admin login: {exc}")
