"""HTTP：登录、管理端 API、内部 effective-codes。"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import jwt
import requests

from auth_harness.config import HarnessConfig
from auth_harness.infrastructure import system_paths as paths

SUCCESS_CODE = 0
INTERNAL_HEADER = "X-Internal-JWT"
INTERNAL_MAX_TTL_SECONDS = 60

_DEPT_META_KEYS = ("parentId", "deptName", "deptCode", "status", "orderNum", "remark")
_ROLE_META_KEYS = ("roleCode", "roleName", "status", "orderNum", "remark")
_PERMISSION_META_KEYS = ("permissionCode", "permissionName", "status", "orderNum", "remark")
_POST_META_KEYS = ("deptId", "postCode", "postName", "status", "orderNum", "remark")


class ApiClient:
    """封装 auth-harness 所需 HTTP 调用。"""

    def __init__(self, config: HarnessConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self._access_token: str | None = None

    def login(self) -> str:
        """用户名密码登录，返回 accessToken。"""
        url = f"{self.config.auth_base_url}/api/auth/login/username"
        payload = {
            "username": self.config.admin["username"],
            "password": self.config.admin["password"],
            "rememberMe": False,
        }
        response = self.session.post(url, json=payload, timeout=30)
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}
        if response.status_code == 401:
            raise RuntimeError(
                "登录失败 (401)：请确认 config.yml 中 admin 账号密码正确，"
                "且目标库中存在该用户并具备 sys:dept:update / sys:userrole:update 等权限。"
                f" 响应: {body}"
            )
        response.raise_for_status()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"登录失败: {body}")
        token = body["data"]["accessToken"]
        self._access_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        return token

    def ensure_login(self) -> None:
        """确保已登录。"""
        if not self._access_token:
            self.login()

    def put_dept_roles(self, dept_id: int, role_ids: list[int]) -> None:
        """部门角色全量覆盖。"""
        self._authorized_put(paths.dept_roles(dept_id), {"roleIds": role_ids})

    def put_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        """用户直连角色全量覆盖。"""
        self._authorized_put(paths.user_roles(user_id), {"roleIds": role_ids})

    def put_post_roles(self, post_id: int, role_ids: list[int]) -> None:
        """岗位角色全量覆盖。"""
        self._authorized_put(paths.post_roles(post_id), {"roleIds": role_ids})

    def post_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        """角色权限全量分配。"""
        self._authorized_post(paths.role_permissions(role_id), {"permissionIds": permission_ids})

    def post_user_dept(
        self,
        user_id: int,
        dept_id: int,
        *,
        is_primary: bool = True,
        remark: str | None = None,
    ) -> None:
        """新增用户部门关联。"""
        payload: dict[str, Any] = {
            "deptId": dept_id,
            "isPrimary": is_primary,
        }
        if remark is not None:
            payload["remark"] = remark
        self._authorized_post(paths.user_dept_collection(user_id), payload)

    def put_user_dept(
        self,
        user_id: int,
        relation_id: int,
        dept_id: int,
        *,
        is_primary: bool = True,
        remark: str | None = None,
    ) -> None:
        """更新用户部门关联。"""
        payload: dict[str, Any] = {
            "deptId": dept_id,
            "isPrimary": is_primary,
        }
        if remark is not None:
            payload["remark"] = remark
        self._authorized_put(paths.user_dept_item(user_id, relation_id), payload)

    def delete_user_depts(self, user_id: int, relation_ids: list[int]) -> None:
        """批量删除用户部门关联。"""
        self._authorized_delete(paths.user_dept_collection(user_id), relation_ids)

    def post_user_post(
        self,
        user_id: int,
        post_id: int,
        *,
        is_primary: bool = True,
        remark: str | None = None,
    ) -> None:
        """新增用户岗位关联。"""
        payload: dict[str, Any] = {
            "postId": post_id,
            "isPrimary": is_primary,
        }
        if remark is not None:
            payload["remark"] = remark
        self._authorized_post(paths.user_post_collection(user_id), payload)

    def delete_user_posts(self, user_id: int, relation_ids: list[int]) -> None:
        """批量删除用户岗位关联。"""
        self._authorized_delete(paths.user_post_collection(user_id), relation_ids)

    def update_dept_meta(self, dept_id: int, **changes: Any) -> None:
        """更新部门元数据（名称/父级/状态等）。"""
        self._update_meta(paths.DEPT, dept_id, self.get_dept_detail, _DEPT_META_KEYS, changes)

    def move_dept(self, dept_id: int, parent_id: int) -> None:
        """移动部门到新的父部门。"""
        detail = self.get_dept_detail(dept_id)
        current_parent = int(detail.get("parentId") or 0)
        if current_parent == parent_id:
            raise RuntimeError(
                f"部门 {dept_id} 父级已是 {parent_id}，服务端 move 为 no-op，不会写入 outbox；"
                f"请先 make seed 重置 harness 部门树"
            )
        self._authorized_put(paths.dept_move(), {"id": dept_id, "parentId": parent_id})
        updated = self.get_dept_detail(dept_id)
        if int(updated.get("parentId") or 0) != parent_id:
            raise RuntimeError(
                f"部门 {dept_id} 移动后 parent={updated.get('parentId')}，期望 {parent_id}"
            )

    def update_role_meta(self, role_id: int, **changes: Any) -> None:
        """更新角色元数据（编码/名称/状态等）。"""
        self._update_meta(paths.ROLE, role_id, self.get_role_detail, _ROLE_META_KEYS, changes)

    def update_permission_meta(self, permission_id: int, **changes: Any) -> None:
        """更新权限元数据（编码/名称/状态等）。"""
        self._update_meta(
            paths.PERMISSION,
            permission_id,
            self.get_permission_detail,
            _PERMISSION_META_KEYS,
            changes,
        )

    def update_post_meta(self, post_id: int, **changes: Any) -> None:
        """更新岗位元数据（名称/排序/状态等）。"""
        self._update_meta(paths.POST, post_id, self.get_post_detail, _POST_META_KEYS, changes)

    def batch_update_user_status(self, user_ids: list[int], status: int) -> None:
        """批量更新用户状态。"""
        self._authorized_put(paths.user_status_batch(), {"ids": user_ids, "status": status})

    def delete_users(self, user_ids: list[int]) -> None:
        """批量逻辑删除用户。"""
        self._authorized_delete(paths.USER, user_ids)

    def get_dept_detail(self, dept_id: int) -> dict[str, Any]:
        """部门详情。"""
        return self._get_data(paths.dept_detail(dept_id))

    def get_role_detail(self, role_id: int) -> dict[str, Any]:
        """角色详情。"""
        return self._get_data(paths.role_detail(role_id))

    def get_permission_detail(self, permission_id: int) -> dict[str, Any]:
        """权限详情。"""
        return self._get_data(paths.permission_detail(permission_id))

    def get_post_detail(self, post_id: int) -> dict[str, Any]:
        """岗位详情。"""
        return self._get_data(paths.post_detail(post_id))

    def get_effective_codes(self, user_id: int) -> dict[str, Any]:
        """调用内部 effective-codes（需 X-Internal-JWT）。"""
        url = (
            f"{self.config.auth_base_url}/api/auth/inner/authorization/principal/"
            f"{user_id}/effective-codes"
        )
        headers = {INTERNAL_HEADER: self._issue_internal_service_token()}
        response = self.session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"effective-codes 失败 userId={user_id}: {body}")
        data = body["data"] or {}
        return {
            "userId": user_id,
            "roles": sorted(data.get("roleCodes") or []),
            "permissions": sorted(data.get("permissionCodes") or []),
        }

    def _system(self, path: str) -> str:
        return f"{self.config.system_base_url}{path}"

    def _authorized_put(self, path: str, payload: dict[str, Any]) -> None:
        self.ensure_login()
        self._put_json(self._system(path), payload)

    def _authorized_post(self, path: str, payload: dict[str, Any]) -> None:
        self.ensure_login()
        self._post_json(self._system(path), payload)

    def _authorized_delete(self, path: str, payload: list[Any]) -> None:
        self.ensure_login()
        self._delete_json(self._system(path), payload)

    def _update_meta(
        self,
        resource_path: str,
        entity_id: int,
        detail_loader: Callable[[int], dict[str, Any]],
        field_keys: tuple[str, ...],
        changes: dict[str, Any],
    ) -> None:
        detail = detail_loader(entity_id)
        payload: dict[str, Any] = {"id": entity_id}
        for key in field_keys:
            payload[key] = detail.get(key)
        payload.update(changes)
        self._authorized_put(resource_path, payload)

    def _get_data(self, path: str) -> dict[str, Any]:
        self.ensure_login()
        response = self.session.get(self._system(path), timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"GET {path} 失败: {body}")
        data = body.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"GET {path} 返回非对象: {body}")
        return data

    def _put_json(self, url: str, payload: dict[str, Any]) -> None:
        response = self.session.put(url, json=payload, timeout=30)
        self._raise_for_http_error("PUT", url, response)
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"PUT {url} 失败: {body}")

    def _post_json(self, url: str, payload: dict[str, Any]) -> None:
        response = self.session.post(url, json=payload, timeout=30)
        self._raise_for_http_error("POST", url, response)
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"POST {url} 失败: {body}")

    def _delete_json(self, url: str, payload: list[Any]) -> None:
        response = self.session.delete(url, json=payload, timeout=30)
        self._raise_for_http_error("DELETE", url, response)
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"DELETE {url} 失败: {body}")

    @staticmethod
    def _raise_for_http_error(method: str, url: str, response: requests.Response) -> None:
        """将 HTTP 错误包装成带响应体的可读异常。"""
        if response.ok:
            return
        try:
            detail: Any = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"{method} {url} HTTP {response.status_code}: {detail}"
        )

    def _issue_internal_service_token(self) -> str:
        """签发服务身份内部 JWT（与 InternalTokenProvider.buildServiceToken 对齐）。"""
        jwt_conf = self.config.internal_jwt
        secret = jwt_conf["secret"]
        issuer = jwt_conf["issuer"]
        service_id = jwt_conf.get("service_id", "auth-harness")
        now = int(time.time())
        claims = {
            "jti": str(uuid.uuid4()),
            "iss": issuer,
            "sub": "0",
            "iat": now,
            "token_type": "INTERNAL",
            "principal_type": "SERVICE",
            "service_id": service_id,
            "exp": now + INTERNAL_MAX_TTL_SECONDS,
        }
        algorithm = jwt_conf.get("algorithm", "HS256")
        return jwt.encode(claims, secret, algorithm=algorithm)
