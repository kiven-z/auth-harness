"""加载 permissions_catalog.yml。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from auth_harness.domain.paths import PERMISSIONS_CATALOG_PATH


@dataclass(frozen=True)
class PermissionsCatalog:
    """权限码中文名与扫描忽略规则。"""

    resources: dict[str, str] = field(default_factory=dict)
    actions: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, str] = field(default_factory=dict)
    ignore_codes: frozenset[str] = field(default_factory=frozenset)
    exclude_globs: tuple[str, ...] = ()
    prune_protect_prefixes: tuple[str, ...] = ()

    def resolve_name(self, code: str) -> str | None:
        """解析展示名；无法解析返回 None。"""
        if code in self.overrides:
            return self.overrides[code]
        parts = code.split(":")
        if len(parts) < 2:
            return None
        action = parts[-1]
        resource = ":".join(parts[:-1])
        resource_name = self.resources.get(resource)
        action_name = self.actions.get(action)
        if not resource_name or not action_name:
            return None
        return f"{resource_name}-{action_name}"

    def is_prune_protected(self, code: str) -> bool:
        """是否禁止被 --prune 删除。"""
        return any(code.startswith(prefix) for prefix in self.prune_protect_prefixes)


def load_catalog(path: Path | None = None) -> PermissionsCatalog:
    """从 YAML 加载目录。"""
    catalog_path = path or PERMISSIONS_CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as handle:
        raw: Any = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"无效的权限目录: {catalog_path}")
    return PermissionsCatalog(
        resources={str(k): str(v) for k, v in (raw.get("resources") or {}).items()},
        actions={str(k): str(v) for k, v in (raw.get("actions") or {}).items()},
        overrides={str(k): str(v) for k, v in (raw.get("overrides") or {}).items()},
        ignore_codes=frozenset(str(x) for x in (raw.get("ignore_codes") or [])),
        exclude_globs=tuple(str(x) for x in (raw.get("exclude_globs") or [])),
        prune_protect_prefixes=tuple(str(x) for x in (raw.get("prune_protect_prefixes") or [])),
    )
