"""HTTP：登录、管理端 API、内部 effective-codes。"""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
import requests

from auth_harness.config import HarnessConfig

SUCCESS_CODE = 0
INTERNAL_HEADER = "X-Internal-JWT"
INTERNAL_MAX_TTL_SECONDS = 60


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
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/dept/{dept_id}/roles"
        self._put_json(url, {"roleIds": role_ids})

    def put_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        """用户直连角色全量覆盖。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-role/{user_id}"
        self._put_json(url, {"roleIds": role_ids})

    def put_post_roles(self, post_id: int, role_ids: list[int]) -> None:
        """岗位角色全量覆盖。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/post/{post_id}/roles"
        self._put_json(url, {"roleIds": role_ids})

    def post_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        """角色权限全量分配。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/role/{role_id}/permissions"
        self._post_json(url, {"permissionIds": permission_ids})

    def post_user_dept(
        self,
        user_id: int,
        dept_id: int,
        *,
        status: int = 1,
        is_primary: bool = True,
        remark: str | None = None,
    ) -> None:
        """新增用户部门关联。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-dept/{user_id}"
        payload: dict[str, Any] = {
            "deptId": dept_id,
            "status": status,
            "isPrimary": is_primary,
        }
        if remark is not None:
            payload["remark"] = remark
        self._post_json(url, payload)

    def put_user_dept(
        self,
        user_id: int,
        relation_id: int,
        dept_id: int,
        *,
        status: int = 1,
        is_primary: bool = True,
        remark: str | None = None,
    ) -> None:
        """更新用户部门关联。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-dept/{user_id}/{relation_id}"
        payload: dict[str, Any] = {
            "deptId": dept_id,
            "status": status,
            "isPrimary": is_primary,
        }
        if remark is not None:
            payload["remark"] = remark
        self._put_json(url, payload)

    def delete_user_depts(self, user_id: int, relation_ids: list[int]) -> None:
        """批量删除用户部门关联。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-dept/{user_id}"
        self._delete_json(url, relation_ids)

    def post_user_post(
        self,
        user_id: int,
        post_id: int,
        *,
        status: int = 1,
        is_primary: bool = True,
        remark: str | None = None,
    ) -> None:
        """新增用户岗位关联。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-post/{user_id}"
        payload: dict[str, Any] = {
            "postId": post_id,
            "status": status,
            "isPrimary": is_primary,
        }
        if remark is not None:
            payload["remark"] = remark
        self._post_json(url, payload)

    def delete_user_posts(self, user_id: int, relation_ids: list[int]) -> None:
        """批量删除用户岗位关联。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-post/{user_id}"
        self._delete_json(url, relation_ids)

    def update_dept_meta(self, dept_id: int, **changes: Any) -> None:
        """更新部门元数据（名称/父级/状态等）。"""
        detail = self.get_dept_detail(dept_id)
        payload = {
            "id": dept_id,
            "parentId": detail["parentId"],
            "deptName": detail["deptName"],
            "deptCode": detail["deptCode"],
            "status": detail["status"],
            "orderNum": detail.get("orderNum"),
            "remark": detail.get("remark"),
        }
        payload.update(changes)
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/dept"
        self._put_json(url, payload)

    def move_dept(self, dept_id: int, parent_id: int) -> None:
        """移动部门到新的父部门。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/dept/{dept_id}/move"
        self._put_json(url, {"parentId": parent_id})

    def update_role_meta(self, role_id: int, **changes: Any) -> None:
        """更新角色元数据（编码/名称/状态等）。"""
        detail = self.get_role_detail(role_id)
        payload = {
            "id": role_id,
            "roleCode": detail["roleCode"],
            "roleName": detail["roleName"],
            "status": detail["status"],
            "orderNum": detail.get("orderNum"),
            "remark": detail.get("remark"),
        }
        payload.update(changes)
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/role"
        self._put_json(url, payload)

    def update_permission_meta(self, permission_id: int, **changes: Any) -> None:
        """更新权限元数据（编码/名称/状态等）。"""
        detail = self.get_permission_detail(permission_id)
        payload = {
            "id": permission_id,
            "permissionCode": detail["permissionCode"],
            "permissionName": detail["permissionName"],
            "status": detail["status"],
            "orderNum": detail.get("orderNum"),
            "remark": detail.get("remark"),
        }
        payload.update(changes)
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/permission"
        self._put_json(url, payload)

    def update_post_meta(self, post_id: int, **changes: Any) -> None:
        """更新岗位元数据（名称/排序/状态等）。"""
        detail = self.get_post_detail(post_id)
        payload = {
            "id": post_id,
            "deptId": detail["deptId"],
            "postCode": detail["postCode"],
            "postName": detail["postName"],
            "status": detail["status"],
            "orderNum": detail.get("orderNum"),
            "remark": detail.get("remark"),
        }
        payload.update(changes)
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/post"
        self._put_json(url, payload)

    def batch_update_user_status(self, user_ids: list[int], status: int) -> None:
        """批量更新用户状态。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user/status"
        self._put_json(url, {"ids": user_ids, "status": status})

    def delete_users(self, user_ids: list[int]) -> None:
        """批量逻辑删除用户。"""
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user"
        self._delete_json(url, user_ids)

    def get_dept_detail(self, dept_id: int) -> dict[str, Any]:
        """部门详情。"""
        url = f"{self.config.system_base_url}/api/system/dept/{dept_id}"
        return self._get_data(url)

    def get_role_detail(self, role_id: int) -> dict[str, Any]:
        """角色详情。"""
        url = f"{self.config.system_base_url}/api/system/role/{role_id}"
        return self._get_data(url)

    def get_permission_detail(self, permission_id: int) -> dict[str, Any]:
        """权限详情。"""
        url = f"{self.config.system_base_url}/api/system/permission/{permission_id}"
        return self._get_data(url)

    def get_post_detail(self, post_id: int) -> dict[str, Any]:
        """岗位详情。"""
        url = f"{self.config.system_base_url}/api/system/post/{post_id}"
        return self._get_data(url)

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

    def _get_data(self, url: str) -> dict[str, Any]:
        self.ensure_login()
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"GET {url} 失败: {body}")
        data = body.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"GET {url} 返回非对象: {body}")
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
