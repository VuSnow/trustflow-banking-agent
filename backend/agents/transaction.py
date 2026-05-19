import json
import logging
from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import AgentOutput, TransactionExtractionResult
from backend.prompts.transaction import TRANSACTION_EXTRACTOR_SYSTEM_PROMPT, TRANSACTION_USER_TEMPLATE

logger = logging.getLogger(__name__)


class TransactionAgent:
    def __init__(self):
        self.llm = AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def extract(self, message: str) -> AgentOutput:
        """Extract transaction entities from user message."""
        logger.debug(f"Extracting transaction from: {message[:50]}")

        response = await self.llm.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": TRANSACTION_EXTRACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": TRANSACTION_USER_TEMPLATE.format(
                    message=message)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        data = json.loads(content)

        extraction = TransactionExtractionResult(**data)

        clarification = None
        if extraction.needs_clarification:
            clarification = self._build_clarification(extraction.missing_info)

        result = AgentOutput(
            agent_type="transaction",
            action=extraction.transaction_type,
            detail=extraction.model_dump(),
            clarification=clarification,
            raw_message=message,
        )
        logger.info(
            f"Transaction extracted: type={extraction.transaction_type}, "
            f"confidence={extraction.confidence:.2f}, "
            f"needs_clarification={extraction.needs_clarification}"
        )
        return result

    def _build_clarification(self, missing_info: list[str]) -> str:
        """Build clarification message from missing fields."""
        messages = {
            "amount": "Bạn muốn chuyển bao nhiêu?",
            "recipient_or_recipient_account": "Bạn muốn chuyển cho ai? Vui lòng cho biết tên hoặc số tài khoản.",
            "phone_number": "Vui lòng cho biết số điện thoại cần nạp.",
            "customer_code_or_provider": "Vui lòng cho biết mã khách hàng hoặc nhà cung cấp dịch vụ.",
            "transaction_type": "Bạn muốn thực hiện giao dịch gì?",
            "multiple_transactions": "Tôi chỉ xử lý được một giao dịch mỗi lần. Bạn muốn thực hiện giao dịch nào trước?",
        }
        parts = [messages.get(info, f"Vui lòng cung cấp thêm: {info}") for info in missing_info]
        return " ".join(parts)

transaction_agent = TransactionAgent()