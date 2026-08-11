"""登录后提交 example_order 异步导出，轮询至终态并断言成功。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import click
import requests
import yaml

from auth_harness.config import HarnessConfig
from auth_harness.domain.paths import HARNESS_ROOT

SUCCESS_CODE = 0
DEFAULT_FIXTURE = HARNESS_ROOT / "fixtures" / "example_order_export_cases.yml"
DEFAULT_GATEWAY = "http://127.0.0.1:8080"
ORDERS_PATH = "/api/example/orders"
EXPORT_ASYNC_PATH = "/api/example/orders/export/async"
TASK_DETAIL_PATH = "/api/system/me/file-export-tasks/{task_id}"
DOWNLOAD_LINK_PATH = "/api/system/me/file-export-tasks/{task_id}/download-link"

TERMINAL_STATUSES = frozenset({"SUCCESS", "FAILED", "CANCELLED", "EXPIRED"})
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


def run_example_order_export_probe(
    config: HarnessConfig,
    *,
    fixture_path: Path | None = None,
    base_url: str | None = None,
    username: str | None = None,
) -> int:
    """按 fixture 提交异步导出并断言成功；返回失败数（0=全过）。"""
    fixture = _load_fixture(fixture_path or DEFAULT_FIXTURE)
    gateway = (base_url or _gateway_from_config(config)).rstrip("/")
    password = str(fixture.get("password") or config.admin.get("password") or "Admin@123456")
    timeout_seconds = int(fixture.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    poll_interval = float(fixture.get("poll_interval_seconds") or DEFAULT_POLL_INTERVAL_SECONDS)
    cases = list(fixture.get("cases") or [])
    if username:
        cases = [c for c in cases if c.get("username") == username]
        if not cases:
            click.echo(f"[example-order-export] fixture 中无账号: {username}", err=True)
            return 1

    click.echo(
        f"[example-order-export] gateway={gateway} cases={len(cases)} "
        f"timeout={timeout_seconds}s poll={poll_interval}s"
    )
    failures = 0
    for case in cases:
        ok, detail = _probe_one(gateway, password, case, timeout_seconds, poll_interval)
        label = case.get("username")
        note = case.get("note") or ""
        if ok:
            click.echo(f"  PASS  {label:16} {detail}  # {note}")
        else:
            failures += 1
            click.echo(f"  FAIL  {label:16} {detail}  # {note}", err=True)

    if failures:
        click.echo(f"[example-order-export] {failures}/{len(cases)} 失败", err=True)
    else:
        click.echo(f"[example-order-export] 全部通过 ({len(cases)})")
    return failures


def is_terminal_status(status: str | None) -> bool:
    """任务是否已进入终态。"""
    return status is not None and status.upper() in TERMINAL_STATUSES


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


def _probe_one(
    gateway: str,
    password: str,
    case: dict[str, Any],
    timeout_seconds: int,
    poll_interval: float,
) -> tuple[bool, str]:
    username = str(case["username"])
    expect_min_rows = case.get("expect_min_rows")
    try:
        token = _login(gateway, username, password)
        scoped_count = len(_fetch_orders(gateway, token))
        task_id = _create_export_task(gateway, token)
        detail = _wait_terminal(gateway, token, task_id, timeout_seconds, poll_interval)
    except Exception as exc:  # noqa: BLE001 — 探针汇总全部账号结果
        return False, f"请求失败: {exc}"

    status = str(detail.get("status") or "")
    processed = detail.get("processedRows")
    total = detail.get("totalRows")
    file_record_id = detail.get("fileRecordId")
    error_message = detail.get("errorMessage")
    summary = (
        f"taskId={task_id} status={status} processed={processed} "
        f"total={total} scoped={scoped_count} fileRecordId={file_record_id}"
    )

    if status != "SUCCESS":
        return False, f"{summary} error={error_message}"
    if file_record_id is None:
        return False, f"{summary} 缺少产物 fileRecordId"
    if processed is None or int(processed) != scoped_count:
        return False, f"{summary} processedRows 应等于列表可见行数 {scoped_count}"
    if expect_min_rows is not None and int(processed) < int(expect_min_rows):
        return False, f"{summary} processedRows < expect_min_rows={expect_min_rows}"

    try:
        download = _fetch_download_link(gateway, token, task_id)
    except Exception as exc:  # noqa: BLE001
        return False, f"{summary} 下载链接失败: {exc}"
    download_url = download.get("url") or download.get("downloadUrl") or download.get("presignedUrl")
    if not download_url:
        return False, f"{summary} 下载链接为空: {download}"
    return True, summary


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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fetch_orders(gateway: str, token: str) -> list[Any]:
    url = f"{gateway}{ORDERS_PATH}"
    response = requests.get(url, headers=_auth_headers(token), timeout=30)
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


def _create_export_task(gateway: str, token: str) -> int:
    request_id = f"harness-example-order-export-{uuid.uuid4().hex}"
    url = f"{gateway}{EXPORT_ASYNC_PATH}"
    response = requests.post(
        url,
        params={"requestId": request_id},
        json={},
        headers=_auth_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != SUCCESS_CODE:
        raise RuntimeError(f"{EXPORT_ASYNC_PATH} 失败: {body}")
    data = body.get("data") or {}
    task_id = data.get("taskId")
    if task_id is None:
        raise RuntimeError(f"创建导出无 taskId: {body}")
    return int(task_id)


def _wait_terminal(
    gateway: str,
    token: str,
    task_id: int,
    timeout_seconds: int,
    poll_interval: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _fetch_task_detail(gateway, token, task_id)
        if is_terminal_status(str(last.get("status") or "")):
            return last
        time.sleep(poll_interval)
    raise TimeoutError(f"任务 {task_id} 在 {timeout_seconds}s 内未终态，最后状态={last}")


def _fetch_task_detail(gateway: str, token: str, task_id: int) -> dict[str, Any]:
    url = f"{gateway}{TASK_DETAIL_PATH.format(task_id=task_id)}"
    response = requests.get(url, headers=_auth_headers(token), timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("code") != SUCCESS_CODE:
        raise RuntimeError(f"任务详情失败: {body}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"任务详情非对象: {body}")
    return data


def _fetch_download_link(gateway: str, token: str, task_id: int) -> dict[str, Any]:
    url = f"{gateway}{DOWNLOAD_LINK_PATH.format(task_id=task_id)}"
    response = requests.get(url, headers=_auth_headers(token), timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get("code") != SUCCESS_CODE:
        raise RuntimeError(f"下载链接失败: {body}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"下载链接非对象: {body}")
    return data
