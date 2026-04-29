"""OpenAI 兼容适配器基类单元测试

测试 OpenAICompatibleAdapter 的初始化、chat、chat_with_system、
is_available、calculate_cost 和 get_model_info 方法。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelConfig,
    ModelProvider,
    ModelResponse,
)


# ===========================================================================
# 测试用子类 (OpenAICompatibleAdapter 是抽象基类的实现)
# ===========================================================================


class TestOpenAICompatibleAdapter(OpenAICompatibleAdapter):
    """用于测试的 OpenAICompatibleAdapter 子类。"""

    SUPPORTED_MODELS = ["test-model-v1", "test-model-v2"]
    DEFAULT_BASE_URL = "https://api.test.example.com/v1"
    PROVIDER_NAME = "TestProvider"


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def model_config():
    """创建测试用模型配置。"""
    return ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="test-model-v1",
        api_key="test-api-key-12345",
        base_url="https://api.test.example.com/v1",
        temperature=0.7,
        max_tokens=2048,
        timeout=30,
        top_p=0.9,
    )


@pytest.fixture
def adapter(model_config):
    """创建测试适配器实例。"""
    return TestOpenAICompatibleAdapter(model_config)


@pytest.fixture
def mock_async_client():
    """创建 mock 的 AsyncOpenAI 客户端。"""
    mock_client = AsyncMock()
    return mock_client


@pytest.fixture
def mock_chat_response():
    """创建 mock 的聊天完成响应。"""
    response = MagicMock()
    response.model = "test-model-v1"

    choice = MagicMock()
    choice.message.content = '{"action": "buy", "symbol": "AAPL"}'
    choice.finish_reason = "stop"
    response.choices = [choice]

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    response.usage = usage

    return response


# ===========================================================================
# 初始化测试
# ===========================================================================


class TestInitialization:
    """初始化测试。"""

    def test_init_with_config(self, model_config):
        """测试使用配置初始化适配器。"""
        adapter = TestOpenAICompatibleAdapter(model_config)
        assert adapter.config == model_config
        assert adapter.provider == ModelProvider.OPENAI
        assert adapter.model_name == "test-model-v1"
        assert adapter._available is False
        assert adapter._async_client is None
        assert adapter._client is None

    def test_init_sets_default_base_url(self):
        """测试初始化时设置默认 base_url。"""
        config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="test-model-v1",
            api_key="test-key",
            # 不设置 base_url
        )
        adapter = TestOpenAICompatibleAdapter(config)
        assert adapter.config.base_url == "https://api.test.example.com/v1"

    def test_init_preserves_custom_base_url(self, model_config):
        """测试初始化时保留自定义 base_url。"""
        adapter = TestOpenAICompatibleAdapter(model_config)
        assert adapter.config.base_url == "https://api.test.example.com/v1"

    def test_repr(self, adapter):
        """测试 __repr__ 方法。"""
        repr_str = repr(adapter)
        assert "TestOpenAICompatibleAdapter" in repr_str
        assert "provider=openai" in repr_str
        assert "model=test-model-v1" in repr_str


# ===========================================================================
# chat() 方法测试
# ===========================================================================


class TestChat:
    """chat() 方法测试。"""

    @pytest.mark.asyncio
    async def test_chat_success(self, adapter, mock_async_client, mock_chat_response):
        """测试成功的 chat 调用。"""
        adapter._async_client = mock_async_client
        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )

        messages = [
            {"role": "system", "content": "You are a trading assistant."},
            {"role": "user", "content": "Analyze AAPL"},
        ]

        response = await adapter.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == '{"action": "buy", "symbol": "AAPL"}'
        assert response.model == "test-model-v1"
        assert response.provider == ModelProvider.OPENAI
        assert response.finish_reason == "stop"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.latency_ms > 0

        # 验证调用参数
        mock_async_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_async_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "test-model-v1"
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["top_p"] == 0.9

    @pytest.mark.asyncio
    async def test_chat_with_custom_params(self, adapter, mock_async_client, mock_chat_response):
        """测试使用自定义参数的 chat 调用。"""
        adapter._async_client = mock_async_client
        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )

        messages = [{"role": "user", "content": "Hello"}]
        response = await adapter.chat(
            messages,
            temperature=0.5,
            max_tokens=1024,
            top_p=0.8,
        )

        assert isinstance(response, ModelResponse)

        call_kwargs = mock_async_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 1024
        assert call_kwargs["top_p"] == 0.8

    @pytest.mark.asyncio
    async def test_chat_auto_init_client(self, adapter, mock_chat_response):
        """测试 chat 自动初始化客户端。"""
        mock_client_instance = AsyncMock()
        mock_client_instance.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )

        with patch.object(adapter, "_init_client") as mock_init:
            adapter._async_client = mock_client_instance
            # 手动设置客户端，模拟 _init_client 的效果
            mock_init.side_effect = lambda: setattr(
                adapter, "_async_client", mock_client_instance
            )

            messages = [{"role": "user", "content": "Hello"}]
            await adapter.chat(messages)

            # 如果 _async_client 已经设置，_init_client 不应被调用
            mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_with_empty_choices(self, adapter, mock_async_client):
        """测试空 choices 响应的处理。"""
        response = MagicMock()
        response.model = "test-model-v1"
        response.choices = []
        response.usage = None

        adapter._async_client = mock_async_client
        mock_async_client.chat.completions.create = AsyncMock(return_value=response)

        messages = [{"role": "user", "content": "Hello"}]
        result = await adapter.chat(messages)

        assert result.content == ""
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    @pytest.mark.asyncio
    async def test_chat_with_no_usage(self, adapter, mock_async_client):
        """测试无 usage 信息的响应处理。"""
        response = MagicMock()
        response.model = "test-model-v1"
        response.choices = []
        response.usage = None

        adapter._async_client = mock_async_client
        mock_async_client.chat.completions.create = AsyncMock(return_value=response)

        messages = [{"role": "user", "content": "Hello"}]
        result = await adapter.chat(messages)

        assert result.usage == {}
        assert result.cost == 0.0


# ===========================================================================
# chat_with_system() 方法测试
# ===========================================================================


class TestChatWithSystem:
    """chat_with_system() 方法测试。"""

    @pytest.mark.asyncio
    async def test_chat_with_system(self, adapter, mock_async_client, mock_chat_response):
        """测试使用系统提示词的 chat 调用。"""
        adapter._async_client = mock_async_client
        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )

        response = await adapter.chat_with_system(
            system_prompt="You are a trading assistant.",
            user_message="Analyze AAPL",
        )

        assert isinstance(response, ModelResponse)

        # 验证发送的消息包含系统提示和用户消息
        call_kwargs = mock_async_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a trading assistant."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Analyze AAPL"

    @pytest.mark.asyncio
    async def test_chat_with_system_passes_kwargs(self, adapter, mock_async_client, mock_chat_response):
        """测试 chat_with_system 传递额外参数。"""
        adapter._async_client = mock_async_client
        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_chat_response
        )

        await adapter.chat_with_system(
            system_prompt="System prompt",
            user_message="User message",
            temperature=0.3,
            max_tokens=512,
        )

        call_kwargs = mock_async_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 512


# ===========================================================================
# is_available() 方法测试
# ===========================================================================


class TestIsAvailable:
    """is_available() 方法测试。"""

    def test_is_available_with_api_key(self, adapter):
        """测试设置了 api_key 时 is_available 返回 True。"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        adapter._client = mock_client

        result = adapter.is_available()
        assert result is True
        assert adapter._available is True

    def test_is_available_without_api_key(self):
        """测试未设置 api_key 时 is_available 返回 False。"""
        config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="test-model-v1",
            api_key=None,
        )
        adapter = TestOpenAICompatibleAdapter(config)

        result = adapter.is_available()
        assert result is False

    def test_is_available_with_empty_api_key(self):
        """测试空 api_key 时 is_available 返回 False。"""
        config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="test-model-v1",
            api_key="",
        )
        adapter = TestOpenAICompatibleAdapter(config)

        result = adapter.is_available()
        assert result is False

    def test_is_available_on_client_error(self, adapter):
        """测试客户端异常时 is_available 返回 False。"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection error")

        adapter._client = mock_client

        result = adapter.is_available()
        assert result is False
        assert adapter._available is False


# ===========================================================================
# calculate_cost() 方法测试
# ===========================================================================


class TestCalculateCost:
    """calculate_cost() 方法测试。"""

    def test_calculate_cost_known_model(self):
        """测试已知模型的成本计算。"""
        # gpt-4o: input=$2.5/M, output=$10.0/M
        cost = OpenAICompatibleAdapter.calculate_cost(
            model="gpt-4o",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == pytest.approx(2.5 + 10.0, rel=1e-6)

    def test_calculate_cost_default_model(self):
        """测试未知模型使用默认定价。"""
        # default: input=$1.0/M, output=$3.0/M
        cost = OpenAICompatibleAdapter.calculate_cost(
            model="unknown-model",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == pytest.approx(1.0 + 3.0, rel=1e-6)

    def test_calculate_cost_zero_tokens(self):
        """测试零 token 的成本计算。"""
        cost = OpenAICompatibleAdapter.calculate_cost(
            model="gpt-4o",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0

    def test_calculate_cost_small_tokens(self):
        """测试少量 token 的成本计算。"""
        # gpt-4o-mini: input=$0.15/M, output=$0.6/M
        cost = OpenAICompatibleAdapter.calculate_cost(
            model="gpt-4o-mini",
            input_tokens=100,
            output_tokens=200,
        )
        expected = (100 / 1_000_000) * 0.15 + (200 / 1_000_000) * 0.6
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_calculate_cost_deepseek(self):
        """测试 DeepSeek 模型的成本计算。"""
        # deepseek-chat: input=$0.14/M, output=$0.28/M
        cost = OpenAICompatibleAdapter.calculate_cost(
            model="deepseek-chat",
            input_tokens=500_000,
            output_tokens=500_000,
        )
        expected = (500_000 / 1_000_000) * 0.14 + (500_000 / 1_000_000) * 0.28
        assert cost == pytest.approx(expected, rel=1e-9)


# ===========================================================================
# get_model_info() 方法测试
# ===========================================================================


class TestGetModelInfo:
    """get_model_info() 方法测试。"""

    def test_get_model_info_structure(self, adapter):
        """测试 get_model_info 返回正确的结构。"""
        info = adapter.get_model_info()

        assert isinstance(info, dict)
        assert info["provider"] == "TestProvider"
        assert info["model"] == "test-model-v1"
        assert info["available"] is False
        assert info["supported_models"] == ["test-model-v1", "test-model-v2"]
        assert "config" in info
        assert info["config"]["temperature"] == 0.7
        assert info["config"]["max_tokens"] == 2048
        assert info["config"]["timeout"] == 30

    def test_get_model_info_includes_base_url(self, adapter):
        """测试 get_model_info 包含 base_url。"""
        info = adapter.get_model_info()
        assert "base_url" in info
        assert info["base_url"] == "https://api.test.example.com/v1"

    def test_get_model_info_without_base_url(self):
        """测试无 base_url 时 get_model_info 不包含该字段。"""
        config = ModelConfig(
            provider=ModelProvider.OPENAI,
            model_name="test-model-v1",
            api_key="test-key",
            base_url=None,
        )
        adapter = TestOpenAICompatibleAdapter(config)
        # 初始化后 base_url 会被设为 DEFAULT_BASE_URL
        info = adapter.get_model_info()
        assert "base_url" in info

    def test_get_model_info_after_availability_check(self, adapter):
        """测试可用性检查后 get_model_info 反映最新状态。"""
        mock_client = MagicMock()
        adapter._client = mock_client

        adapter.is_available()
        info = adapter.get_model_info()
        assert info["available"] is True


# ===========================================================================
# _build_messages() 方法测试
# ===========================================================================


class TestBuildMessages:
    """_build_messages() 方法测试。"""

    def test_build_messages_with_system_and_user(self, adapter):
        """测试构建包含系统提示和用户消息的消息列表。"""
        messages = adapter._build_messages(
            system_prompt="System",
            user_message="User",
        )
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "System"}
        assert messages[1] == {"role": "user", "content": "User"}

    def test_build_messages_with_existing_messages(self, adapter):
        """测试构建包含已有消息的消息列表。"""
        existing = [{"role": "assistant", "content": "Previous"}]
        messages = adapter._build_messages(
            system_prompt="System",
            user_message="User",
            messages=existing,
        )
        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": "System"}
        assert messages[1] == {"role": "assistant", "content": "Previous"}
        assert messages[2] == {"role": "user", "content": "User"}

    def test_build_messages_empty(self, adapter):
        """测试空参数构建消息列表。"""
        messages = adapter._build_messages()
        assert messages == []
