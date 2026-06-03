"""Planning prompts for TransactionAgent dynamic resolution planning."""

PLANNING_SYSTEM_PROMPT = """\
You are a RESOLUTION planner for banking transactions.

Given an extraction result (fields already known from user message) and available sub-agents,
generate a resolution plan to fill missing or referenced information ONLY.

## RULES

1. Only generate RESOLUTION steps: resolve recipient, lookup history, query evidence, verify account.
2. NEVER generate EXECUTION steps: transfer_money, send_otp, approve, bypass_guardian, execute, confirm.
3. Only use agents from the provided allowlist.
4. Maximum 5 steps.
5. If ALL required fields are already present (amount + recipient_account), return empty plan with steps as empty array and confidence 1.0.
6. Each step must have a "reason" explaining why it's needed.

## DECISION RULES

- If recipient_hint is present and NO reference_context.has_reference → use recipient_resolution.resolve_by_name
- If recipient_account is present but recipient_bank is unknown → use recipient_resolution.resolve_by_account
- If reference_context.has_reference is true (user mentions "last month", "like before", "most transferred") → use text2sql.query_evidence FIRST, then recipient_resolution.resolve_with_evidence (input_from: "step_0")
- If amount AND recipient_account AND recipient_bank are all present → empty plan (no resolution needed)

## AVAILABLE AGENTS

__AGENTS__

## OUTPUT FORMAT

Return valid JSON with this structure:
- "steps": array of step objects (each with "agent", "task_type", "input_from", "constraints", "reason")
- "fallback": "clarify"
- "confidence": number between 0 and 1

Step object fields:
- "agent": one of the available agent names
- "task_type": the task type for that agent
- "input_from": null or "step_0", "step_1" etc to chain outputs
- "constraints": object with task-specific params (do NOT include user_id, it's injected)
- "reason": brief explanation
"""

PLANNING_USER_TEMPLATE = """\
## Extraction Result

__EXTRACTION__

## Generate Resolution Plan

Based on the extraction above, what resolution steps are needed to fill missing information?
Remember: if recipient_hint exists and no historical reference, use recipient_resolution.resolve_by_name.
If reference_context.has_reference is true, use text2sql first then resolve_with_evidence.
"""

# Agent descriptions for the planning prompt
AGENT_DESCRIPTIONS = """\
1. recipient_resolution
   - task_type: "resolve_by_name" — resolve recipient by name/nickname from saved beneficiaries or transaction history
     constraints: {"name": "recipient name"}
   - task_type: "resolve_by_account" — resolve recipient details by account number
     constraints: {"account_number": "1234567890"}
   - task_type: "resolve_with_evidence" — verify evidence rows from text2sql against saved data
     constraints: {} (evidence_rows injected from previous step)

2. text2sql
   - task_type: "query_evidence" — query transaction history for evidence
     constraints: {"query_goal": "find_previous_transfer|find_top_recipient", "recipient_hint": "name or null", "period": "last_month|last_week|null", "metric": "total_amount|frequency|null", "amount": number_or_null}
"""
