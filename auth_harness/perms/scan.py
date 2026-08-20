"""扫描 Java 源码中的 @auth.decide('...')。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DECIDE_PATTERN = re.compile(r"""@auth\.decide\(\s*['\"]([^'\"]+)['\"]\s*\)""")

# 与 AuthCodeConvention 对齐：1～4 段，每段 * 或 [a-z][a-z0-9]*
PERMISSION_CODE_PATTERN = re.compile(
    r"^(?:\*|[a-z][a-z0-9]*)(?::(?:\*|[a-z][a-z0-9]*)){0,3}$"
)


@dataclass(frozen=True, order=True)
class ScannedPermission:
    """源码中出现的权限码及引用位置。"""

    code: str
    relative_path: str
    line: int


def scan_java_permissions(
    server_root: Path,
    *,
    exclude_globs: tuple[str, ...] = (),
) -> list[ScannedPermission]:
    """扫描 auth-server-pro 下 Java 文件中的 decide 权限码。"""
    root = server_root.resolve()
    hits: list[ScannedPermission] = []
    for path in sorted(root.rglob("*.java")):
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel, exclude_globs):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line):
                continue
            for match in DECIDE_PATTERN.finditer(line):
                code = match.group(1)
                if not PERMISSION_CODE_PATTERN.match(code):
                    continue
                hits.append(ScannedPermission(code=code, relative_path=rel, line=line_no))
    return hits


def unique_codes(hits: list[ScannedPermission], *, ignore_codes: frozenset[str]) -> list[str]:
    """去重排序，并去掉 ignore 列表。"""
    codes = {hit.code for hit in hits if hit.code not in ignore_codes}
    return sorted(codes)


def _is_comment_line(line: str) -> bool:
    stripped = line.lstrip()
    return (
        stripped.startswith("//")
        or stripped.startswith("*")
        or stripped.startswith("/*")
        or stripped.startswith("*/")
    )


def _is_excluded(relative_path: str, exclude_globs: tuple[str, ...]) -> bool:
    from fnmatch import fnmatch

    for pattern in exclude_globs:
        normalized = pattern[2:] if pattern.startswith("**/") else pattern
        if fnmatch(relative_path, pattern) or fnmatch(relative_path, normalized):
            return True
        # 兼容 **/foo/** 匹配中间段
        if pattern.startswith("**/") and pattern.endswith("/**"):
            mid = pattern[3:-3]
            if f"/{mid}/" in f"/{relative_path}/":
                return True
    return False
