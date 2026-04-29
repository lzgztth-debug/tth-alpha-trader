"""JWT 认证模块

提供基于 JWT 的 API 认证功能，包括用户注册、登录、令牌刷新和用户信息查询。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from loguru import logger
from passlib.context import CryptContext
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY", os.getenv("JWT_SECRET_KEY", "alphatrader-default-secret-key-change-in-production"))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# 内存用户存储 (生产环境应替换为数据库)
# ---------------------------------------------------------------------------

_users_db: Dict[str, Dict[str, Any]] = {}


def _init_default_user() -> None:
    """初始化默认管理员用户（仅当用户表为空时）。"""
    if "admin" not in _users_db:
        _users_db["admin"] = {
            "username": "admin",
            "hashed_password": pwd_context.hash("admin123"),
            "full_name": "Admin",
            "role": "admin",
            "is_active": True,
        }
        logger.info("默认管理员用户已创建: admin / admin123")


_init_default_user()


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    full_name: Optional[str] = Field(default=None, max_length=64, description="全名")


class UserLoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """令牌响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    refresh_token: str = Field(..., description="JWT 刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="访问令牌过期时间（秒）")


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str = Field(..., description="刷新令牌")


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool


# ---------------------------------------------------------------------------
# 密码工具
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码。"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希。"""
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT 工具
# ---------------------------------------------------------------------------

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建 JWT 访问令牌。

    Args:
        data:         要编码的数据字典。
        expires_delta: 过期时间增量。

    Returns:
        JWT 令牌字符串。
    """
    to_encode = data.copy()

    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    logger.debug(f"JWT 访问令牌已创建: subject={data.get('sub')}")
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建 JWT 刷新令牌。

    Args:
        data:         要编码的数据字典。
        expires_delta: 过期时间增量。

    Returns:
        JWT 刷新令牌字符串。
    """
    to_encode = data.copy()

    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    logger.debug(f"JWT 刷新令牌已创建: subject={data.get('sub')}")
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """解码 JWT 令牌。

    Args:
        token: JWT 令牌字符串。

    Returns:
        解码后的数据字典。

    Raises:
        HTTPException: 令牌无效或已过期。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT 令牌解码失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI 依赖
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """获取当前认证用户。

    FastAPI 依赖项，用于保护需要认证的 API 端点。

    Args:
        credentials: HTTP Bearer 凭证。

    Returns:
        用户信息字典。

    Raises:
        HTTPException: 未认证或认证失败。
    """
    # 如果认证未启用，返回默认用户
    api_key_enabled = os.getenv("API_KEY_ENABLED", "true").lower() == "true"
    if not api_key_enabled:
        return {"sub": "default", "role": "admin"}

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)

    # 确保是访问令牌
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌类型",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
        )

    # 检查用户是否存在
    user = _users_db.get(username)
    if user is None or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    return payload


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[Dict[str, Any]]:
    """获取可选的当前用户（不强制认证）。

    Args:
        credentials: HTTP Bearer 凭证。

    Returns:
        用户信息字典，未认证时返回 None。
    """
    if credentials is None:
        return None

    try:
        return decode_token(credentials.credentials)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=UserInfoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户",
    description="使用用户名和密码注册新用户。",
)
async def register(request: UserRegisterRequest) -> UserInfoResponse:
    """注册新用户。"""
    username = request.username

    # 检查用户名是否已存在
    if username in _users_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名 '{username}' 已存在",
        )

    # 创建用户
    user_data = {
        "username": username,
        "hashed_password": get_password_hash(request.password),
        "full_name": request.full_name or username,
        "role": "user",
        "is_active": True,
    }
    _users_db[username] = user_data

    logger.info(f"新用户已注册: {username}")

    return UserInfoResponse(
        username=user_data["username"],
        full_name=user_data["full_name"],
        role=user_data["role"],
        is_active=user_data["is_active"],
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="用户登录",
    description="使用用户名和密码登录，返回 JWT 访问令牌和刷新令牌。",
)
async def login(request: UserLoginRequest) -> TokenResponse:
    """用户登录，返回 JWT 令牌。"""
    user = _users_db.get(request.username)

    # 验证用户存在、密码正确且账户激活
    if user is None or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )

    # 生成令牌
    token_data = {"sub": user["username"], "role": user["role"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info(f"用户登录成功: {request.username}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="刷新访问令牌",
    description="使用刷新令牌获取新的访问令牌和刷新令牌。",
)
async def refresh_token(request: RefreshTokenRequest) -> TokenResponse:
    """使用刷新令牌获取新的令牌对。"""
    payload = decode_token(request.refresh_token)

    # 确保是刷新令牌
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌类型，需要刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否存在且激活
    user = _users_db.get(username)
    if user is None or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 生成新的令牌对
    token_data = {"sub": user["username"], "role": user["role"]}
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    logger.info(f"令牌刷新成功: {username}")

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserInfoResponse,
    summary="获取当前用户信息",
    description="获取当前认证用户的详细信息。",
)
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> UserInfoResponse:
    """获取当前认证用户信息。"""
    username = current_user.get("sub")
    user = _users_db.get(username)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return UserInfoResponse(
        username=user["username"],
        full_name=user["full_name"],
        role=user["role"],
        is_active=user["is_active"],
    )
