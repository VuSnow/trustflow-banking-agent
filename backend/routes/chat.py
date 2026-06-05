"""Chat endpoint and pipeline execution logic."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.models import (
    ChatRequest,
    ChatResponse,
    PipelineState,
)
from backend.agents.orchestrator import orchestrator
from backend.services.audit_log import write_audit_log
from backend.services.chat_session_store import ChatSessionStore
from backend.services.transaction_fsm import handle_transaction_state_intercept
from backend.services.card_operation_fsm import handle_card_operation_state_intercept

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

chat_session_store: ChatSessionStore
DOMAIN_AGENT_MAP: dict


def init(store: ChatSessionStore, agent_map: dict):
    global chat_session_store, DOMAIN_AGENT_MAP
    chat_session_store = store
    DOMAIN_AGENT_MAP = agent_map


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"[RECEIVED] user={request.user_id} msg={request.message}")
    try:
        chat_session_store.ensure_session(request.user_id, request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    chat_session_store.add_message(
        session_id=request.session_id,
        user_id=request.user_id,
        role="user",
        message=request.message,
    )

    # Fetch recent history for multi-turn context
    history = chat_session_store.get_messages(request.session_id)

    # ─── Deterministic intercept: transaction state (OTP/confirmation) ──
    intercepted = await handle_transaction_state_intercept(
        request,
        get_transaction_state=chat_session_store.get_transaction_state,
        set_transaction_state=chat_session_store.set_transaction_state,
        clear_transaction_state=chat_session_store.clear_transaction_state,
        clear_pipeline_state=chat_session_store.clear_pipeline_state,
    )
    if intercepted:
        response = intercepted
    else:
        # ─── Deterministic intercept: card operation state ────────────
        card_intercepted = await handle_card_operation_state_intercept(
            request,
            get_card_operation_state=chat_session_store.get_card_operation_state,
            set_card_operation_state=chat_session_store.set_card_operation_state,
            clear_card_operation_state=chat_session_store.clear_card_operation_state,
        )
        if card_intercepted:
            response = card_intercepted
        else:
            pipeline_state_dict = chat_session_store.get_pipeline_state(request.session_id)
            if pipeline_state_dict:
                response = await _resume_pipeline(pipeline_state_dict, request, history)
            else:
                response = await _start_new_pipeline(request, history)

    chat_session_store.add_message(
        session_id=request.session_id,
        user_id=request.user_id,
        role="assistant",
        message=response.message,
        data=response.model_dump(),
    )
    return response


async def _start_new_pipeline(request: ChatRequest, history: list[dict]) -> ChatResponse:
    """Plan and execute a new pipeline (single or multi-step)."""
    plan = await orchestrator.plan_pipeline(request.message, history=history)
    logger.info(
        f"[PIPELINE] steps={len(plan.steps)} multi={plan.is_multi_intent} "
        f"agents={[s.agent for s in plan.steps]}"
    )

    state = PipelineState(plan=plan, current_step_index=0, step_results=[])
    return await _execute_pipeline(state, request, history)


async def _resume_pipeline(
    state_dict: dict, request: ChatRequest, history: list[dict]
) -> ChatResponse:
    """Resume a paused pipeline after user provides input."""
    state = PipelineState(**state_dict)
    logger.info(
        f"[PIPELINE RESUME] step={state.current_step_index}/{len(state.plan.steps)} "
        f"status={state.status}"
    )

    current_step = state.plan.steps[state.current_step_index]
    current_step.message = request.message

    return await _execute_pipeline(state, request, history)


async def _execute_pipeline(
    state: PipelineState, request: ChatRequest, history: list[dict]
) -> ChatResponse:
    """Execute pipeline steps sequentially until completion or pause."""
    collected_responses: list[str] = []

    while state.current_step_index < len(state.plan.steps):
        step = state.plan.steps[state.current_step_index]
        agent = DOMAIN_AGENT_MAP.get(step.agent)

        if not agent:
            logger.warning(f"[PIPELINE] No agent for: {step.agent}")
            state.step_results.append({"status": "skipped", "agent": step.agent})
            state.current_step_index += 1
            continue

        # ─── Safety gate: evaluate condition before running step ──────────
        if step.condition and state.step_results:
            gate_passed, gate_reason = _evaluate_condition(step.condition, state.step_results[-1])
            if not gate_passed:
                logger.warning(
                    f"[PIPELINE GATE] Step {state.current_step_index} ({step.agent}) "
                    f"blocked by condition={step.condition}: {gate_reason}"
                )
                write_audit_log(
                    cif_no=request.user_id,
                    event_type="PIPELINE_STEP_BLOCKED",
                    actor="system",
                    session_id=request.session_id,
                    event_payload={
                        "step_index": state.current_step_index,
                        "agent": step.agent,
                        "condition": step.condition,
                        "reason": gate_reason,
                        "previous_data": state.step_results[-1].get("data", {}),
                    },
                )
                state.step_results.append({
                    "status": "blocked",
                    "agent": step.agent,
                    "reason": gate_reason,
                })
                state.current_step_index += 1
                collected_responses.append(
                    f"⚠️ {gate_reason}"
                )
                continue

        # ─── Context injection: prepend previous result into message ──────
        step_message = step.message
        if step.depends_on_previous and state.step_results:
            prev_summary = _format_previous_result(state.step_results[-1])
            step_message = (
                f"[Kết quả bước trước]\n{prev_summary}\n\n"
                f"[Yêu cầu hiện tại]\n{step.message}"
            )

        # Build pipeline context from previous step results
        pipeline_context = None
        if step.depends_on_previous and state.step_results:
            pipeline_context = {
                "previous_results": state.step_results[-1],
                "all_results": state.step_results,
            }

        logger.info(
            f"[PIPELINE STEP {state.current_step_index}] "
            f"agent={step.agent} msg={step_message[:80]}"
        )

        # Run agent with context
        output = await agent.run(
            step_message, request.user_id, request.session_id,
            history=history, pipeline_context=pipeline_context,
        )

        # Handle agent output — pipeline pauses
        if output.status in ("clarification_needed", "needs_otp"):
            state.status = "waiting_user"
            state.waiting_reason = output.clarification_message
            chat_session_store.set_pipeline_state(
                request.session_id, state.model_dump()
            )
            msg = output.clarification_message or "Vui lòng xác nhận."
            if collected_responses:
                msg = "\n\n".join(collected_responses) + "\n\n" + msg
            return ChatResponse(
                status=output.status,
                message=msg,
                data=output.response_data or (
                    output.action_draft.model_dump() if output.action_draft else None
                ),
            )

        # Step completed — store result and advance
        step_result = {
            "agent": step.agent,
            "status": output.status,
            "data": output.response_data,
            "info_response": output.info_response,
        }
        state.step_results.append(step_result)
        state.current_step_index += 1

        if output.info_response:
            collected_responses.append(output.info_response)
        elif output.action_draft:
            collected_responses.append(
                f"Giao dịch đã sẵn sàng: {output.action_draft.operation} "
                f"{output.action_draft.amount:,} {output.action_draft.currency}"
                if output.action_draft.amount else "Giao dịch đã sẵn sàng."
            )

    # All steps complete
    state.status = "completed"
    chat_session_store.clear_pipeline_state(request.session_id)
    chat_session_store.clear_transaction_state(request.session_id)

    if len(state.step_results) == 1:
        result = state.step_results[0]
        return ChatResponse(
            status=result["status"],
            message=result.get("info_response") or "Hoàn tất.",
            data=result.get("data"),
        )

    combined_message = "\n\n".join(collected_responses) if collected_responses else "Hoàn tất."
    combined_data = {
        "pipeline_results": state.step_results,
        "steps_completed": len(state.step_results),
    }
    return ChatResponse(
        status="info_response",
        message=combined_message,
        data=combined_data,
    )


# ─── Condition evaluation helpers ────────────────────────────────────────────


def _evaluate_condition(condition: str, previous_result: dict) -> tuple[bool, str]:
    """Evaluate a step condition against the previous step's result.

    Returns (passed: bool, reason: str).
    """
    if condition == "always" or condition is None:
        return True, ""

    if condition == "previous_success":
        status = previous_result.get("status", "")
        if status in ("error", "skipped", "blocked"):
            return False, f"Bước trước thất bại (status={status}). Bỏ qua bước tiếp theo."
        return True, ""

    if condition == "previous_safe":
        data = previous_result.get("data", {})
        is_reported = data.get("is_reported", False)
        risk_level = data.get("risk_level", "LOW")

        if is_reported and risk_level in ("HIGH", "CRITICAL", "BLOCK"):
            report_count = data.get("report_count", 0)
            return False, (
                f"Tài khoản đích có {report_count} báo cáo lừa đảo "
                f"(mức rủi ro: {risk_level}). "
                "Giao dịch đã bị hủy tự động vì lý do an toàn."
            )
        return True, ""

    # Unknown condition — pass by default
    logger.warning(f"[PIPELINE] Unknown condition: {condition}")
    return True, ""


def _format_previous_result(previous_result: dict) -> str:
    """Format previous step result into a compact summary for context injection."""
    parts = []

    agent = previous_result.get("agent", "unknown")
    status = previous_result.get("status", "unknown")
    parts.append(f"Agent: {agent} | Status: {status}")

    # Include info_response text (the natural language answer)
    info = previous_result.get("info_response")
    if info:
        # Truncate long responses
        if len(info) > 500:
            info = info[:500] + "..."
        parts.append(f"Response: {info}")

    # Include key data fields (compact)
    data = previous_result.get("data", {})
    if data:
        # Pick relevant fields, skip trace/internal
        relevant_keys = [
            k for k in data
            if k not in ("trace", "delegation_trace", "pipeline_results")
        ]
        if relevant_keys:
            compact = {k: data[k] for k in relevant_keys[:10]}
            parts.append(f"Data: {compact}")

    return "\n".join(parts)
