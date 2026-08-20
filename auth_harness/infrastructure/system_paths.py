"""system-service Admin API 路径（与 auth-server-pro Controller 对齐）。

约定：
- 资源 CRUD：PUT 集合路径 + body 含 id（部门/角色/权限/岗位）
- 子资源授权：PUT /{resourceId}/roles 等
- 部门移动：PUT /dept/move + body {id, parentId}（菜单才是 /{id}/move）
"""

from __future__ import annotations

DEPT = "/api/system/dept"
ROLE = "/api/system/role"
PERMISSION = "/api/system/permission"
POST = "/api/system/post"
USER = "/api/system/user"
USER_ROLE = "/api/system/user-role"
USER_DEPT = "/api/system/user-dept"
USER_POST = "/api/system/user-post"


def dept_detail(dept_id: int) -> str:
    return f"{DEPT}/{dept_id}"


def dept_roles(dept_id: int) -> str:
    return f"{DEPT}/{dept_id}/roles"


def dept_move() -> str:
    return f"{DEPT}/move"


def role_detail(role_id: int) -> str:
    return f"{ROLE}/{role_id}"


def role_permissions(role_id: int) -> str:
    return f"{ROLE}/{role_id}/permissions"


def permission_detail(permission_id: int) -> str:
    return f"{PERMISSION}/{permission_id}"


def post_detail(post_id: int) -> str:
    return f"{POST}/{post_id}"


def post_roles(post_id: int) -> str:
    return f"{POST}/{post_id}/roles"


def user_roles(user_id: int) -> str:
    return f"{USER_ROLE}/{user_id}"


def user_dept_collection(user_id: int) -> str:
    return f"{USER_DEPT}/{user_id}"


def user_dept_item(user_id: int, relation_id: int) -> str:
    return f"{USER_DEPT}/{user_id}/{relation_id}"


def user_post_collection(user_id: int) -> str:
    return f"{USER_POST}/{user_id}"


def user_status_batch() -> str:
    return f"{USER}/status"
