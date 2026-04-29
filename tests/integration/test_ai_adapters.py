"""AI 模型适配器集成测试

使用 mock 测试 OpenAI/Claude/Qwen/DeepSeek/Ollama 适配器的基本功能。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.ai_models.base import (
    BaseAIModelAdapter,
    ModelConfig,
    ModelProvider,
    ModelResponse,
    AIModelError,
    AIModelConnectionError,
)
from src.adapters.ai_models.openai_adapter import OpenAIAdapter
from src.adapters.ai_models.claude_adapter import ClaudeAdapter
from src.adapters.ai_models.qwen_adapter import QwenAdapter
from src.adapters.ai_models.deepseek_adapter import DeepSeekAdapter
from src.adapters.ai_models.ollama_adapter import OllamaAdapter


# ===========================================================================
# 通用测试辅助
# ===========================================================================


def make_mock_response(
    content: str = "测试响应",
    model: str = "test-model",
    provider: ModelProvider = ModelProvider.OPENAI,
) -> ModelResponse:
    """创建模拟的 ModelResponse。"""
    return ModelResponse(
        content=content,
        model=model,
        provider=provider,
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        latency_ms=100.0,
        finish_reason="stop",
    )


# ===========================================================================
# OpenAI 适配器测试
# ===========================================================================


class TestOpenAIAdapter:
    """OpenAI 适配器测试。"""

    @pytest.fixture
    def config(self):
        return ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="gpt-4o",
            api_key="sk-test-key",
            temperature=0.7,
            max_tokens=4096,
        )

    @pytest.fixture
    def adapter(self, config):
        return OpenAIAdapter(config)

    def test_init(self, adapter):
        """测试初始化。"""
        assert adapter.provider == ModelProvider.OPENAI
        assert adapter.model_name == "gpt-4o"
        assert adapter.config.api_key == "sk-test-key"

    @pytest.mark.asyncio
    async def test_chat_with_system(self, adapter):
        """测试 chat_with_system 方法。"""
        mock_response = make_mock_response(
            content='{"action": "buy", "symbol": "AAPL"}',
            model="gpt-4o",
            provider=ModelProvider.OPENAI,
        )

        adapter._async_client = MagicMock()
        adapter._async_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"action": "buy", "symbol": "AAPL"}'), finish_reason="stop")],
                model="gpt-4o",
                usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )
        )

        result = await adapter.chat_with_system(
            system_prompt="你是交易助手",
            user_message="分析AAPL",
        )
        assert result.content == '{"action": "buy", "symbol": "AAPL"}'
        assert result.provider == ModelProvider.OPENAI
        assert result.usage["total_tokens"] == 30

    def test_is_available_no_key(self):
        """测试无 API Key 时不可用。"""
        config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="gpt-4o",
            api_key=None,
        )
        adapter = OpenAIAdapter(config)
        assert adapter.is_available() is False

    def test_get_model_info(self, adapter):
        """测试获取模型信息。"""
        info = adapter.get_model_info()
        assert info["provider"] == "openai"
        assert info["model"] == "gpt-4o"
        assert "gpt-4o" in info["supported_models"]

    def test_repr(self, adapter):
        """测试字符串表示。"""
        repr_str = repr(adapter)
        assert "OpenAIAdapter" in repr_str
        assert "gpt-4o" in repr_str


# ===========================================================================
# Claude 适配器测试
# ===========================================================================


class TestClaudeAdapter:
    """Claude 适配器测试。"""

    @pytest.fixture
    def config(self):
        return ModelConfig(
            provider=ModelProvider.CLAUDE,
            model_name="claude-sonnet-4-20250514",
            api_key="sk-ant-test-key",
            temperature=0.7,
            max_tokens=4096,
        )

    @pytest.fixture
    def adapter(self, config):
        return ClaudeAdapter(config)

    def test_init(self, adapter):
        """测试初始化。"""
        assert adapter.provider == ModelProvider.CLAUDE
        assert adapter.model_name == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_chat_with_system(self, adapter):
        """测试 chat_with_system 方法。"""
        mock_content_block = MagicMock()
        mock_content_block.text = "建议持有AAPL"

        adapter._async_client = MagicMock()
        adapter._async_client.messages.create = AsyncMock(
            return_value=MagicMock(
                content=[mock_content_block],
                model="claude-sonnet-4-20250514",
                stop_reason="end_turn",
                usage=MagicMock(input_tokens=15, output_tokens=25),
            )
        )

        result = await adapter.chat_with_system(
            system_prompt="你是交易助手",
            user_message="分析AAPL",
        )
        assert result.content == "建议持有AAPL"
        assert result.provider == ModelProvider.CLAUDE
        assert result.usage["total_tokens"] == 40

    def test_is_available_no_key(self):
        """测试无 API Key 时不可用。"""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE,
            model_name="claude-sonnet-4-20250514",
            api_key=None,
        )
        adapter = ClaudeAdapter(config)
        assert adapter.is_available() is False

    def test_get_model_info(self, adapter):
        """测试获取模型信息。"""
        info = adapter.get_model_info()
        assert info["provider"] == "claude"
        assert info["model"] == "claude-sonnet-4-20250514"
        assert len(info["supported_models"]) > 0


# ===========================================================================
# Qwen 适配器测试
# ===========================================================================


class TestQwenAdapter:
    """通义千问适配器测试。"""

    @pytest.fixture
    def config(self):
        return ModelConfig(
            provider=ModelProvider.QWEN,
            model_name="qwen-max",
            api_key="sk-dashscope-test",
            temperature=0.7,
            max_tokens=4096,
        )

    @pytest.fixture
    def adapter(self, config):
        return QwenAdapter(config)

    def test_init(self, adapter):
        """测试初始化。"""
        assert adapter.provider == ModelProvider.QWEN
        assert adapter.model_name == "qwen-max"

    @pytest.mark.asyncio
    async def test_chat_with_system(self, adapter):
        """测试 chat_with_system 方法。"""
        # Mock dashscope SDK
        mock_response = MagicMock()
        mock_response.output.choices = [
            MagicMock(
                message=MagicMock(content="建议买入"),
                finish_reason="stop",
            )
        ]
        mock_response.usage = MagicMock(
            input_tokens=10, output_tokens=20, total_tokens=30,
        )

        adapter._generation = MagicMock()
        adapter._generation.call = MagicMock(return_value=mock_response)
        # Mock _init_client 以避免实际导入 dashscope
        adapter._init_client = MagicMock()

        result = await adapter.chat_with_system(
            system_prompt="你是交易助手",
            user_message="分析市场",
        )
        assert result.content == "建议买入"
        assert result.provider == ModelProvider.QWEN

    def test_get_model_info(self, adapter):
        """测试获取模型信息。"""
        info = adapter.get_model_info()
        assert info["provider"] == "qwen"
        assert info["model"] == "qwen-max"


# ===========================================================================
# DeepSeek 适配器测试
# ===========================================================================


class TestDeepSeekAdapter:
    """DeepSeek 适配器测试。"""

    @pytest.fixture
    def config(self):
        return ModelConfig(
            provider=ModelProvider.DEEPSEEK,
            model_name="deepseek-chat",
            api_key="sk-deepseek-test",
            base_url="https://api.deepseek.com/v1",
            temperature=0.7,
            max_tokens=4096,
        )

    @pytest.fixture
    def adapter(self, config):
        return DeepSeekAdapter(config)

    def test_init(self, adapter):
        """测试初始化。"""
        assert adapter.provider == ModelProvider.DEEPSEEK
        assert adapter.model_name == "deepseek-chat"
        assert adapter.config.base_url == "https://api.deepseek.com/v1"

    @pytest.mark.asyncio
    async def test_chat_with_system(self, adapter):
        """测试 chat_with_system 方法。"""
        adapter._async_client = MagicMock()
        adapter._async_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content='{"action": "hold"}'),
                    finish_reason="stop",
                )],
                model="deepseek-chat",
                usage=MagicMock(prompt_tokens=10, completion_tokens=15, total_tokens=25),
            )
        )

        result = await adapter.chat_with_system(
            system_prompt="你是交易助手",
            user_message="分析",
        )
        assert result.content == '{"action": "hold"}'
        assert result.provider == ModelProvider.DEEPSEEK

    def test_get_model_info(self, adapter):
        """测试获取模型信息。"""
        info = adapter.get_model_info()
        assert info["provider"] == "deepseek"
        assert info["model"] == "deepseek-chat"


# ===========================================================================
# Ollama 适配器测试
# ===========================================================================


class TestOllamaAdapter:
    """Ollama 本地模型适配器测试。"""

    @pytest.fixture
    def config(self):
        return ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_name="llama3",
            base_url="http://localhost:11434",
            temperature=0.7,
            max_tokens=4096,
            timeout=120,
        )

    @pytest.fixture
    def adapter(self, config):
        return OllamaAdapter(config)

    def test_init(self, adapter):
        """测试初始化。"""
        assert adapter.provider == ModelProvider.OLLAMA
        assert adapter.model_name == "llama3"
        assert adapter.config.base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_chat_with_system(self, adapter):
        """测试 chat_with_system 方法。"""
        import asyncio
        import json

        mock_ollama_response = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "建议观望"},
            "done": True,
            "total_duration": 500_000_000,
            "eval_count": 20,
            "prompt_eval_count": 50,
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_ollama_response)
        mock_response.text = AsyncMock(return_value=json.dumps(mock_ollama_response))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await adapter.chat_with_system(
                system_prompt="你是交易助手",
                user_message="分析",
            )
        assert result.content == "建议观望"
        assert result.provider == ModelProvider.OLLAMA

    def test_is_available(self, adapter):
        """测试可用性检查。"""
        mock_get_response = AsyncMock()
        mock_get_response.status = 200
        mock_get_response.json = AsyncMock(return_value={"models": [{"name": "llama3"}]})
        mock_get_response.__aenter__ = AsyncMock(return_value=mock_get_response)
        mock_get_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_get_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            available = adapter.is_available()
        assert available is True

    def test_get_model_info(self, adapter):
        """测试获取模型信息。"""
        info = adapter.get_model_info()
        assert info["provider"] == "ollama"
        assert info["model"] == "llama3"


# ===========================================================================
# 通用接口测试
# ===========================================================================


class TestCommonInterface:
    """测试所有适配器遵循统一接口。"""

    @pytest.mark.parametrize("adapter_class, config_kwargs", [
        (OpenAIAdapter, {"provider": ModelProvider.OPENAI, "model_name": "gpt-4o", "api_key": "test"}),
        (ClaudeAdapter, {"provider": ModelProvider.CLAUDE, "model_name": "claude-sonnet-4-20250514", "api_key": "test"}),
        (QwenAdapter, {"provider": ModelProvider.QWEN, "model_name": "qwen-max", "api_key": "test"}),
        (DeepSeekAdapter, {"provider": ModelProvider.DEEPSEEK, "model_name": "deepseek-chat", "api_key": "test"}),
        (OllamaAdapter, {"provider": ModelProvider.OLLAMA, "model_name": "llama3", "base_url": "http://localhost:11434"}),
    ])
    def test_adapter_properties(self, adapter_class, config_kwargs):
        """测试所有适配器的公共属性。"""
        config = ModelConfig(**config_kwargs)
        adapter = adapter_class(config)

        assert hasattr(adapter, "provider")
        assert hasattr(adapter, "model_name")
        assert hasattr(adapter, "is_available")
        assert hasattr(adapter, "get_model_info")
        assert hasattr(adapter, "chat")
        assert hasattr(adapter, "chat_with_system")

    @pytest.mark.parametrize("adapter_class, config_kwargs", [
        (OpenAIAdapter, {"provider": ModelProvider.OPENAI, "model_name": "gpt-4o", "api_key": "test"}),
        (ClaudeAdapter, {"provider": ModelProvider.CLAUDE, "model_name": "claude-sonnet-4-20250514", "api_key": "test"}),
        (QwenAdapter, {"provider": ModelProvider.QWEN, "model_name": "qwen-max", "api_key": "test"}),
        (DeepSeekAdapter, {"provider": ModelProvider.DEEPSEEK, "model_name": "deepseek-chat", "api_key": "test"}),
        (OllamaAdapter, {"provider": ModelProvider.OLLAMA, "model_name": "llama3", "base_url": "http://localhost:11434"}),
    ])
    def test_get_model_info_returns_dict(self, adapter_class, config_kwargs):
        """测试所有适配器的 get_model_info 返回字典。"""
        config = ModelConfig(**config_kwargs)
        adapter = adapter_class(config)
        info = adapter.get_model_info()
        assert isinstance(info, dict)
        assert "provider" in info
        assert "model" in info
        assert "available" in info
        assert "config" in info
