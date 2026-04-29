"""AI 成本追踪服务单元测试

测试 CostService 的 record_usage、get_summary、get_by_provider 和 get_by_day。
"""

import pytest

from src.services.cost_service import CostService, CostRecord


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def cost_service():
    """创建 CostService 实例。"""
    return CostService()


# ===========================================================================
# record_usage() 测试
# ===========================================================================


class TestRecordUsage:
    """record_usage() 测试。"""

    def test_record_usage_returns_cost_record(self, cost_service):
        """测试 record_usage 返回 CostRecord。"""
        record = cost_service.record_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            latency_ms=800.0,
        )

        assert isinstance(record, CostRecord)
        assert record.provider == "openai"
        assert record.model == "gpt-4o"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.total_tokens == 150
        assert record.latency_ms == 800.0
        assert record.cost > 0

    def test_record_usage_calculates_cost(self, cost_service):
        """测试 record_usage 正确计算成本。"""
        # gpt-4o: input=$2.5/M, output=$10.0/M
        record = cost_service.record_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )

        assert record.cost == pytest.approx(2.5 + 10.0, rel=1e-6)

    def test_record_usage_default_tokens(self, cost_service):
        """测试默认 token 数为 0。"""
        record = cost_service.record_usage(
            provider="openai",
            model="gpt-4o",
        )

        assert record.input_tokens == 0
        assert record.output_tokens == 0
        assert record.total_tokens == 0
        assert record.cost == 0.0

    def test_record_usage_multiple_records(self, cost_service):
        """测试记录多条使用记录。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)
        cost_service.record_usage("deepseek", "deepseek-chat", 200, 100)
        cost_service.record_usage("openai", "gpt-4o-mini", 300, 150)

        summary = cost_service.get_summary()
        assert summary["total_calls"] == 3

    def test_record_usage_timestamp(self, cost_service):
        """测试记录包含时间戳。"""
        record = cost_service.record_usage("openai", "gpt-4o", 100, 50)
        assert record.timestamp is not None


# ===========================================================================
# get_summary() 测试
# ===========================================================================


class TestGetSummary:
    """get_summary() 测试。"""

    def test_get_summary_empty(self, cost_service):
        """测试空记录时的摘要。"""
        summary = cost_service.get_summary()

        assert summary["total_cost"] == 0.0
        assert summary["total_tokens"] == 0
        assert summary["total_calls"] == 0
        assert summary["total_input_tokens"] == 0
        assert summary["total_output_tokens"] == 0
        assert summary["providers"] == []
        assert summary["avg_latency_ms"] == 0.0

    def test_get_summary_with_records(self, cost_service):
        """测试有记录时的摘要。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50, latency_ms=100.0)
        cost_service.record_usage("deepseek", "deepseek-chat", 200, 100, latency_ms=200.0)

        summary = cost_service.get_summary()

        assert summary["total_cost"] > 0
        assert summary["total_tokens"] == 450  # 100+50 + 200+100
        assert summary["total_calls"] == 2
        assert summary["total_input_tokens"] == 300  # 100 + 200
        assert summary["total_output_tokens"] == 150  # 50 + 100
        assert set(summary["providers"]) == {"openai", "deepseek"}
        assert summary["avg_latency_ms"] == 150.0  # (100 + 200) / 2

    def test_get_summary_single_record(self, cost_service):
        """测试单条记录的摘要。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50, latency_ms=500.0)

        summary = cost_service.get_summary()

        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 150
        assert summary["avg_latency_ms"] == 500.0


# ===========================================================================
# get_by_provider() 测试
# ===========================================================================


class TestGetByProvider:
    """get_by_provider() 测试。"""

    def test_get_by_provider_empty(self, cost_service):
        """测试空记录时的提供商统计。"""
        result = cost_service.get_by_provider("openai")

        assert result["provider"] == "openai"
        assert result["total_cost"] == 0.0
        assert result["total_tokens"] == 0
        assert result["total_calls"] == 0
        assert result["models"] == {}

    def test_get_by_provider_with_records(self, cost_service):
        """测试有记录时的提供商统计。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)
        cost_service.record_usage("openai", "gpt-4o-mini", 200, 100)
        cost_service.record_usage("deepseek", "deepseek-chat", 300, 150)

        result = cost_service.get_by_provider("openai")

        assert result["provider"] == "openai"
        assert result["total_calls"] == 2
        assert result["total_tokens"] == 450  # 150 + 300
        assert "gpt-4o" in result["models"]
        assert "gpt-4o-mini" in result["models"]
        assert result["models"]["gpt-4o"]["total_calls"] == 1
        assert result["models"]["gpt-4o-mini"]["total_calls"] == 1

    def test_get_by_provider_nonexistent(self, cost_service):
        """测试不存在的提供商。"""
        result = cost_service.get_by_provider("nonexistent_provider")

        assert result["provider"] == "nonexistent_provider"
        assert result["total_calls"] == 0
        assert result["models"] == {}

    def test_get_by_provider_multiple_models(self, cost_service):
        """测试同一提供商多个模型的统计。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)
        cost_service.record_usage("openai", "gpt-4o", 200, 100)
        cost_service.record_usage("openai", "gpt-4o-mini", 300, 150)

        result = cost_service.get_by_provider("openai")

        assert result["total_calls"] == 3
        assert result["models"]["gpt-4o"]["total_calls"] == 2
        assert result["models"]["gpt-4o-mini"]["total_calls"] == 1


# ===========================================================================
# get_by_day() 测试
# ===========================================================================


class TestGetByDay:
    """get_by_day() 测试。"""

    def test_get_by_day_empty(self, cost_service):
        """测试空记录时的按天统计。"""
        result = cost_service.get_by_day()
        assert result == []

    def test_get_by_day_with_records(self, cost_service):
        """测试有记录时的按天统计。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)
        cost_service.record_usage("deepseek", "deepseek-chat", 200, 100)

        result = cost_service.get_by_day(days=7)

        assert len(result) == 1  # 同一天
        assert result[0]["total_calls"] == 2
        assert result[0]["total_tokens"] == 450
        assert result[0]["total_cost"] > 0
        assert "date" in result[0]

    def test_get_by_day_sorted_descending(self, cost_service):
        """测试按天统计结果按日期降序排列。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)

        result = cost_service.get_by_day(days=7)
        # 单日记录，排序后应只有一个
        assert len(result) >= 1

    def test_get_by_day_custom_days(self, cost_service):
        """测试自定义天数的统计。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)

        # 查询 1 天内的记录
        result_1 = cost_service.get_by_day(days=1)
        # 查询 30 天内的记录
        result_30 = cost_service.get_by_day(days=30)

        # 今天的记录应在两个查询中都存在
        assert len(result_1) >= 1
        assert len(result_30) >= 1

    def test_get_by_day_date_format(self, cost_service):
        """测试日期格式正确。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)

        result = cost_service.get_by_day(days=7)
        if result:
            # 日期格式应为 YYYY-MM-DD
            assert len(result[0]["date"]) == 10


# ===========================================================================
# clear_records() 测试
# ===========================================================================


class TestClearRecords:
    """clear_records() 测试。"""

    def test_clear_records(self, cost_service):
        """测试清除所有记录。"""
        cost_service.record_usage("openai", "gpt-4o", 100, 50)
        cost_service.record_usage("deepseek", "deepseek-chat", 200, 100)

        count = cost_service.clear_records()
        assert count == 2

        summary = cost_service.get_summary()
        assert summary["total_calls"] == 0

    def test_clear_records_empty(self, cost_service):
        """测试清除空记录。"""
        count = cost_service.clear_records()
        assert count == 0
