"""DeepSeek 适配器单元测试

测试 DeepSeekAdapter 的正常行为和 deepseek-reasoner 模型的特殊处理。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.adapters.ai_models.base import ModelConfig, ModelProvider, ModelResponse
from src.adapters.ai_models.deepseek_adapter import DeepSeekAdapter


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def chat_config():
    """创建 deepseek-chat 模型配置。"""
    return ModelConfig(
        provider=ModelProvider.DEEPSEEK,
        model_name="deepseek-chat",
        api_key="test-deepseek-key",
        temperature=0.7,
        max_tokens=4096,
        timeout=60,
        top_p=0.9,
    )


@pytest.fixture
def reasoner_config():
    """创建 deepseek-reasoner 模型配置。"""
    return ModelConfig(
        provider=ModelProvider.DEEPSEEK,
        model_name="deepseek-reasoner",
        api_key="test-deepseek-key",
        temperature=0.7,
        max_tokens=4096,
        timeout=60,
        top_p=0.9,
    )


@pytest.fixture
def chat_adapter(chat_config):
    """创建 DeepSeekAdapter (chat 模型) 实例。"""
    return DeepSeekAdapter(chat_config)


@pytest.fixture
def reasoner_adapter(reasoner_config):
    """创建 DeepSeekAdapter (reasoner 模型) 实例。"""
    return DeepSeekAdapter(reasoner_config)


@pytest.fixture
def mock_chat_response():
    """创建 mock 的聊天完成响应。"""
    response = MagicMock()
    response.model = "deepseek-chat"

    choice = MagicMock()
    choice.message.content = '{"action": "buy", "symbol": "AAPL"}'
    choice.finish_reason = "stop"
    # deepseek-chat 没有 reasoning_content
    del choice.message.reasoning_content
    response.choices = [choice]

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    response.usage = usage

    return response


@pytest.fixture
def mock_reasoner_response():
    """创建 mock 的 reasoner 聊天完成响应。"""
    response = MagicMock()
    response.model = "deepseek-reasoner"

    choice = MagicMock()
    choice.message.content = '{"action": "sell", "symbol": "GOOGL"}'
    choice.finish_reason = "stop"
    choice.message.reasoning_content = "Let me analyze this step by step..."
    response.choices = [choice]

    usage = MagicMock()
    usage.prompt_tokens = 200
    usage.completion_tokens = 150
    response.usage = usage

    return response


# ===========================================================================
# deepseek-chat 模型测试 (正常行为)
# ===========================================================================


class TestDeepSeekChat:
    """deepseek-chat 模型正常行为测试。"""

    def test_init_chat_model(self, chat_adapter):
        """测试初始化 deepseek-chat 模型。"""
        assert chat_adapter.model_name == "deepseek-chat"
        assert chat_adapter.provider == ModelProvider.DEEPSEEK
        assert chat_adapter.config.temperature == 0.7
        assert chat_adapter.config.top_p == 0.9

    def test_provider_name(self, chat_adapter):
        """测试 PROVIDER_NAME。"""
        assert DeepSeekAdapter.PROVIDER_NAME == "DeepSeek"

    def test_supported_models(self):
        """测试支持的模型列表。"""
        assert "deepseek-chat" in DeepSeekAdapter.SUPPORTED_MODELS
        assert "deepseek-reasoner" in DeepSeekAdapter.SUPPORTED_MODELS

    @pytest.mark.asyncio
    async def test_chat_includes_temperature_and_top_p(
        self, chat_adapter, mock_chat_response
    ):
        """测试 deepseek-chat 请求包含 temperature 和 top_p。"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )
        chat_adapter._async_client = mock_client

        messages = [{"role": "user", "content": "Hello"}]
        await chat_adapter.chat(messages)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" in call_kwargs
        assert call_kwargs["temperature"] == 0.7
        assert "top_p" in call_kwargs
        assert call_kwargs["top_p"] == 0.9

    @pytest.mark.asyncio
    async def test_chat_response(self, chat_adapter, mock_chat_response):
        """测试 deepseek-chat 返回正确的响应。"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )
        chat_adapter._async_client = mock_client

        messages = [{"role": "user", "content": "Hello"}]
        response = await chat_adapter.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == '{"action": "buy", "symbol": "AAPL"}'
        assert response.model == "deepseek-chat"
        assert response.provider == ModelProvider.DEEPSEEK
        assert response.input_tokens == 100
        assert response.output_tokens == 50


# ===========================================================================
# deepseek-reasoner 模型测试 (特殊处理)
# ===========================================================================


class TestDeepSeekReasoner:
    """deepseek-reasoner 模型特殊处理测试。"""

    def test_init_reasoner_model(self, reasoner_adapter):
        """测试初始化 deepseek-reasoner 模型。"""
        assert reasoner_adapter.model_name == "deepseek-reasoner"
        assert reasoner_adapter.config.temperature == 0.7
        assert reasoner_adapter.config.top_p == 0.9

    @pytest.mark.asyncio
    async def test_reasoner_removes_temperature_and_top_p(
        self, reasoner_adapter, mock_reasoner_response
    ):
        """测试 deepseek-reasoner 请求自动移除 temperature 和 top_p。"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_reasoner_response
        )
        reasoner_adapter._async_client = mock_client

        messages = [{"role": "user", "content": "Analyze deeply"}]
        await reasoner_adapter.chat(messages)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        # deepseek-reasoner 不支持 temperature 和 top_p，应被移除
        assert "temperature" not in call_kwargs
        assert "top_p" not in call_kwargs

    @pytest.mark.asyncio
    async def test_reasoner_captures_reasoning_content(
        self, reasoner_adapter, mock_reasoner_response
    ):
        """测试 deepseek-reasoner 捕获 reasoning_content。"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_reasoner_response
        )
        reasoner_adapter._async_client = mock_client

        messages = [{"role": "user", "content": "Analyze"}]
        response = await reasoner_adapter.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.raw_response is not None
        assert "reasoning_content" in response.raw_response
        assert response.raw_response["reasoning_content"] == "Let me analyze this step by step..."

    @pytest.mark.asyncio
    async def test_reasoner_response_content(self, reasoner_adapter, mock_reasoner_response):
        """测试 deepseek-reasoner 返回正确的 content。"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_reasoner_response
        )
        reasoner_adapter._async_client = mock_client

        messages = [{"role": "user", "content": "Hello"}]
        response = await reasoner_adapter.chat(messages)

        assert response.content == '{"action": "sell", "symbol": "GOOGL"}'
        assert response.model == "deepseek-reasoner"
        assert response.input_tokens == 200
        assert response.output_tokens == 150


