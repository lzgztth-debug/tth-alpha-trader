"""Seed (豆包) 适配器单元测试

测试 SeedAdapter 的初始化、get_model_info 和 calculate_cost。
"""

import pytest

from src.adapters.ai_models.base import ModelConfig, ModelProvider
from src.adapters.ai_models.seed_adapter import SeedAdapter


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def seed_config():
    """创建 Seed 适配器配置。"""
    return ModelConfig(
        provider=ModelProvider.SEED,
        model_name="doubao-pro-32k",
        api_key="test-seed-key",
        temperature=0.7,
        max_tokens=4096,
        timeout=60,
    )


@pytest.fixture
def adapter(seed_config):
    """创建 SeedAdapter 实例。"""
    return SeedAdapter(seed_config)


# ===========================================================================
# 初始化测试
# ===========================================================================


class TestSeedInitialization:
    """SeedAdapter 初始化测试。"""

    def test_init_with_default_values(self, seed_config):
        """测试使用默认值初始化 SeedAdapter。"""
        adapter = SeedAdapter(seed_config)

        assert adapter.config == seed_config
        assert adapter.provider == ModelProvider.SEED
        assert adapter.model_name == "doubao-pro-32k"
        assert adapter._available is False
        assert adapter._async_client is None

    def test_init_sets_default_base_url(self):
        """测试初始化时设置默认 base_url。"""
        config = ModelConfig(
            provider=ModelProvider.SEED,
            model_name="doubao-pro-32k",
            api_key="test-key",
        )
        adapter = SeedAdapter(config)

        assert adapter.config.base_url == "https://ark.cn-beijing.volces.com/api/v3"

    def test_init_preserves_custom_base_url(self):
        """测试保留自定义 base_url。"""
        config = ModelConfig(
            provider=ModelProvider.SEED,
            model_name="doubao-pro-32k",
            api_key="test-key",
            base_url="https://custom.endpoint.com/v1",
        )
        adapter = SeedAdapter(config)

        assert adapter.config.base_url == "https://custom.endpoint.com/v1"

    def test_provider_name(self, adapter):
        """测试 PROVIDER_NAME 类属性。"""
        assert SeedAdapter.PROVIDER_NAME == "Seed"
        assert adapter.PROVIDER_NAME == "Seed"

    def test_supported_models(self):
        """测试 SUPPORTED_MODELS 类属性。"""
        assert "doubao-pro-32k" in SeedAdapter.SUPPORTED_MODELS
        assert "doubao-pro-128k" in SeedAdapter.SUPPORTED_MODELS
        assert "doubao-lite-32k" in SeedAdapter.SUPPORTED_MODELS
        assert "doubao-lite-128k" in SeedAdapter.SUPPORTED_MODELS


# ===========================================================================
# get_model_info() 测试
# ===========================================================================


class TestSeedGetModelInfo:
    """SeedAdapter get_model_info() 测试。"""

    def test_get_model_info_returns_correct_provider(self, adapter):
        """测试返回正确的 provider 名称。"""
        info = adapter.get_model_info()
        assert info["provider"] == "Seed"

    def test_get_model_info_returns_correct_models(self, adapter):
        """测试返回正确的模型列表。"""
        info = adapter.get_model_info()
        assert info["supported_models"] == SeedAdapter.SUPPORTED_MODELS
        assert "doubao-pro-32k" in info["supported_models"]
        assert "doubao-lite-128k" in info["supported_models"]

    def test_get_model_info_structure(self, adapter):
        """测试返回正确的结构。"""
        info = adapter.get_model_info()

        assert isinstance(info, dict)
        assert "provider" in info
        assert "model" in info
        assert "available" in info
        assert "supported_models" in info
        assert "config" in info
        assert info["model"] == "doubao-pro-32k"
        assert info["config"]["temperature"] == 0.7
        assert info["config"]["max_tokens"] == 4096


# ===========================================================================
# calculate_cost() 测试
# ===========================================================================


class TestSeedCalculateCost:
    """SeedAdapter calculate_cost() 测试。"""

    def test_calculate_cost_known_model(self):
        """测试已知模型的成本计算 (使用默认定价)。"""
        # Seed 模型不在 MODEL_PRICING 中，使用 default 定价
        # default: input=$1.0/M, output=$3.0/M
        cost = SeedAdapter.calculate_cost(
            model="doubao-pro-32k",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == pytest.approx(1.0 + 3.0, rel=1e-6)

    def test_calculate_cost_with_small_tokens(self):
        """测试少量 token 的成本计算。"""
        cost = SeedAdapter.calculate_cost(
            model="doubao-pro-32k",
            input_tokens=100,
            output_tokens=200,
        )
        expected = (100 / 1_000_000) * 1.0 + (200 / 1_000_000) * 3.0
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_calculate_cost_zero_tokens(self):
        """测试零 token 的成本为 0。"""
        cost = SeedAdapter.calculate_cost(
            model="doubao-pro-32k",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0
