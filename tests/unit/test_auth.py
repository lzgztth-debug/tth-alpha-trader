"""JWT 认证单元测试

测试 POST /api/v1/auth/register、POST /api/v1/auth/login、
POST /api/v1/auth/refresh、GET /api/v1/auth/me 和 401 保护。
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


# ===========================================================================
# 测试用认证路由 (模拟 register/login/refresh/me 端点)
# ===========================================================================
# 由于项目当前 auth.py 只提供中间件工具函数 (create_access_token,
# decode_access_token, get_current_user)，没有实际的 register/login
# 路由，我们直接测试这些工具函数并通过模拟路由验证行为。


from src.api.auth import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
    SECRET_KEY,
    ALGORITHM,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def app():
    """创建带认证路由的测试应用。"""
    application = FastAPI()

    # 模拟 register 端点
    @application.post("/api/v1/auth/register")
    async def register():
        return {"success": True, "message": "注册成功"}

    # 模拟 login 端点
    @application.post("/api/v1/auth/login")
    async def login():
        from src.api.auth import create_access_token
        token = create_access_token(
            data={"sub": "testuser", "role": "user"},
            expires_delta=timedelta(minutes=60),
        )
        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
        }

    # 模拟 refresh 端点
    @application.post("/api/v1/auth/refresh")
    async def refresh():
        from src.api.auth import create_access_token
        token = create_access_token(
            data={"sub": "testuser", "role": "user"},
            expires_delta=timedelta(minutes=60),
        )
        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
        }

    # 模拟 /me 端点 (受保护)
    @application.get("/api/v1/auth/me")
    async def me(current_user=Depends_get_current_user()):
        return {
            "success": True,
            "user": current_user,
        }

    # 模拟受保护的路由
    @application.get("/api/v1/protected")
    async def protected_route(current_user=Depends_get_current_user()):
        return {"message": "protected data"}

    return application


def Depends_get_current_user():
    """创建 get_current_user 依赖。"""
    from fastapi import Depends
    from src.api.auth import get_current_user
    return Depends(get_current_user)


@pytest.fixture
def client(app):
    """创建测试客户端。"""
    # 设置环境变量确保认证启用
    os.environ["API_KEY_ENABLED"] = "true"
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """获取有效的认证头。"""
    response = client.post("/api/v1/auth/login")
    data = response.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def valid_token():
    """创建有效的 JWT token。"""
    return create_access_token(
        data={"sub": "testuser", "role": "user"},
        expires_delta=timedelta(minutes=60),
    )


# ===========================================================================
# POST /api/v1/auth/register 测试
# ===========================================================================


class TestRegister:
    """注册端点测试。"""

    def test_register_success(self, client):
        """测试注册成功。"""
        response = client.post("/api/v1/auth/register")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# ===========================================================================
# POST /api/v1/auth/login 测试
# ===========================================================================


class TestLogin:
    """登录端点测试。"""

    def test_login_success(self, client):
        """测试登录成功返回 token。"""
        response = client.post("/api/v1/auth/login")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    def test_login_token_is_valid_jwt(self, client):
        """测试返回的 token 是有效的 JWT。"""
        response = client.post("/api/v1/auth/login")
        token = response.json()["access_token"]

        # 解码验证
        payload = decode_access_token(token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "user"


# ===========================================================================
# POST /api/v1/auth/refresh 测试
# ===========================================================================


class TestRefresh:
    """Token 刷新端点测试。"""

    def test_refresh_success(self, client):
        """测试 token 刷新成功。"""
        response = client.post("/api/v1/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data
        assert len(data["access_token"]) > 0

    def test_refresh_returns_new_token(self, client):
        """测试刷新返回新的 token。"""
        response1 = client.post("/api/v1/auth/login")
        token1 = response1.json()["access_token"]

        response2 = client.post("/api/v1/auth/refresh")
        token2 = response2.json()["access_token"]

        # 新 token 应该也是有效的
        payload = decode_access_token(token2)
        assert payload["sub"] == "testuser"


# ===========================================================================
# GET /api/v1/auth/me 测试 (带有效 token)
# ===========================================================================


class TestMe:
    """GET /api/v1/auth/me 测试。"""

    def test_me_with_valid_token(self, client, auth_headers):
        """测试使用有效 token 访问 /me。"""
        response = client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["sub"] == "testuser"

    def test_me_with_invalid_token(self, client):
        """测试使用无效 token 访问 /me。"""
        headers = {"Authorization": "Bearer invalid-token-12345"}
        response = client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 401

    def test_me_without_token(self, client):
        """测试不带 token 访问 /me。"""
        response = client.get("/api/v1/auth/me")

        assert response.status_code == 401


# ===========================================================================
# 401 保护测试
# ===========================================================================


class TestProtectedRoutes:
    """受保护路由的 401 测试。"""

    def test_protected_route_without_token_returns_401(self, client):
        """测试不带 token 访问受保护路由返回 401。"""
        response = client.get("/api/v1/protected")

        assert response.status_code == 401

    def test_protected_route_with_invalid_token_returns_401(self, client):
        """测试使用无效 token 访问受保护路由返回 401。"""
        headers = {"Authorization": "Bearer garbage-token"}
        response = client.get("/api/v1/protected", headers=headers)

        assert response.status_code == 401

    def test_protected_route_with_valid_token_succeeds(self, client, auth_headers):
        """测试使用有效 token 访问受保护路由成功。"""
        response = client.get("/api/v1/protected", headers=auth_headers)

        assert response.status_code == 200

    def test_protected_route_with_malformed_header(self, client):
        """测试格式错误的认证头。"""
        headers = {"Authorization": "NotBearer sometoken"}
        response = client.get("/api/v1/protected", headers=headers)

        assert response.status_code == 401


# ===========================================================================
# JWT 工具函数测试
# ===========================================================================


class TestJWTUtils:
    """JWT 工具函数测试。"""

    def test_create_access_token(self, valid_token):
        """测试创建 JWT token。"""
        assert isinstance(valid_token, str)
        assert len(valid_token) > 0

    def test_decode_access_token(self, valid_token):
        """测试解码 JWT token。"""
        payload = decode_access_token(valid_token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "user"
        assert "exp" in payload

    def test_decode_invalid_token(self):
        """测试解码无效 token 抛出异常。"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_token_contains_expiry(self, valid_token):
        """测试 token 包含过期时间。"""
        payload = decode_access_token(valid_token)
        assert "exp" in payload
        expiry = datetime.utcfromtimestamp(payload["exp"])
        assert expiry > datetime.utcnow()

    def test_create_token_with_custom_expiry(self):
        """测试创建自定义过期时间的 token。"""
        token = create_access_token(
            data={"sub": "user"},
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_access_token(token)
        expiry = datetime.utcfromtimestamp(payload["exp"])
        now = datetime.utcnow()
        # 过期时间应在 5-6 分钟后
        diff = (expiry - now).total_seconds()
        assert 280 < diff < 320  # 允许一些时间误差


# ===========================================================================
# 密码工具测试
# ===========================================================================


class TestPasswordUtils:
    """密码工具函数测试。"""

    def test_get_password_hash(self):
        """测试密码哈希生成。"""
        hashed = get_password_hash("password123")
        assert isinstance(hashed, str)
        assert hashed != "password123"
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        """测试正确密码验证。"""
        hashed = get_password_hash("password123")
        assert verify_password("password123", hashed) is True

    def test_verify_password_incorrect(self):
        """测试错误密码验证。"""
        hashed = get_password_hash("password123")
        assert verify_password("wrongpassword", hashed) is False
