"""解析 / 生成 sys_permission seed SQL。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROW_PATTERN = re.compile(
    r"\((\d+),'([^']+)','((?:\\'|[^'])*)',(\d+),(\d+),"
    r"'([^']*)','([^']*)',(\d+),(\d+|NULL),(\d+),(?:'((?:\\'|[^'])*)'|NULL)\)"
)


@dataclass(frozen=True, order=True)
class SeedPermissionRow:
    """seed SQL 中的一行权限。"""

    permission_id: int
    permission_code: str
    permission_name: str
    order_num: int
    status: int = 1
    remark: str | None = None


def parse_seed_sql(path: Path) -> list[SeedPermissionRow]:
    """从 02-seed-sys-permission.sql 解析权限行。"""
    text = path.read_text(encoding="utf-8")
    rows: list[SeedPermissionRow] = []
    for match in ROW_PATTERN.finditer(text):
        remark = match.group(11)
        rows.append(
            SeedPermissionRow(
                permission_id=int(match.group(1)),
                permission_code=match.group(2),
                permission_name=match.group(3).replace("\\'", "'"),
                order_num=int(match.group(4)),
                status=int(match.group(5)),
                remark=None if remark is None else remark.replace("\\'", "'"),
            )
        )
    return rows


def seed_codes(rows: list[SeedPermissionRow]) -> set[str]:
    return {row.permission_code for row in rows}


def build_upsert_sql(
    entries: list[tuple[str, str, int]],
    *,
    remark: str = "synced from code",
    created_by: int = 1,
) -> str:
    """生成按 permission_code 幂等插入的 SQL（已存在则跳过名称）。"""
    if not entries:
        return "-- no missing permissions\n"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")
    lines = [
        "-- 仅插入缺失权限码；已存在的行不改名",
        "INSERT INTO sys_permission",
        "  (permission_code, permission_name, order_num, status,",
        "   created_at, updated_at, created_by, updated_by, version, remark)",
        "VALUES",
    ]
    value_sql: list[str] = []
    for code, name, order_num in entries:
        value_sql.append(
            "  ("
            f"'{_escape(code)}', '{_escape(name)}', {order_num}, 1, "
            f"'{now}', '{now}', {created_by}, {created_by}, 0, '{_escape(remark)}')"
        )
    lines.append(",\n".join(value_sql))
    lines.append(
        "ON DUPLICATE KEY UPDATE updated_at = updated_at;"
    )
    lines.append("")
    return "\n".join(lines)


def build_prune_sql(orphan_codes: list[str]) -> str:
    """生成删除 orphan 权限码的 SQL（依赖 FK CASCADE 清角色绑定）。"""
    if not orphan_codes:
        return "-- no orphan permissions to prune\n"
    codes_sql = ",\n  ".join(f"'{_escape(code)}'" for code in orphan_codes)
    return (
        "-- 删除代码中已不存在的权限码（会 CASCADE 清理 sys_role_permission）\n"
        "DELETE FROM sys_permission\n"
        f"WHERE permission_code IN (\n  {codes_sql}\n);\n"
    )


def build_sync_sql(
    entries: list[tuple[str, str, int]],
    orphan_codes: list[str],
    *,
    prune: bool,
    remark: str = "synced from code",
    created_by: int = 1,
) -> str:
    """生成补缺 + 可选删 orphan 的同步 SQL。"""
    parts: list[str] = []
    insert_sql = build_upsert_sql(entries, remark=remark, created_by=created_by)
    if entries or not prune:
        parts.append(insert_sql.rstrip())
    if prune:
        parts.append(build_prune_sql(orphan_codes).rstrip())
    if not parts:
        return "-- nothing to sync\n"
    return "\n\n".join(parts) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
