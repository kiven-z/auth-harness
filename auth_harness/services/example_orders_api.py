"""GET /api/example/orders 分页拉取（开发期演示单）。"""

from __future__ import annotations

from typing import Any

import requests

SUCCESS_CODE = 0
ORDERS_PATH = "/api/example/orders"
DEFAULT_PAGE_SIZE = 100


def fetch_all_example_orders(
    gateway: str,
    token: str,
    *,
    timeout: float = 30,
) -> list[Any]:
    """分页拉取当前用户可见的全部演示单行。"""
    gateway_base = gateway.rstrip("/")
    rows: list[Any] = []
    page_index = 1
    total = 0

    while True:
        page_rows, page_total = fetch_example_order_page(
            gateway_base,
            token,
            page_index=page_index,
            page_size=DEFAULT_PAGE_SIZE,
            timeout=timeout,
        )
        if page_index == 1:
            total = page_total
        rows.extend(page_rows)
        if len(rows) >= total or not page_rows:
            break
        page_index += 1

    return rows


def fetch_example_order_page(
    gateway: str,
    token: str,
    *,
    page_index: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    query: dict[str, Any] | None = None,
    timeout: float = 30,
) -> tuple[list[Any], int]:
    """拉取单页演示单，返回 (list, total)。"""
    params: dict[str, Any] = {
        "pageIndex": page_index,
        "pageSize": page_size,
    }
    if query:
        params.update(query)

    url = f"{gateway.rstrip('/')}{ORDERS_PATH}"
    response = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != SUCCESS_CODE:
        raise RuntimeError(f"{ORDERS_PATH} 失败: {body}")

    data = body.get("data")
    if data is None:
        return [], 0
    if not isinstance(data, dict):
        raise RuntimeError(f"{ORDERS_PATH} 返回非分页对象: {body}")

    rows = data.get("list")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise RuntimeError(f"{ORDERS_PATH} list 非数组: {body}")

    total_raw = data.get("total")
    total = int(total_raw) if total_raw is not None else len(rows)
    return rows, total
