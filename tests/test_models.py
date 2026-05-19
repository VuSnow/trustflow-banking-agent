import pytest
from pydantic import ValidationError

from backend.models import (
    ChatRequest,
    ChatResponse,
    IntentResult,
    AgentOutput,
    TransactionExtractionResult,
)


class TestChatRequest:
    def test_valid(self):
        req = ChatRequest(user_id="u1", message="hello", session_id="s1")
        assert req.user_id == "u1"

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            ChatRequest(user_id="u1", message="hello")


class TestIntentResult:
    def test_defaults(self):
        result = IntentResult(task_type="QA")
        assert result.risk_hint == "LOW"
        assert result.confidence == 0.0
        assert result.route == ""


class TestTransactionExtractionResult:
    def test_valid_transfer(self):
        result = TransactionExtractionResult(
            transaction_type="transfer",
            details={"amount": 2000000, "currency": "VND", "recipient": "Minh"},
            raw_text="Chuyển 2tr cho Minh",
            confidence=0.98,
        )
        assert result.transaction_type == "transfer"
        assert result.needs_clarification is False
        assert result.missing_info == []

    def test_invalid_transaction_type(self):
        with pytest.raises(ValidationError):
            TransactionExtractionResult(
                transaction_type="invalid_type",
                details={},
                raw_text="test",
            )

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            TransactionExtractionResult(
                transaction_type="transfer",
                details={},
                raw_text="test",
                confidence=1.5,
            )


class TestAgentOutput:
    def test_defaults(self):
        output = AgentOutput(
            agent_type="transaction",
            action="transfer",
        )
        assert output.risk_signals == []
        assert output.clarification is None
        assert output.detail == {}
