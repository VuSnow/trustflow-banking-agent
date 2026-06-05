"""LLM-based confirmation classifier.

Classifies user responses during transaction confirmation flow into:
- CONFIRM: user agrees to proceed
- CANCEL: user wants to abort
- MODIFY: user wants to change something in the draft
- UNCLEAR: ambiguous response, needs re-asking

No hard-coded keywords. Uses a lightweight LLM call with structured JSON output.
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.prompts.confirmation import CONFIRMATION_CLASSIFIER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def classify_confirmation(
    message: str,
    draft_summary: str | None = None,
    client: AsyncOpenAI | None = None,
) -> dict:
    """Classify user's response to a transaction confirmation prompt.

    Args:
        message: The user's response message.
        draft_summary: Optional context about what was being confirmed.
        client: OpenAI client (created if not provided).

    Returns:
        {"classification": "CONFIRM|CANCEL|MODIFY|UNCLEAR", "reason": "..."}
    """
    client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)

    user_content = f"User response: {message}"
    if draft_summary:
        user_content = f"Transaction being confirmed: {draft_summary}\n\n{user_content}"

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": CONFIRMATION_CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        classification = data.get("classification", "UNCLEAR").upper()
        if classification not in ("CONFIRM", "CANCEL", "MODIFY", "UNCLEAR"):
            classification = "UNCLEAR"
        return {"classification": classification, "reason": data.get("reason", "")}
    except Exception as e:
        logger.error(f"[CLASSIFIER] Error: {e}", exc_info=True)
        # On failure, default to UNCLEAR so we don't accidentally confirm
        return {"classification": "UNCLEAR", "reason": f"classifier_error: {e}"}
