"""MySQL 辅助：执行 seed SQL、查询 outbox / 用户 / 授权。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor

from auth_harness.config import HARNESS_ROOT, HarnessConfig

SQL_DIR = HARNESS_ROOT / "sql"

SEED_ORDER = [
    "seed_roles_perms.sql",
    "seed_org.sql",
    "seed_users_bulk.sql",
    "seed_grants.sql",
]


def connect(config: HarnessConfig) -> pymysql.connections.Connection:
    """创建 MySQL 连接。"""
    mysql = config.mysql
    return pymysql.connect(
        host=mysql["host"],
        port=int(mysql.get("port", 3306)),
        user=mysql["user"],
        password=mysql["password"],
        database=mysql["database"],
        charset=mysql.get("charset", "utf8mb4"),
        autocommit=True,
        cursorclass=DictCursor,
    )


def execute_sql_file(conn: pymysql.connections.Connection, sql_path: Path) -> None:
    """执行单个 SQL 文件（支持多语句与存储过程）。"""
    content = sql_path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        for statement in _split_sql_statements(content):
            if statement.strip():
                cursor.execute(statement)


def _split_sql_statements(content: str) -> list[str]:
    """按 DELIMITER 切换拆分 SQL 语句。"""
    delimiter = ";"
    statements: list[str] = []
    buffer: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("DELIMITER "):
            pending = "".join(buffer).strip()
            if pending:
                statements.append(pending)
            buffer = []
            delimiter = stripped.split(maxsplit=1)[1]
            continue
        buffer.append(line)
        buffer.append("\n")
        if stripped.endswith(delimiter):
            chunk = "".join(buffer).rstrip()
            if delimiter != ";":
                if not chunk.endswith(delimiter):
                    raise ValueError(f"SQL 语句未以分隔符 {delimiter!r} 结尾: {chunk[-80:]}")
                chunk = chunk[: -len(delimiter)].strip()
            else:
                chunk = chunk.strip()
            if chunk:
                statements.append(chunk)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def run_seed(config: HarnessConfig) -> None:
    """按顺序执行 seed SQL（先 cleanup，保证重复执行不因外键失败）。"""
    conn = connect(config)
    try:
        print("[seed] cleanup.sql (pre-seed)")
        execute_sql_file(conn, SQL_DIR / "cleanup.sql")
        for name in SEED_ORDER:
            path = SQL_DIR / name
            print(f"[seed] {name}")
            execute_sql_file(conn, path)
    finally:
        conn.close()


def run_cleanup(config: HarnessConfig) -> None:
    """执行 cleanup.sql。"""
    conn = connect(config)
    try:
        print("[cleanup] cleanup.sql")
        execute_sql_file(conn, SQL_DIR / "cleanup.sql")
    finally:
        conn.close()


def fetch_one(conn: pymysql.connections.Connection, sql: str, params: Iterable[Any] = ()) -> dict | None:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def fetch_all(conn: pymysql.connections.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def count_dept_members(conn: pymysql.connections.Connection, dept_id: int) -> int:
    """统计部门子树内活跃成员数。"""
    row = fetch_one(
        conn,
        """
        SELECT COUNT(DISTINCT ud.user_id) AS cnt
        FROM user_dept ud
        INNER JOIN dept_closure dc ON ud.dept_id = dc.descendant_id
        INNER JOIN sys_dept d ON d.id = ud.dept_id AND d.is_deleted = 0 AND d.status = 1
        INNER JOIN sys_dept da ON da.id = dc.ancestor_id AND da.is_deleted = 0 AND da.status = 1
        WHERE dc.ancestor_id = %s AND ud.status IN (1, 2)
        """,
        (dept_id,),
    )
    return int(row["cnt"]) if row else 0


def list_dept_user_ids(conn: pymysql.connections.Connection, dept_id: int) -> list[int]:
    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT ud.user_id
        FROM user_dept ud
        INNER JOIN dept_closure dc ON ud.dept_id = dc.descendant_id
        WHERE dc.ancestor_id = %s AND ud.status IN (1, 2)
        ORDER BY ud.user_id
        """,
        (dept_id,),
    )
    return [int(r["user_id"]) for r in rows]


