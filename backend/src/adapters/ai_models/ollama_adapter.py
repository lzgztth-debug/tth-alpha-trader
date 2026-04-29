# src/adapters/ai_models/ollama_adapter.py
# Ollama 本地模型适配器 - 支持本地部署的开源模型（Llama 3, Qwen 等）

import time
import logging
import json
from typing import List, Dict, Any, Optional

import aiohttp

from src.adapters.ai_models.base import (
    BaseAIModelAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
    AIModelError,
    AIModelConnectionError,
    AIModelTimeoutError,
)

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseAIModelAdapter):
    """
    Ollama 本地模型适配器

    通过 Ollama REST API 调用本地部署的开源模型。
    支持 Llama 3, Qwen, Mistral, Phi-3 等模型。

    配置参数:
        provider: ModelProvider.OLLAMA
        model_name: 模型名称（如 llama3, qwen2, mistral, phi3）
        base_url: Ollama 服务地址，默认 http://localhost:11434
        temperature: 温度参数，默认 0.7
        max_tokens: 最大输出 token 数，默认 4096
        timeout: 超时时间（秒），默认 120（本地模型可能较慢）
    """

    # 常见的本地模型列表
    SUPPORTED_MODELS = [
        "llama3",
        "llama3:70b",
        "llama3.1",
        "llama3.1:405b",
        "qwen2",
        "qwen2:72b",
        "qwen2.5",
        "qwen2.5:72b",
        "mistral",
        "mistral:7b",
        "codellama",
        "phi3",
        "phi3:14b",
        "gemma2",
        "gemma2:27b",
        "deepseek-coder-v2",
        "yi",
        "yi:34b",
    ]

    # 默认 Ollama 服务地址
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None

        # 设置默认 base_url
        if not self.config.base_url:
            self.config.base_url = self.DEFAULT_BASE_URL

        # Ollama 本地模型通常不需要 API Key
        if not self.config.api_key:
            self.config.api_key = "ollama"

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _close_session(self):
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ModelResponse:
        """发送对话消息"""
        start_time = time.time()

        try:
            session = await self._get_session()

            # 合并参数
            temperature = kwargs.get('temperature', self.config.temperature)
            num_predict = kwargs.get('max_tokens', self.config.max_tokens)
            top_p = kwargs.get('top_p', self.config.top_p)
            stop = kwargs.get('stop', self.config.stop)

            # 构建 Ollama API 请求
            request_body = {
                "model": self.config.model_name,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": num_predict,
                    "top_p": top_p,
                },
            }

            if stop:
                request_body["options"]["stop"] = stop

            url = f"{self.config.base_url}/api/chat"

            logger.debug(
                f"Ollama: 发送请求, model={self.config.model_name}, "
                f"messages_count={len(messages)}, url={url}"
            )

            async with session.post(url, json=request_body) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AIModelError(
                        f"API 请求失败 (HTTP {response.status}): {error_text}",
                        provider="Ollama"
                    )

                data = await response.json()

            latency_ms = self._measure_latency(start_time)

            # 解析响应
            content = data.get("message", {}).get("content", "")
            model = data.get("model", self.config.model_name)
            finish_reason = "stop" if data.get("done", False) else ""

            # 解析 token 使用量
            usage = {}
            if "prompt_eval_count" in data or "eval_count" in data:
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
                    "completion_tokens": data.get("eval_count", 0) or 0,
                    "total_tokens": (
                        (data.get("prompt_eval_count", 0) or 0) +
                        (data.get("eval_count", 0) or 0)
                    ),
                }

            # 解析加载时间
            load_duration = data.get("load_duration", 0)
            if load_duration:
                load_ms = load_duration / 1_000_000  # 纳秒转毫秒
                logger.debug(f"Ollama: 模型加载时间 {load_ms:.0f}ms")

            model_response = ModelResponse(
                content=content,
                model=model,
                provider=ModelProvider.OLLAMA,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
            )

            logger.info(
                f"Ollama: 响应成功, model={model}, "
                f"tokens={usage.get('total_tokens', 0)}, "
                f"latency={latency_ms:.0f}ms"
            )

            return model_response

        except AIModelError:
            raise
        except aiohttp.ClientError as e:
            latency_ms = self._measure_latency(start_time)
            raise AIModelConnectionError(
                f"连接 Ollama 服务失败: {e}",
                provider="Ollama"
            )
        except asyncio.TimeoutError:
            latency_ms = self._measure_latency(start_time)
            raise AIModelTimeoutError(
                f"请求超时 ({self.config.timeout}s)",
                provider="Ollama"
            )
        except Exception as e:
            latency_ms = self._measure_latency(start_time)
            logger.error(f"Ollama: 请求失败, error={e}, latency={latency_ms:.0f}ms")
            raise AIModelError(
                f"请求失败: {e}",
                provider="Ollama"
            )

    async def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs
    ) -> ModelResponse:
        """使用系统提示词发送消息"""
        messages = self._build_messages(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        return await self.chat(messages, **kwargs)

    def is_available(self) -> bool:
        """检查 Ollama 服务和模型是否可用"""
        try:
            import asyncio

            async def _check():
                try:
                    session = await self._get_session()

                    # 检查 Ollama 服务是否运行
                    url = f"{self.config.base_url}/api/tags"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            return False

                        data = await resp.json()
                        models = data.get("models", [])

                        # 检查指定模型是否已安装
                        model_names = [m.get("name", "") for m in models]
                        available = any(
                            self.config.model_name in name
                            for name in model_names
                        )

                        if not available:
                            logger.warning(
                                f"Ollama: 模型 {self.config.model_name} 未安装. "
                                f"可用模型: {model_names}"
                            )
                            return False

                        return True

                except Exception as e:
                    logger.warning(f"Ollama: 可用性检查失败: {e}")
                    return False
                finally:
                    await self._close_session()

            loop = asyncio.get_event_loop()
            self._available = loop.run_until_complete(_check())
            return self._available

        except Exception as e:
            self._available = False
            logger.warning(f"Ollama: 可用性检查异常: {e}")
            return False

    async def is_available_async(self) -> bool:
        """异步检查模型是否可用"""
        try:
            session = await self._get_session()

            url = f"{self.config.base_url}/api/tags"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    self._available = False
                    return False

                data = await resp.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]

                self._available = any(
                    self.config.model_name in name
                    for name in model_names
                )
                return self._available

        except Exception as e:
            self._available = False
            logger.warning(f"Ollama: 异步可用性检查失败: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "provider": "ollama",
            "model": self.config.model_name,
            "available": self._available,
            "supported_models": self.SUPPORTED_MODELS,
            "base_url": self.config.base_url,
            "config": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "timeout": self.config.timeout,
            },
        }

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        列出 Ollama 中已安装的所有模型

        Returns:
            List[Dict]: 模型信息列表
        """
        try:
            session = await self._get_session()
            url = f"{self.config.base_url}/api/tags"

            async with session.get(url) as resp:
                if resp.status != 200:
                    raise AIModelError(
                        f"获取模型列表失败 (HTTP {resp.status})",
                        provider="Ollama"
                    )

                data = await resp.json()
                models = data.get("models", [])

                result = []
                for m in models:
                    result.append({
                        "name": m.get("name", ""),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                        "details": m.get("details", {}),
                    })

                logger.info(f"Ollama: 获取到 {len(result)} 个已安装模型")
                return result

        except AIModelError:
            raise
        except Exception as e:
            raise AIModelError(
                f"获取模型列表失败: {e}",
                provider="Ollama"
            )

    async def pull_model(self, model_name: str) -> bool:
        """
        拉取/下载模型

        Args:
            model_name: 模型名称

        Returns:
            bool: 是否成功
        """
        try:
            session = await self._get_session()
            url = f"{self.config.base_url}/api/pull"

            async with session.post(
                url,
                json={"name": model_name, "stream": False},
                timeout=aiohttp.ClientTimeout(total=600),  # 模型下载可能很慢
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Ollama: 拉取模型失败: {error_text}")
                    return False

                data = await resp.json()
                logger.info(f"Ollama: 模型 {model_name} 拉取成功")
                return True

        except Exception as e:
            logger.error(f"Ollama: 拉取模型异常: {e}")
            return False

    async def close(self):
        """清理资源"""
        await self._close_session()
        logger.info("Ollama: 资源已清理")
