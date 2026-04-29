"""MiniMax 适配器单元测试

测试 MiniMaxAdapter 的初始化、get_model_info 和 calculate_cost。
"""

import pytest

from src.adapters.ai_models.base import ModelConfig, ModelProvider
from src.adapters.ai_models.minimax_adapter import MiniMaxAdapter


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def minimax_config():
    """创建 MiniMax 适配器配置。"""
    return ModelConfig(
        provider=ModelProvider.MINIMAX,
        model_name="abab6.5s-chat",
        api_key="test-minimax-key",
        temperature=0.7,
        max_tokens=4096,
        timeout=60,
    )


@pytest.fixture
def adapter(minimax_config):
    """创建 MiniMaxAdapter 实例。"""
    return MiniMaxAdapter(minimax_config)


# ===========================================================================
# 初始化测试
# ===========================================================================


class TestMiniMaxInitialization:
    """MiniMaxAdapter 初始化测试。"""

    def test_init(self, minimax_config):
        """测试初始化 MiniMaxAdapter。"""
        adapter = MiniMaxAdapter(minimax_config)

        assert adapter.config == minimax_config
        assert adapter.provider == ModelProvider.MINIMAX
        assert adapter.model_name == "abab6.5s-chat"
        assert adapter._available is False
        assert adapter._async_client is None

    def test_init_sets_default_base_url(self):
        """测试初始化时设置默认 base_url。"""
        config = ModelConfig(
            provider=ModelProvider.MINIMAX,
            model_name="abab6.5s-chat",
            api_key="test-key",
        )
        adapter = MiniMaxAdapter(config)

        assert adapter.config.base_url == "https://api.minimax.chat/v1"

    def test_init_preserves_custom_base_url(self):
        """测试保留自定义 base_url。"""
        config = ModelConfig(
            provider=ModelProvider.MINIMAX,
            model_name="abab6.5s-chat",
            api_key="test-key",
            base_url="https://custom.minimax.com/v1",
        )
        adapter = MiniMaxAdapter(config)

        assert adapter.config.base_url == "https://custom.minimax.com/v1"

    def test_provider_name(self, adapter):
        """测试 PROVIDER_NAME 类属性。"""
        assert MiniMaxAdapter.PROVIDER_NAME == "MiniMax"
        assert adapter.PROVIDER_NAME == "MiniMax"

    def test_supported_models(self):
        """测试 SUPPORTED_MODELS 类属性。"""
        assert "abab6.5s-chat" in MiniMaxAdapter.SUPPORTED_MODELS
        assert "abab6.5-chat" in MiniMaxAdapter.SUPPORTED_MODELS
        assert "abab6-chat" in MiniMaxAdapter.SUPPORTED_MODELS
        assert "MiniMax-Text-01" in MiniMaxAdapter.SUPPORTED_MODELS


# ===========================================================================
# get_model_info() 测试
# ===========================================================================


class TestMiniMaxGetModelInfo:
    """MiniMaxAdapter get_model_info() 测试。"""

    def test_get_model_info_returns_correct_models(self, adapter):
        """测试返回正确的模型列表。"""
        info = adapter.get_model_info()
        assert info["supported_models"] == MiniMaxAdapter.SUPPORTED_MODELS
        assert len(info["supported_models"]) == 4

    def test_get_model_info_structure(self, adapter):
        """测试返回正确的结构。"""
        info = adapter.get_model_info()

        assert isinstance(info, dict)
        assert info["provider"] == "MiniMax"
        assert info["model"] == "abab6.5s-chat"
        assert "config" in info
        assert info["config"]["temperature"] == 0.7


# ===========================================================================
# calculate_cost() 测试
# ===========================================================================


class TestMiniMaxCalculateCost:
    """MiniMaxAdapter calculate_cost() 测试。"""

    def test_calculate_cost_uses_default_pricing(self):
        """测试 MiniMax 模型使用默认定价。"""
        # MiniMax 模型不在 MODEL_PRICING 中，使用 default
        # default: input=$1.0/M, output=$3.0/M
        cost = MiniMaxAdapter.calculate_cost(
            model="abab6.5s-chat",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == pytest.approx(1.0 + 3.0, rel=1e-6)

    def test_calculate_cost_small_tokens(self):
        """测试少量 token 的成本计算。"""
        cost = MiniMaxAdapter.calculate_cost(
            model="abab6.5s-chat",
            input_tokens=500,
            output_tokens=1000,
        )
        expected = (500 / 1_000_000) * 1.0 + (1000 / 1_000_000) * 3.0
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_calculate_cost_zero_tokens(self):
        """测试零 token 的成本为 0。"""
        cost = MiniMaxAdapter.calculate_cost(
            model="abab6.5s-chat",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0
