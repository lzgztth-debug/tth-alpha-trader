"""AI 决策 API 路由单元测试

测试 POST /api/v1/ai/decide、POST /api/v1/ai/decide/multi、
GET /api/v1/ai/models 和 GET /api/v1/ai/providers。
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ai import router as ai_router
from src.models.decision import Decision, DecisionAction


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def app():
    """创建测试用 FastAPI 应用。"""
    application = FastAPI()
    application.include_router(ai_router)
    return application


@pytest.fixture
def client(app):
    """创建测试客户端。"""
    return TestClient(app)


@pytest.fixture
def mock_agent_engine():
    """创建 mock 的 AIAgentEngine。"""
    engine = MagicMock()

    # 模拟 make_decision 返回
    decision = Decision(
        decision_id=str(uuid.uuid4()),
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        model="gpt-4o",
        provider="openai",
        action=DecisionAction.BUY,
        symbol="AAPL",
        quantity=100,
        price=150.0,
        confidence=0.85,
        reasoning="均线金叉，MACD向上",
        latency_ms=1200,
    )
    engine.make_decision = AsyncMock(return_value=decision)

    # 模拟 make_decision_multi_model 返回
    multi_decision = Decision(
        decision_id=str(uuid.uuid4()),
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        model="multi_model",
        provider="multi",
        action=DecisionAction.BUY,
        symbol="AAPL",
        quantity=100,
        price=150.0,
        confidence=0.75,
        reasoning="[多模型-多数投票] 动作=buy, 票数=3/3",
        raw_response=json.dumps([
            {"model": "gpt-4o", "action": "buy", "confidence": 0.85, "symbol": "AAPL"},
        ]),
        latency_ms=2500,
    )
    engine.make_decision_multi_model = AsyncMock(return_value=multi_decision)

    # 模拟 list_models 返回
    engine.list_models = MagicMock(return_value=[
        {"name": "gpt-4o", "provider": "openai", "model": "gpt-4o", "available": "True"},
        {"name": "deepseek-chat", "provider": "deepseek", "model": "deepseek-chat", "available": "True"},
    ])

    return engine


@pytest.fixture
def client_with_engine(app, mock_agent_engine):
    """创建带 mock agent_engine 的测试客户端。"""
    app.state.agent_engine = mock_agent_engine
    return TestClient(app)


# ===========================================================================
# POST /api/v1/ai/decide 测试
# ===========================================================================


class TestDecideEndpoint:
    """POST /api/v1/ai/decide 测试。"""

    def test_decide_success(self, client_with_engine, mock_agent_engine):
        """测试成功的单模型决策。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide",
            json={
                "symbol": "AAPL",
                "model_name": "gpt-4o",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["decision"] is not None
        assert data["decision"]["action"] == "buy"
        assert data["decision"]["symbol"] == "AAPL"
        assert data["decision"]["model"] == "gpt-4o"
        assert data["decision"]["confidence"] == 0.85
        assert data["decision"]["reasoning"] == "均线金叉，MACD向上"

        mock_agent_engine.make_decision.assert_called_once()

    def test_decide_with_account_id(self, client_with_engine, mock_agent_engine):
        """测试带账户 ID 的决策。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide",
            json={
                "symbol": "AAPL",
                "account_id": "test_account_001",
                "model_name": "gpt-4o",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        call_kwargs = mock_agent_engine.make_decision.call_args.kwargs
        assert call_kwargs["account_id"] == "test_account_001"

    def test_decide_with_system_prompt(self, client_with_engine, mock_agent_engine):
        """测试带自定义系统提示词的决策。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide",
            json={
                "symbol": "AAPL",
                "system_prompt": "Custom system prompt",
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_agent_engine.make_decision.call_args.kwargs
        assert call_kwargs["system_prompt"] == "Custom system prompt"

    def test_decide_no_engine(self, client):
        """测试未初始化引擎时的决策。"""
        response = client.post(
            "/api/v1/ai/decide",
            json={"symbol": "AAPL"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "未初始化" in data["error"]

    def test_decide_missing_symbol(self, client_with_engine):
        """测试缺少 symbol 参数。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide",
            json={},
        )

        assert response.status_code == 422

    def test_decide_engine_error(self, client_with_engine, mock_agent_engine):
        """测试引擎抛出异常。"""
        mock_agent_engine.make_decision = AsyncMock(
            side_effect=RuntimeError("模型调用失败")
        )

        response = client_with_engine.post(
            "/api/v1/ai/decide",
            json={"symbol": "AAPL"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "模型调用失败" in data["error"]


# ===========================================================================
# POST /api/v1/ai/decide/multi 测试
# ===========================================================================


class TestDecideMultiEndpoint:
    """POST /api/v1/ai/decide/multi 测试。"""

    def test_decide_multi_success(self, client_with_engine, mock_agent_engine):
        """测试成功的多模型决策。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide/multi",
            json={
                "symbol": "AAPL",
                "model_names": ["gpt-4o", "deepseek-chat"],
                "voting_strategy": "majority",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["decision"] is not None
        assert data["decision"]["action"] == "buy"
        assert data["decision"]["symbol"] == "AAPL"
        assert data["decision"]["model"] == "multi_model"

        mock_agent_engine.make_decision_multi_model.assert_called_once()

    def test_decide_multi_with_voting_strategy(self, client_with_engine, mock_agent_engine):
        """测试不同投票策略。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide/multi",
            json={
                "symbol": "AAPL",
                "voting_strategy": "confidence",
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_agent_engine.make_decision_multi_model.call_args.kwargs
        assert call_kwargs["voting_strategy"] == "confidence"

    def test_decide_multi_no_engine(self, client):
        """测试未初始化引擎时的多模型决策。"""
        response = client.post(
            "/api/v1/ai/decide/multi",
            json={"symbol": "AAPL"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "未初始化" in data["error"]

    def test_decide_multi_missing_symbol(self, client_with_engine):
        """测试缺少 symbol 参数。"""
        response = client_with_engine.post(
            "/api/v1/ai/decide/multi",
            json={},
        )

        assert response.status_code == 422


# ===========================================================================
# GET /api/v1/ai/models 测试
# ===========================================================================


class TestListModelsEndpoint:
    """GET /api/v1/ai/models 测试。"""

    def test_list_models_success(self, client_with_engine, mock_agent_engine):
        """测试成功列出模型。"""
        response = client_with_engine.get("/api/v1/ai/models")

        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "gpt-4o"
        assert data["models"][1]["name"] == "deepseek-chat"

        mock_agent_engine.list_models.assert_called_once()

    def test_list_models_no_engine(self, client):
        """测试未初始化引擎时返回空列表。"""
        response = client.get("/api/v1/ai/models")

        assert response.status_code == 200
        data = response.json()
        assert data["models"] == []

    def test_list_models_empty(self, client_with_engine, mock_agent_engine):
        """测试无注册模型时返回空列表。"""
        mock_agent_engine.list_models.return_value = []

        response = client_with_engine.get("/api/v1/ai/models")

        assert response.status_code == 200
        data = response.json()
        assert data["models"] == []


# ===========================================================================
# GET /api/v1/ai/providers 测试
# ===========================================================================


class TestListProvidersEndpoint:
    """GET /api/v1/ai/providers 测试。"""

    def test_list_providers_success(self, client):
        """测试成功列出提供商。"""
        response = client.get("/api/v1/ai/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert len(data["providers"]) > 0

        # 验证包含已知提供商
        provider_names = [p["name"] for p in data["providers"]]
        assert "openai" in provider_names
        assert "deepseek" in provider_names
        assert "claude" in provider_names
        assert "seed" in provider_names
        assert "minimax" in provider_names
        assert "qianfan" in provider_names

    def test_list_providers_structure(self, client):
        """测试提供商列表结构。"""
        response = client.get("/api/v1/ai/providers")

        data = response.json()
        for provider in data["providers"]:
            assert "name" in provider
            assert "display_name" in provider
            assert isinstance(provider["name"], str)
            assert isinstance(provider["display_name"], str)
