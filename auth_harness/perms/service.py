"""权限码扫描 / 校验 / 生成 / 落库编排。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from auth_harness.config import HarnessConfig
from auth_harness.domain.paths import (
    DEFAULT_AUTH_SERVER_ROOT,
    DEFAULT_PERMISSION_SEED_PATH,
    PERMISSIONS_CATALOG_PATH,
)
from auth_harness.infrastructure import db as db_mod
from auth_harness.perms.catalog import PermissionsCatalog, load_catalog
from auth_harness.perms.scan import ScannedPermission, scan_java_permissions, unique_codes
from auth_harness.perms.seed_sql import (
    SeedPermissionRow,
    build_upsert_sql,
    parse_seed_sql,
    seed_codes,
)


@dataclass
class PermissionDiff:
    """代码与对照集差异。"""

    code_codes: list[str]
    baseline_codes: set[str]
    missing: list[str] = field(default_factory=list)
    orphan: list[str] = field(default_factory=list)
    unresolved_names: list[str] = field(default_factory=list)
    hits: list[ScannedPermission] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unresolved_names


def default_server_root() -> Path:
    return DEFAULT_AUTH_SERVER_ROOT


def default_seed_path() -> Path:
    return DEFAULT_PERMISSION_SEED_PATH


def default_catalog_path() -> Path:
    return PERMISSIONS_CATALOG_PATH


def scan_permission_codes(
    *,
    server_root: Path | None = None,
    catalog_path: Path | None = None,
) -> tuple[list[str], list[ScannedPermission], PermissionsCatalog]:
    """扫描代码权限码（已过滤 ignore）。"""
    catalog = load_catalog(catalog_path)
    root = server_root or default_server_root()
    hits = scan_java_permissions(root, exclude_globs=catalog.exclude_globs)
    codes = unique_codes(hits, ignore_codes=catalog.ignore_codes)
    return codes, hits, catalog


def check_permissions(
    *,
    server_root: Path | None = None,
    catalog_path: Path | None = None,
    seed_path: Path | None = None,
    config: HarnessConfig | None = None,
    against_db: bool = False,
    fail_on_orphan: bool = False,
) -> PermissionDiff:
    """对比代码权限码与 seed SQL（或 DB）。"""
    codes, hits, catalog = scan_permission_codes(
        server_root=server_root,
        catalog_path=catalog_path,
    )
    if against_db:
        if config is None:
            raise ValueError("against_db 需要 HarnessConfig")
        baseline = _load_db_codes(config)
    else:
        path = seed_path or default_seed_path()
        if not path.exists():
            raise FileNotFoundError(f"权限 seed 不存在: {path}")
        baseline = seed_codes(parse_seed_sql(path))

    missing = sorted(set(codes) - baseline)
    orphan = sorted(baseline - set(codes))
    unresolved = [code for code in codes if catalog.resolve_name(code) is None]
    diff = PermissionDiff(
        code_codes=codes,
        baseline_codes=baseline,
        missing=missing,
        orphan=orphan,
        unresolved_names=unresolved,
        hits=hits,
    )
    if fail_on_orphan and orphan:
        # ok 属性不含 orphan；严格模式由调用方看 orphan
        pass
    return diff


def generate_upsert_sql(
    *,
    server_root: Path | None = None,
    catalog_path: Path | None = None,
    seed_path: Path | None = None,
    config: HarnessConfig | None = None,
    against_db: bool = False,
    order_step: int = 10,
) -> tuple[str, list[tuple[str, str, int]], PermissionDiff]:
    """为缺失码生成 upsert SQL。"""
    diff = check_permissions(
        server_root=server_root,
        catalog_path=catalog_path,
        seed_path=seed_path,
        config=config,
        against_db=against_db,
    )
    catalog = load_catalog(catalog_path)
    start_order = _next_order_num(diff, against_db=against_db, config=config, seed_path=seed_path)
    entries: list[tuple[str, str, int]] = []
    for index, code in enumerate(diff.missing):
        name = catalog.resolve_name(code)
        if name is None:
            continue
        entries.append((code, name, start_order + index * order_step))
    sql = build_upsert_sql(entries)
    return sql, entries, diff


def apply_missing(
    config: HarnessConfig,
    *,
    server_root: Path | None = None,
    catalog_path: Path | None = None,
    order_step: int = 10,
) -> tuple[int, list[tuple[str, str, int]], PermissionDiff]:
    """将缺失权限码插入开发库（已存在跳过）。"""
    sql, entries, diff = generate_upsert_sql(
        server_root=server_root,
        catalog_path=catalog_path,
        config=config,
        against_db=True,
        order_step=order_step,
    )
    if not entries:
        return 0, entries, diff
    if diff.unresolved_names:
        unresolved = [c for c in diff.missing if c in diff.unresolved_names]
        if unresolved:
            raise ValueError(
                "无法解析中文名，请先补 fixtures/permissions_catalog.yml: "
                + ", ".join(unresolved)
            )
    conn = db_mod.connect(config)
    try:
        with conn.cursor() as cursor:
            for statement in _split_statements(sql):
                if statement.strip() and not statement.strip().startswith("--"):
                    cursor.execute(statement)
    finally:
        conn.close()
    return len(entries), entries, diff


def format_diff_report(diff: PermissionDiff, *, fail_on_orphan: bool = False) -> str:
    """人类可读差异报告。"""
    lines = [
        f"code={len(diff.code_codes)} baseline={len(diff.baseline_codes)} "
        f"missing={len(diff.missing)} orphan={len(diff.orphan)} "
        f"unresolved={len(diff.unresolved_names)}"
    ]
    if diff.missing:
        lines.append("missing (in code, not in baseline):")
        lines.extend(f"  + {code}" for code in diff.missing)
    if diff.orphan:
        lines.append("orphan (in baseline, not in code):")
        lines.extend(f"  - {code}" for code in diff.orphan)
    if diff.unresolved_names:
        lines.append("unresolved names (add to catalog):")
        lines.extend(f"  ? {code}" for code in diff.unresolved_names)
    if not diff.missing and not diff.unresolved_names and not (fail_on_orphan and diff.orphan):
        lines.append("OK")
    return "\n".join(lines)


def exit_code_for_diff(diff: PermissionDiff, *, fail_on_orphan: bool = False) -> int:
    if diff.missing or diff.unresolved_names:
        return 1
    if fail_on_orphan and diff.orphan:
        return 1
    return 0


def _load_db_codes(config: HarnessConfig) -> set[str]:
    conn = db_mod.connect(config)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT permission_code FROM sys_permission")
            return {str(row["permission_code"]) for row in cursor.fetchall()}
    finally:
        conn.close()


def _next_order_num(
    diff: PermissionDiff,
    *,
    against_db: bool,
    config: HarnessConfig | None,
    seed_path: Path | None,
) -> int:
    if against_db:
        if config is None:
            return 10
        conn = db_mod.connect(config)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COALESCE(MAX(order_num), 0) AS max_order FROM sys_permission")
                row = cursor.fetchone() or {}
                return int(row.get("max_order") or 0) + 10
        finally:
            conn.close()
    path = seed_path or default_seed_path()
    rows: list[SeedPermissionRow] = parse_seed_sql(path) if path.exists() else []
    if not rows:
        return 10
    return max(row.order_num for row in rows) + 10


def _split_statements(sql: str) -> list[str]:
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    return [part.strip() for part in cleaned.split(";") if part.strip()]