def list_active_users_in_range(conn: pymysql.connections.Connection, id_min: int, id_max: int) -> list[int]:
    rows = fetch_all(
        conn,
        """
        SELECT id FROM sys_user
        WHERE id BETWEEN %s AND %s AND status = 1
        ORDER BY id
        """,
        (id_min, id_max),
    )
    return [int(r["id"]) for r in rows]


def fetch_perm_version(conn: pymysql.connections.Connection, user_id: int) -> int | None:
    row = fetch_one(conn, "SELECT perm_version FROM sys_user WHERE id = %s", (user_id,))
    if not row:
        return None
    return int(row["perm_version"] or 0)


# DB oracle：复刻 UserAuthorizationGrantMapper 正向展开逻辑
ORACLE_ROLES_SQL = """
WITH user_subjects AS (
    SELECT 'USER' AS sub_type, %s AS sub_id
    UNION ALL
    SELECT 'DEPT' AS sub_type, dc.ancestor_id AS sub_id
    FROM user_dept ud
    JOIN dept_closure dc ON ud.dept_id = dc.descendant_id
    JOIN sys_dept d ON d.id = ud.dept_id AND d.is_deleted = 0 AND d.status = 1
    JOIN sys_dept da ON da.id = dc.ancestor_id AND da.is_deleted = 0 AND da.status = 1
    WHERE ud.user_id = %s AND ud.status IN (1, 2)
    UNION ALL
    SELECT 'POST' AS sub_type, up.post_id AS sub_id
    FROM user_post up
    INNER JOIN sys_post sp ON sp.id = up.post_id AND sp.is_deleted = 0 AND sp.status = 1
    WHERE up.user_id = %s AND up.status IN (1, 2)
)
SELECT DISTINCT r.role_code
FROM grant_table gt
JOIN user_subjects us ON gt.subject_type = us.sub_type AND gt.subject_id = us.sub_id
JOIN sys_role r ON r.id = gt.role_id
WHERE r.status = 1
ORDER BY r.role_code
"""

ORACLE_PERMISSIONS_SQL = """
WITH user_subjects AS (
    SELECT 'USER' AS sub_type, %s AS sub_id
    UNION ALL
    SELECT 'DEPT' AS sub_type, dc.ancestor_id AS sub_id
    FROM user_dept ud
    JOIN dept_closure dc ON ud.dept_id = dc.descendant_id
    JOIN sys_dept d ON d.id = ud.dept_id AND d.is_deleted = 0 AND d.status = 1
    JOIN sys_dept da ON da.id = dc.ancestor_id AND da.is_deleted = 0 AND da.status = 1
    WHERE ud.user_id = %s AND ud.status IN (1, 2)
    UNION ALL
    SELECT 'POST' AS sub_type, up.post_id AS sub_id
    FROM user_post up
    INNER JOIN sys_post sp ON sp.id = up.post_id AND sp.is_deleted = 0 AND sp.status = 1
    WHERE up.user_id = %s AND up.status IN (1, 2)
),
all_role_ids AS (
    SELECT DISTINCT r.id AS role_id
    FROM grant_table gt
    JOIN user_subjects us ON gt.subject_type = us.sub_type AND gt.subject_id = us.sub_id
    JOIN sys_role r ON r.id = gt.role_id
    WHERE r.status = 1
)
SELECT DISTINCT p.permission_code
FROM sys_role_permission rp
JOIN all_role_ids ar ON rp.role_id = ar.role_id
JOIN sys_permission p ON p.id = rp.permission_id
WHERE p.status = 1
ORDER BY p.permission_code
"""


def query_db_oracle(conn: pymysql.connections.Connection, user_id: int) -> dict[str, Any]:
    """从 DB 重建用户角色/权限（不经过 HTTP）。"""
    roles = [
        r["role_code"]
        for r in fetch_all(conn, ORACLE_ROLES_SQL, (user_id, user_id, user_id))
    ]
    permissions = [
        r["permission_code"]
        for r in fetch_all(conn, ORACLE_PERMISSIONS_SQL, (user_id, user_id, user_id))
    ]
    perm_version = fetch_perm_version(conn, user_id)
    return {
        "userId": user_id,
        "roles": roles,
        "permissions": permissions,
        "permVersion": perm_version,
    }
