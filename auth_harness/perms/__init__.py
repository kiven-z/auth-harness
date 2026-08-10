"""从后端 @auth.decide 扫描权限码，对照 seed / DB。"""

from auth_harness.perms.service import (
    apply_missing,
    build_sync_plan,
    check_permissions,
    generate_upsert_sql,
    scan_permission_codes,
)

__all__ = [
    "apply_missing",
    "build_sync_plan",
    "check_permissions",
    "generate_upsert_sql",
    "scan_permission_codes",
]
