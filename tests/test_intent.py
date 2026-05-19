import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agents.orchestrator import Orchestrator
from backend.models import IntentResult


@pytest.fixture
def orchestrator():
    return Orchestrator()


@pytest.fixture
def mock_intent_response(mock_openai_response):
    """Mock a valid intent classification response."""
    def _make(task_type="TRANSACTION", risk_hint="LOW", route="transaction_extractor", confidence=0.98):
        content = json.dumps({
            "task_type": task_type,
            "risk_hint": risk_hint,
            "route": route,
            "confidence": confidence,
            "reason": "test reason",
        })
        return mock_openai_response(content)
    return _make


class TestClassifyIntent:
    @pytest.mark.asyncio
    async def test_transfer_intent(self, orchestrator, mock_intent_response):
        orchestrator.llm = AsyncMock()
        orchestrator.llm.chat.completions.create = AsyncMock(
            return_value=mock_intent_response("TRANSACTION", "LOW", "transaction_extractor", 0.98)
        )

        result = await orchestrator.classify_intent("Chuyển 2tr cho Minh")
        assert result.task_type == "TRANSACTION"
        assert result.route == "transaction_extractor"
        assert result.confidence == 0.98

    @pytest.mark.asyncio
    async def test_data_query_intent(self, orchestrator, mock_intent_response):
        orchestrator.llm = AsyncMock()
        orchestrator.llm.chat.completions.create = AsyncMock(
            return_value=mock_intent_response("DATA_QUERY", "LOW", "data_query_extractor", 0.95)
        )

        result = await orchestrator.classify_intent("Số dư tài khoản")
        assert result.task_type == "DATA_QUERY"
        assert result.route == "data_query_extractor"

    @pytest.mark.asyncio
    async def test_qa_intent(self, orchestrator, mock_intent_response):
        orchestrator.llm = AsyncMock()
        orchestrator.llm.chat.completions.create = AsyncMock(
            return_value=mock_intent_response("QA", "LOW", "qa_handler", 0.9)
        )

        result = await orchestrator.classify_intent("Ngân hàng mở cửa mấy giờ?")
        assert result.task_type == "QA"

    @pytest.mark.asyncio
    async def test_llm_error_raises(self, orchestrator):
        orchestrator.llm = AsyncMock()
        orchestrator.llm.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with pytest.raises(Exception, match="API error"):
            await orchestrator.classify_intent("test")
