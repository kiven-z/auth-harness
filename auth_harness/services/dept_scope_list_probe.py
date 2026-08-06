"""登录演示账号并断言 /api/example/orders 行级过滤结果。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import requests
import yaml

from auth_harness.config import HarnessConfig
from auth_harness.domain.paths import HARNESS_ROOT

SUCCESS_CODE = 0
DEFAULT_FIXTURE = HARNESS_ROOT / "fixtures" / "dept_scope_list_cases.yml"
DEFAULT_GATEWAY = "http://127.0.0.1:8080"
ORDERS_PATH = "/api/example/orders"


def run_dept_scope_list_probe(
    config: HarnessConfig,
    *,
    fixture_path: Path | None = None,
    base_url: str | None = None,
    username: str | None = None,
) -> int:
    """按 fixture 逐账号登录并断言订单 id 集合；返回失败数（0=全过）。"""
    fixture = _load_fixture(fixture_path or DEFAULT_FIXTURE)
    gateway = (base_url or _gateway_from_config(config)).rstrip("/")
    password = str(fixture.get("password") or config.admin.get("password") or "Admin@123456")
    cases = list(fixture.get("cases") or [])
    if username:
        cases = [c for c in cases if c.get("username") == username]
        if not cases:
            click.echo(f"[dept-scope-list] fixture 中无账号: {username}", err=True)
            return 1

    click.echo(f"[dept-scope-list] gateway={gateway} path={ORDERS_PATH} cases={len(cases)}")
    failures = 0
    for case in cases:
        ok, detail = _probe_one(gateway, password, case)
        label = case.get("username")
        note = case.get("note") or ""
        if ok:
            click.echo(f"  PASS  {label:16} {detail}  # {note}")
        else:
            failures += 1
            click.echo(f"  FAIL  {label:16} {detail}  # {note}", err=True)

    if failures:
        click.echo(f"[dept-scope-list] {failures}/{len(cases)} 失败", err=True)
    else:
        click.echo(f"[dept-scope-list] 全部通过 ({len(cases)})")
    return failures


def _gateway_from_config(config: HarnessConfig) -> str:
    urls = config.raw.get("urls") or {}
    return str(urls.get("gateway") or DEFAULT_GATEWAY)


def _load_fixture(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"fixture 不存在: {path}")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"无效 fixture: {path}")
    return raw


def _probe_one(gateway: str, password: str, case: dict[str, Any]) -> tuple[bool, str]:
    username = str(case["username"])
    expect_ids = {int(v) for v in (case.get("expected_ids") or [])}

    try:
        token = _login(gateway, username, password)
        rows = _fetch_orders(gateway, token)
    except Exception as exc:  # noqa: BLE001 — 探针要汇总全部账号结果
        return False, f"请求失败: {exc}"

    actual_ids = {_row_id(row) for row in rows}
    actual_ids.discard(None)
    summary = f"ids={sorted(actual_ids)}"
    if actual_ids != expect_ids:
        return False, f"ids actual={sorted(actual_ids)} expect={sorted(expect_ids)}"
    return True, summary


def _row_id(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    value = row.get("id")
    if value is None:
        return None
    return int(value)


def _login(gateway: str, username: str, password: str) -> str:
    url = f"{gateway}/api/auth/login/username"
    response = requests.post(
        url,
        json={"username": username, "password": password, "rememberMe": False},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != SUCCESS_CODE:
        raise RuntimeError(f"登录失败: {body}")
    token = (body.get("data") or {}).get("accessToken")
    if not token:
        raise RuntimeError(f"登录无 accessToken: {body}")
    return str(token)


def _fetch_orders(gateway: str, token: str) -> list[Any]:
    url = f"{gateway}{ORDERS_PATH}"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("code") != SUCCESS_CODE:
        raise RuntimeError(f"{ORDERS_PATH} 失败: {body}")
    data = body.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        raise RuntimeError(f"{ORDERS_PATH} 返回非列表: {body}")
    return data
