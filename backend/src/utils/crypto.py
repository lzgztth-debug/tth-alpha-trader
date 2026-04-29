"""
加密工具模块
============
基于 cryptography.fernet 的对称加密工具。
用于加密/解密敏感数据（如API密钥、交易密码等）。
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class KeyManager:
    """
    密钥管理器 - 负责加密密钥的生成、加载、加密和解密操作。

    使用 Fernet 对称加密方案（AES-128-CBC + HMAC-SHA256）。
    支持从密码派生密钥（PBKDF2）或直接使用 Fernet 密钥。
    """

    def __init__(self, key: Optional[bytes] = None, password: Optional[str] = None, salt: Optional[bytes] = None):
        """
        初始化 KeyManager。

        Args:
            key: Fernet 密钥（bytes），若提供则直接使用
            password: 密码字符串，用于通过 PBKDF2 派生密钥（与 key 二选一）
            salt: PBKDF2 盐值，若为 None 则自动生成

        Raises:
            ValueError: key 和 password 都未提供
        """
        if key is not None:
            self._fernet = Fernet(key)
            self._key = key
        elif password is not None:
            self._salt = salt or os.urandom(16)
            self._key = self._derive_key(password, self._salt)
            self._fernet = Fernet(self._key)
        else:
            raise ValueError("必须提供 key 或 password 参数之一")

    @staticmethod
    def _derive_key(password: str, salt: bytes) -> bytes:
        """
        使用 PBKDF2 从密码派生 Fernet 密钥。

        Args:
            password: 密码字符串
            salt: 盐值

        Returns:
            Fernet 格式的密钥（bytes）
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
        return key

    @staticmethod
    def generate_key() -> str:
        """
        生成一个新的随机 Fernet 密钥。

        Returns:
            Base64 编码的 Fernet 密钥字符串
        """
        return Fernet.generate_key().decode("utf-8")

    @staticmethod
    def generate_salt() -> bytes:
        """
        生成随机盐值。

        Returns:
            16字节的随机盐值
        """
        return os.urandom(16)

    @property
    def key(self) -> bytes:
        """获取当前使用的密钥"""
        return self._key

    def encrypt(self, plaintext: str) -> str:
        """
        加密字符串。

        Args:
            plaintext: 待加密的明文字符串

        Returns:
            Base64 编码的密文字符串

        Raises:
            TypeError: plaintext 不是字符串
        """
        if not isinstance(plaintext, str):
            raise TypeError(f"plaintext 必须是字符串， got {type(plaintext).__name__}")

        encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        解密字符串。

        Args:
            ciphertext: Base64 编码的密文字符串

        Returns:
            解密后的明文字符串

        Raises:
            TypeError: ciphertext 不是字符串
            InvalidToken: 密文无效或密钥不匹配
        """
        if not isinstance(ciphertext, str):
            raise TypeError(f"ciphertext 必须是字符串， got {type(ciphertext).__name__}")

        decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")

    def encrypt_bytes(self, data: bytes) -> bytes:
        """
        加密字节数据。

        Args:
            data: 待加密的字节数据

        Returns:
            加密后的字节数据
        """
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, data: bytes) -> bytes:
        """
        解密字节数据。

        Args:
            data: 待解密的字节数据

        Returns:
            解密后的字节数据
        """
        return self._fernet.decrypt(data)

    def is_valid_token(self, token: str) -> bool:
        """
        验证密文是否可以被当前密钥解密。

        Args:
            token: 待验证的密文字符串

        Returns:
            True 如果密文有效，False 如果密文无效
        """
        try:
            self._fernet.decrypt(token.encode("utf-8"))
            return True
        except (InvalidToken, Exception):
            return False

    def __repr__(self) -> str:
        key_preview = self._key[:8].decode("utf-8", errors="replace") + "..."
        return f"KeyManager(key={key_preview})"
