"""登录后提交 example_order 异步导出：多账号并行建任务，轮询至终态并断言成功。"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
DEFAULT_POLL_INTERVAL_SECONDS = 0.5


@dataclass
class ExportCaseRun:
    """单账号一次导出探测的运行态。"""

    username: str
    note: str
    expect_min_rows: int | None
    token: str = ""
    scoped_count: int = 0
    task_id: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def run_example_order_export_probe(
    config: HarnessConfig,
    *,
    fixture_path: Path | None = None,
    base_url: str | None = None,
    username: str | None = None,
) -> int:
    """按 fixture 并行提交异步导出并断言成功与执行重叠；返回失败数（0=全过）。"""
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
        f"timeout={timeout_seconds}s poll={poll_interval}s parallel={len(cases) >= 2}"
    )
    try:
        runs = _prepare_runs(gateway, password, cases)
        _create_tasks_parallel(gateway, runs)
        max_running = _wait_all_terminal(gateway, runs, timeout_seconds, poll_interval)
    except Exception as exc:  # noqa: BLE001 — 探针汇总结果
        click.echo(f"[example-order-export] 请求失败: {exc}", err=True)
        return 1

    failures = 0
    for run in runs:
        ok, detail = _evaluate_completed_run(gateway, run)
        label = run.username
        note = run.note
        if ok:
            click.echo(f"  PASS  {label:16} {detail}  # {note}")
        else:
            failures += 1
            click.echo(f"  FAIL  {label:16} {detail}  # {note}", err=True)

    if failures == 0 and len(runs) >= 2:
        ok, detail = _evaluate_parallel_overlap(runs, max_running)
        if ok:
            click.echo(f"  PASS  {'parallel':16} {detail}")
        else:
            failures += 1
            click.echo(f"  FAIL  {'parallel':16} {detail}", err=True)

    if failures:
        click.echo(f"[example-order-export] {failures} 项失败", err=True)
    else:
        click.echo(f"[example-order-export] 全部通过 (cases={len(cases)})")
    return failures


def is_terminal_status(status: str | None) -> bool:
    """任务是否已进入终态。"""
    return status is not None and status.upper() in TERMINAL_STATUSES


def parse_instant(value: Any) -> datetime | None:
    """将任务详情中的时间字段解析为 UTC datetime。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).strip()
    if text.isdigit():
        return parse_instant(int(text))
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def execution_windows_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    """两段半开区间 [start, end) 是否相交；首尾相接不算重叠。"""
    return start_a < end_b and start_b < end_a


def any_execution_windows_overlap(windows: list[tuple[datetime, datetime]]) -> bool:
    """是否存在至少一对执行窗口重叠。"""
    for index, left in enumerate(windows):
        for right in windows[index + 1 :]:
            if execution_windows_overlap(*left, *right):
                return True
    return False


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


def _prepare_runs(gateway: str, password: str, cases: list[dict[str, Any]]) -> list[ExportCaseRun]:
    runs: list[ExportCaseRun] = []
    for case in cases:
        username = str(case["username"])
        token = _login(gateway, username, password)
        scoped_count = len(_fetch_orders(gateway, token))
        expect_min = case.get("expect_min_rows")
        runs.append(
            ExportCaseRun(
                username=username,
                note=str(case.get("note") or ""),
                expect_min_rows=int(expect_min) if expect_min is not None else None,
                token=token,
                scoped_count=scoped_count,
            )
        )
    return runs


def _create_tasks_parallel(gateway: str, runs: list[ExportCaseRun]) -> None:
    def create_one(run: ExportCaseRun) -> int:
        return _create_export_task(gateway, run.token)

    workers = max(1, len(runs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        task_ids = list(pool.map(create_one, runs))
    for run, task_id in zip(runs, task_ids, strict=True):
        run.task_id = task_id


def _wait_all_terminal(
    gateway: str,
    runs: list[ExportCaseRun],
    timeout_seconds: int,
    poll_interval: float,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    max_running = 0
    while time.monotonic() < deadline:
        running = 0
        all_terminal = True
        for run in runs:
            if run.task_id is None:
                raise RuntimeError(f"{run.username} 未拿到 taskId")
            run.detail = _fetch_task_detail(gateway, run.token, run.task_id)
            status = str(run.detail.get("status") or "")
            if status.upper() == "RUNNING":
                running += 1
            if not is_terminal_status(status):
                all_terminal = False
        max_running = max(max_running, running)
        if all_terminal:
            return max_running
        time.sleep(poll_interval)
    summaries = []
    for run in runs:
        status = (run.detail or {}).get("status")
        summaries.append(f"{run.username}#{run.task_id}={status}")
    raise TimeoutError(
        f"在 {timeout_seconds}s 内未全部终态，maxRunning={max_running} last=[{', '.join(summaries)}]"
    )


def _evaluate_completed_run(gateway: str, run: ExportCaseRun) -> tuple[bool, str]:
    detail = run.detail or {}
    status = str(detail.get("status") or "")
    processed = detail.get("processedRows")
    total = detail.get("totalRows")
    file_record_id = detail.get("fileRecordId")
    error_message = detail.get("errorMessage")
    summary = (
        f"taskId={run.task_id} status={status} processed={processed} "
        f"total={total} scoped={run.scoped_count} fileRecordId={file_record_id}"
    )
    if status != "SUCCESS":
        return False, f"{summary} error={error_message}"
    if file_record_id is None:
        return False, f"{summary} 缺少产物 fileRecordId"
    if processed is None or int(processed) != run.scoped_count:
        return False, f"{summary} processedRows 应等于列表可见行数 {run.scoped_count}"
    if run.expect_min_rows is not None and int(processed) < run.expect_min_rows:
        return False, f"{summary} processedRows < expect_min_rows={run.expect_min_rows}"
    try:
        download = _fetch_download_link(gateway, run.token, int(run.task_id or 0))
    except Exception as exc:  # noqa: BLE001
        return False, f"{summary} 下载链接失败: {exc}"
    download_url = download.get("url") or download.get("downloadUrl") or download.get("presignedUrl")
    if not download_url:
        return False, f"{summary} 下载链接为空: {download}"
    return True, summary


def _evaluate_parallel_overlap(runs: list[ExportCaseRun], max_running: int) -> tuple[bool, str]:
    windows: list[tuple[datetime, datetime]] = []
    labels: list[str] = []
    for run in runs:
        started = parse_instant((run.detail or {}).get("startedAt"))
        finished = parse_instant((run.detail or {}).get("finishedAt"))
        if started is None or finished is None:
            return False, (
                f"maxRunning={max_running} {run.username}#{run.task_id} 缺少 startedAt/finishedAt，"
                "无法判断是否并行"
            )
        if finished <= started:
            return False, (
                f"maxRunning={max_running} {run.username}#{run.task_id} "
                f"finishedAt={finished.isoformat()} 不晚于 startedAt={started.isoformat()}"
            )
        windows.append((started, finished))
        labels.append(
            f"{run.username}#{run.task_id}[{started.isoformat()}..{finished.isoformat()})"
        )
    overlapped = any_execution_windows_overlap(windows)
    summary = f"maxRunning={max_running} overlap={overlapped} " + " ".join(labels)
    if max_running >= 2 or overlapped:
        return True, summary
    return False, f"{summary} 执行窗口无重叠且未见同时 RUNNING（仍是全局串行）"


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
