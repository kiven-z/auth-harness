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
        response.raise_for_status()
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"登录失败: {body}")
        token = body["data"]["accessToken"]
        self._access_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        return token

    def ensure_login(self) -> None:
        if not self._access_token:
            self.login()

    def put_dept_roles(self, dept_id: int, role_ids: list[int]) -> None:
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/dept/{dept_id}/roles"
        self._put_json(url, {"roleIds": role_ids})

    def put_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/user-role/{user_id}"
        self._put_json(url, {"roleIds": role_ids})

    def post_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        self.ensure_login()
        url = f"{self.config.system_base_url}/api/system/role/{role_id}/permissions"
        self._post_json(url, {"permissionIds": permission_ids})

    def get_effective_codes(self, user_id: int) -> dict[str, Any]:
        """调用内部 effective-codes（需 X-Internal-JWT）。"""
        url = f"{self.config.auth_base_url}/api/auth/inner/authorization/principal/{user_id}/effective-codes"
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

    def _put_json(self, url: str, payload: dict[str, Any]) -> None:
        response = self.session.put(url, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"PUT {url} 失败: {body}")

    def _post_json(self, url: str, payload: dict[str, Any]) -> None:
        response = self.session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != SUCCESS_CODE:
            raise RuntimeError(f"POST {url} 失败: {body}")

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
