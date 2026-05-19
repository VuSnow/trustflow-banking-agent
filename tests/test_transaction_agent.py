import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agents.transaction import TransactionAgent
from backend.models import AgentOutput


@pytest.fixture
def agent():
    return TransactionAgent()


@pytest.fixture
def mock_extraction_response(mock_openai_response):
    """Factory to create mock extraction responses."""
    def _make(transaction_type="transfer", details=None, needs_clarification=False, missing_info=None, confidence=0.98):
        content = json.dumps({
            "transaction_type": transaction_type,
            "details": details or {"amount": 2000000, "currency": "VND", "recipient": "Minh", "recipient_account": None, "source_account": None, "note": "tiền ăn trưa"},
            "raw_text": "test message",
            "needs_clarification": needs_clarification,
            "missing_info": missing_info or [],
            "confidence": confidence,
        })
        return mock_openai_response(content)
    return _make


class TestTransactionAgent:
    @pytest.mark.asyncio
    async def test_extract_transfer(self, agent, mock_extraction_response):
        agent.llm = AsyncMock()
        agent.llm.chat.completions.create = AsyncMock(
            return_value=mock_extraction_response()
        )

        result = await agent.extract("Chuyển 2tr cho Minh tiền ăn trưa")
        assert isinstance(result, AgentOutput)
        assert result.agent_type == "transaction"
        assert result.action == "transfer"
        assert result.detail["details"]["amount"] == 2000000
        assert result.detail["details"]["recipient"] == "Minh"
        assert result.clarification is None

    @pytest.mark.asyncio
    async def test_extract_missing_recipient(self, agent, mock_extraction_response):
        agent.llm = AsyncMock()
        agent.llm.chat.completions.create = AsyncMock(
            return_value=mock_extraction_response(
                details={"amount": 5000000, "currency": "VND", "recipient": None, "recipient_account": None, "source_account": None, "note": None},
                needs_clarification=True,
                missing_info=["recipient_or_recipient_account"],
                confidence=0.84,
            )
        )

        result = await agent.extract("Chuyển 5 triệu")
        assert result.clarification is not None
        assert "chuyển cho ai" in result.clarification

    @pytest.mark.asyncio
    async def test_extract_bill_payment(self, agent, mock_extraction_response):
        agent.llm = AsyncMock()
        agent.llm.chat.completions.create = AsyncMock(
            return_value=mock_extraction_response(
                transaction_type="bill_payment",
                details={"bill_type": "tiền điện", "amount": None, "currency": "VND", "provider": None, "customer_code": None, "source_account": None, "note": None},
                needs_clarification=True,
                missing_info=["customer_code_or_provider"],
                confidence=0.88,
            )
        )

        result = await agent.extract("Thanh toán tiền điện")
        assert result.action == "bill_payment"
        assert "mã khách hàng" in result.clarification

    @pytest.mark.asyncio
    async def test_extract_multiple_transactions(self, agent, mock_extraction_response):
        agent.llm = AsyncMock()
        agent.llm.chat.completions.create = AsyncMock(
            return_value=mock_extraction_response(
                details={"amount": 2000000, "currency": "VND", "recipient": "Minh", "recipient_account": None, "source_account": None, "note": None},
                needs_clarification=True,
                missing_info=["multiple_transactions"],
                confidence=0.9,
            )
        )

        result = await agent.extract("Chuyển 2tr cho Minh và 500k cho Lan")
        assert "một giao dịch mỗi lần" in result.clarification

    @pytest.mark.asyncio
    async def test_llm_error_raises(self, agent):
        agent.llm = AsyncMock()
        agent.llm.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))

        with pytest.raises(Exception, match="timeout"):
            await agent.extract("test")


class TestBuildClarification:
    def test_known_keys(self):
        agent = TransactionAgent()
        msg = agent._build_clarification(["amount", "phone_number"])
        assert "bao nhiêu" in msg
        assert "số điện thoại" in msg

    def test_unknown_key(self):
        agent = TransactionAgent()
        msg = agent._build_clarification(["some_unknown_field"])
        assert "some_unknown_field" in msg

    def test_empty(self):
        agent = TransactionAgent()
        msg = agent._build_clarification([])
        assert msg == ""