# ===========================================================================
# calculate_cost() 测试 (chat vs reasoner 定价差异)
# ===========================================================================


class TestDeepSeekCalculateCost:
    """DeepSeekAdapter calculate_cost() 测试。"""

    def test_calculate_cost_chat_model(self):
        """测试 deepseek-chat 的成本计算。"""
        # deepseek-chat: input=$0.14/M, output=$0.28/M
        cost = DeepSeekAdapter.calculate_cost(
            model="deepseek-chat",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == pytest.approx(0.14 + 0.28, rel=1e-6)

    def test_calculate_cost_reasoner_model(self):
        """测试 deepseek-reasoner 的成本计算。"""
        # deepseek-reasoner: input=$0.55/M, output=$2.19/M
        cost = DeepSeekAdapter.calculate_cost(
            model="deepseek-reasoner",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == pytest.approx(0.55 + 2.19, rel=1e-6)

    def test_calculate_cost_reasoner_more_expensive_than_chat(self):
        """测试 reasoner 比 chat 更贵。"""
        tokens = 1_000_000
        chat_cost = DeepSeekAdapter.calculate_cost(
            model="deepseek-chat",
            input_tokens=tokens,
            output_tokens=tokens,
        )
        reasoner_cost = DeepSeekAdapter.calculate_cost(
            model="deepseek-reasoner",
            input_tokens=tokens,
            output_tokens=tokens,
        )
        assert reasoner_cost > chat_cost

    def test_calculate_cost_small_tokens(self):
        """测试少量 token 的成本计算。"""
        cost = DeepSeekAdapter.calculate_cost(
            model="deepseek-chat",
            input_tokens=100,
            output_tokens=200,
        )
        expected = (100 / 1_000_000) * 0.14 + (200 / 1_000_000) * 0.28
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_calculate_cost_zero_tokens(self):
        """测试零 token 的成本为 0。"""
        cost = DeepSeekAdapter.calculate_cost(
            model="deepseek-chat",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0
