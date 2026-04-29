"""千帆 (Qianfan) 适配器单元测试

测试 QianfanAdapter 的初始化、chat (httpx 直接调用)、
get_model_info 和 calculate_cost。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.ai_models.base import ModelConfig, ModelProvider, ModelResponse
from src.adapters.ai_models.qianfan_adapter import QianfanAdapter


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def qianfan_config():
    """创建千帆适配器配置。"""
    return ModelConfig(
        provider=ModelProvider.QIANFAN,
        model_name="ernie-bot-4",
        api_key="test-qianfan-key",
        base_url="https://aip.baidubce.com",
        temperature=0.7,
        max_tokens=4096,
        timeout=60,
        extra={"secret_key": "test-secret-key"},
    )


@pytest.fixture
def adapter(qianfan_config):
    """创建 QianfanAdapter 实例。"""
    return QianfanAdapter(qianfan_config)


# ===========================================================================
# 初始化测试
# ===========================================================================


class TestQianfanInitialization:
    """QianfanAdapter 初始化测试。"""

    def test_init(self, qianfan_config):
        """测试初始化 QianfanAdapter。"""
        adapter = QianfanAdapter(qianfan_config)

        assert adapter.config == qianfan_config
        assert adapter.provider == ModelProvider.QIANFAN
        assert adapter.model_name == "ernie-bot-4"
        assert adapter._available is False
        assert adapter._client is None

    def test_init_sets_default_base_url(self):
        """测试初始化时设置默认 base_url。"""
        config = ModelConfig(
            provider=ModelProvider.QIANFAN,
            model_name="ernie-bot-4",
            api_key="test-key",
        )
        adapter = QianfanAdapter(config)

        assert adapter.config.base_url == "https://aip.baidubce.com"

    def test_provider_name(self, adapter):
        """测试 PROVIDER_NAME 类属性。"""
        assert QianfanAdapter.PROVIDER_NAME == "Qianfan"
        assert adapter.PROVIDER_NAME == "Qianfan"

    def test_supported_models(self):
        """测试 SUPPORTED_MODELS 类属性。"""
        assert "ernie-bot-4" in QianfanAdapter.SUPPORTED_MODELS
        assert "ernie-bot-turbo" in QianfanAdapter.SUPPORTED_MODELS
        assert "ernie-speed-128k" in QianfanAdapter.SUPPORTED_MODELS
        assert "deepseek-v3" in QianfanAdapter.SUPPORTED_MODELS


# ===========================================================================
# chat() 方法测试 (使用 httpx 直接调用)
# ===========================================================================


class TestQianfanChat:
    """QianfanAdapter chat() 方法测试。"""

    @pytest.mark.asyncio
    async def test_chat_uses_httpx_directly(self, adapter):
        """测试 chat 使用 httpx 直接调用而非 OpenAI SDK。"""
        # 模拟 httpx 客户端
        mock_http_client = AsyncMock()
        mock_http_client.is_closed = False

        # 模拟获取 access_token 的响应
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test-token-123"}

        # 模拟聊天响应
        chat_response = MagicMock()
        chat_response.json.return_value = {
            "result": '{"action": "buy", "symbol": "AAPL"}',
            "finish_reason": "normal",
            "model": "ernie-bot-4",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }

        mock_http_client.post = AsyncMock(
            side_effect=[token_response, chat_response]
        )

        adapter._client = mock_http_client

        messages = [
            {"role": "user", "content": "Analyze AAPL"},
        ]

        response = await adapter.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == '{"action": "buy", "symbol": "AAPL"}'
        assert response.model == "ernie-bot-4"
        assert response.provider == ModelProvider.QIANFAN
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.finish_reason == "normal"

        # 验证 httpx 被调用（而非 openai SDK）
        assert mock_http_client.post.call_count == 2  # token + chat

    @pytest.mark.asyncio
    async def test_chat_with_api_error(self, adapter):
        """测试 API 返回错误时的处理。"""
        mock_http_client = AsyncMock()
        mock_http_client.is_closed = False

        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test-token"}

        error_response = MagicMock()
        error_response.json.return_value = {
            "error_code": 110,
            "error_msg": "Invalid access token",
        }

        mock_http_client.post = AsyncMock(
            side_effect=[token_response, error_response]
        )

        adapter._client = mock_http_client

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(Exception):
            await adapter.chat(messages)

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self, adapter):
        """测试 chat_with_system 构建正确的消息。"""
        mock_http_client = AsyncMock()
        mock_http_client.is_closed = False

        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test-token"}

        chat_response = MagicMock()
        chat_response.json.return_value = {
            "result": "Hold",
            "finish_reason": "normal",
            "model": "ernie-bot-4",
            "usage": {
                "prompt_tokens": 80,
                "completion_tokens": 10,
                "total_tokens": 90,
            },
        }

        mock_http_client.post = AsyncMock(
            side_effect=[token_response, chat_response]
        )

        adapter._client = mock_http_client

        response = await adapter.chat_with_system(
            system_prompt="You are a trading assistant.",
            user_message="Analyze AAPL",
        )

        assert isinstance(response, ModelResponse)

        # 验证发送的消息包含系统提示
        call_args = mock_http_client.post.call_args_list[1]
        import json
        request_body = json.loads(call_args.kwargs.get("json", "{}") or call_args[1].get("json", "{}"))
        messages = request_body.get("messages", [])
        assert any(m["role"] == "system" for m in messages)


# ===========================================================================
# is_available() 测试
# ===========================================================================


class TestQianfanIsAvailable:
    """QianfanAdapter is_available() 测试。"""

    def test_is_available_with_api_key(self, adapter):
        """测试设置了 api_key 时返回 True。"""
        result = adapter.is_available()
        assert result is True
        assert adapter._available is True

    def test_is_available_without_api_key(self):
        """测试未设置 api_key 时返回 False。"""
        config = ModelConfig(
            provider=ModelProvider.QIANFAN,
            model_name="ernie-bot-4",
            api_key=None,
        )
        adapter = QianfanAdapter(config)

        result = adapter.is_available()
        assert result is False


# ===========================================================================
# get_model_info() 测试
# ===========================================================================


class TestQianfanGetModelInfo:
    """QianfanAdapter get_model_info() 测试。"""

    def test_get_model_info_includes_base_url(self, adapter):
        """测试 get_model_info 包含 base_url (千帆特殊之处)。"""
        info = adapter.get_model_info()
        assert "base_url" in info
        assert info["base_url"] == "https://aip.baidubce.com"

    def test_get_model_info_structure(self, adapter):
        """测试返回正确的结构。"""
        info = adapter.get_model_info()

        assert isinstance(info, dict)
        assert info["provider"] == "Qianfan"
        assert info["model"] == "ernie-bot-4"
        assert info["supported_models"] == QianfanAdapter.SUPPORTED_MODELS
        assert "config" in info

    def test_get_model_info_supported_models(self, adapter):
        """测试返回正确的支持模型列表。"""
        info = adapter.get_model_info()
        models = info["supported_models"]
        assert "ernie-bot-4" in models
        assert "ernie-bot-4-8k" in models
        assert "ernie-bot-turbo" in models
        assert "ernie-speed-128k" in models
        assert "ernie-lite-8k" in models
        assert "deepseek-v3" in models


# ===========================================================================
# calculate_cost() 测试
# ===========================================================================


class TestQianfanCalculateCost:
    """QianfanAdapter calculate_cost() 测试。"""

    def test_calculate_cost_uses_default_pricing(self):
        """测试千帆模型使用默认定价。"""
        cost = QianfanAdapter.calculate_cost(
            model="ernie-bot-4",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # default: input=$1.0/M, output=$3.0/M
        assert cost == pytest.approx(1.0 + 3.0, rel=1e-6)

    def test_calculate_cost_small_tokens(self):
        """测试少量 token 的成本计算。"""
        cost = QianfanAdapter.calculate_cost(
            model="ernie-bot-4",
            input_tokens=200,
            output_tokens=300,
        )
        expected = (200 / 1_000_000) * 1.0 + (300 / 1_000_000) * 3.0
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_calculate_cost_zero_tokens(self):
        """测试零 token 的成本为 0。"""
        cost = QianfanAdapter.calculate_cost(
            model="ernie-bot-4",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0
