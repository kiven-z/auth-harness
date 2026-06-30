"""L1 影响面反查（复刻 AuthorizationImpactMapper SQL）。"""

from __future__ import annotations

from typing import Any

import pymysql

from auth_harness.infrastructure import db as db_mod

IMPACT_KINDS = frozenset(
    {
        "GRANT_USER",
        "GRANT_DEPT",
        "GRANT_POST",
        "ROLE",
        "USER_DEPT",
        "USER_POST",
    }
)

SQL_BY_ROLE_CODES = """
SELECT DISTINCT user_id FROM (
    SELECT gt.subject_id AS user_id
    FROM grant_table gt
    INNER JOIN sys_role r ON r.id = gt.role_id
    WHERE gt.subject_type = 'USER' AND r.role_code IN ({placeholders})
    UNION
    SELECT ud.user_id
    FROM grant_table gt
    INNER JOIN sys_role r ON r.id = gt.role_id
    INNER JOIN user_dept ud ON gt.subject_type = 'DEPT'
    INNER JOIN dept_closure dc ON ud.dept_id = dc.descendant_id AND dc.ancestor_id = gt.subject_id
    INNER JOIN sys_dept d ON d.id = dc.descendant_id
    WHERE r.role_code IN ({placeholders}) AND ud.status IN (1, 2)
    UNION
    SELECT up.user_id
    FROM grant_table gt
    INNER JOIN sys_role r ON r.id = gt.role_id
    INNER JOIN user_post up ON gt.subject_type = 'POST' AND up.post_id = gt.subject_id
    WHERE r.role_code IN ({placeholders}) AND up.status IN (1, 2)
) impacted
ORDER BY user_id
"""

SQL_GRANT_USER = """
SELECT DISTINCT gt.subject_id AS user_id
FROM grant_table gt
WHERE gt.subject_type = 'USER' AND gt.subject_id IN ({placeholders})
ORDER BY user_id
"""

SQL_GRANT_DEPT = """
SELECT DISTINCT ud.user_id
FROM user_dept ud
INNER JOIN dept_closure dc ON ud.dept_id = dc.descendant_id
INNER JOIN sys_dept d ON d.id = dc.descendant_id
WHERE dc.ancestor_id IN ({placeholders}) AND ud.status IN (1, 2)
ORDER BY ud.user_id
"""

SQL_GRANT_POST = """
SELECT DISTINCT up.user_id
FROM user_post up
WHERE up.post_id IN ({placeholders}) AND up.status IN (1, 2)
ORDER BY up.user_id
"""

SQL_USER_DEPT = SQL_GRANT_DEPT
SQL_USER_POST = SQL_GRANT_POST


def resolve_impacted_user_ids(
    conn: pymysql.connections.Connection,
    kind: str,
    subject_ids: list[int] | None = None,
    role_codes: list[str] | None = None,
) -> set[int]:
    """按影响面类型反查 userId 集合。"""
    normalized_kind = kind.upper()
    if normalized_kind not in IMPACT_KINDS:
        raise ValueError(f"未知影响面类型: {kind}")

    if normalized_kind == "ROLE":
        if not role_codes:
            raise ValueError("ROLE 类型需要 role_codes")
        return _query_user_ids(conn, SQL_BY_ROLE_CODES, role_codes)

    if not subject_ids:
        raise ValueError(f"{normalized_kind} 需要 subject_ids")

    sql_map = {
        "GRANT_USER": SQL_GRANT_USER,
        "GRANT_DEPT": SQL_GRANT_DEPT,
        "GRANT_POST": SQL_GRANT_POST,
        "USER_DEPT": SQL_USER_DEPT,
        "USER_POST": SQL_USER_POST,
    }
    return _query_user_ids(conn, sql_map[normalized_kind], subject_ids)


def _query_user_ids(
    conn: pymysql.connections.Connection,
    sql_template: str,
    values: list[Any],
) -> set[int]:
    placeholders = ", ".join(["%s"] * len(values))
    sql = sql_template.format(placeholders=placeholders)
    placeholder_count = sql_template.count("{placeholders}")
    params: tuple[Any, ...] = tuple(values) * placeholder_count
    rows = db_mod.fetch_all(conn, sql, params)
    return {int(row["user_id"]) for row in rows}


def compare_user_sets(expected: set[int], actual: set[int]) -> list[str]:
    """对比期望与实际 userId 集合。"""
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    diffs: list[str] = []
    if missing:
        diffs.append(f"缺少 userId: {missing[:20]}{'…' if len(missing) > 20 else ''}")
    if extra:
        diffs.append(f"多余 userId: {extra[:20]}{'…' if len(extra) > 20 else ''}")
    return diffs
