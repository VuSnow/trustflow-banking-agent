import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.models import ChatResponse, IntentResult, AgentOutput


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, async_client):
        response = await async_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "OK"}


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_transaction(self, async_client):
        with patch("backend.agents.orchestrator.Orchestrator.classify_intent") as mock_intent, \
             patch("backend.agents.transaction.TransactionAgent.extract") as mock_extract:

            mock_intent.return_value = IntentResult(
                task_type="TRANSACTION", risk_hint="LOW",
                route="transaction_extractor", confidence=0.98, reason="test"
            )
            mock_extract.return_value = AgentOutput(
                agent_type="transaction", action="transfer",
                detail={"transaction_type": "transfer", "details": {"amount": 2000000}},
                raw_message="test",
            )

            response = await async_client.post("/chat", json={
                "user_id": "u1",
                "message": "Chuyển 2tr cho Minh tiền ăn trưa",
                "session_id": "s1",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_chat_clarification(self, async_client):
        with patch("backend.agents.orchestrator.Orchestrator.classify_intent") as mock_intent, \
             patch("backend.agents.transaction.TransactionAgent.extract") as mock_extract:

            mock_intent.return_value = IntentResult(
                task_type="TRANSACTION", risk_hint="LOW",
                route="transaction_extractor", confidence=0.95, reason="test"
            )
            mock_extract.return_value = AgentOutput(
                agent_type="transaction", action="transfer",
                detail={},
                clarification="Bạn muốn chuyển cho ai?",
                raw_message="test",
            )

            response = await async_client.post("/chat", json={
                "user_id": "u1",
                "message": "Chuyển 5 triệu",
                "session_id": "s1",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "clarification_needed"
            assert "chuyển cho ai" in data["response"]

    @pytest.mark.asyncio
    async def test_chat_missing_field(self, async_client):
        response = await async_client.post("/chat", json={
            "user_id": "u1",
            "message": "hello",
        })
        assert response.status_code == 422
