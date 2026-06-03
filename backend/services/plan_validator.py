"""Plan Validator — ensures LLM-generated plans are safe and within bounds."""

from backend.models import AgentPlan


class PlanValidationError(Exception):
    pass


# Tasks that are NEVER allowed in resolution plans
EXECUTION_BLOCKLIST = {
    "transfer_money", "execute_transfer", "send_otp",
    "approve_transaction", "bypass_guardian", "execute",
    "confirm", "block", "unblock", "send_money",
    "delete", "update", "insert",
}

# Allowed task_types per agent
ALLOWED_TASKS_PER_AGENT = {
    "recipient_resolution": {"resolve_by_name", "resolve_by_account", "resolve_with_evidence"},
    "text2sql": {"query_evidence"},
}

MAX_PLAN_STEPS = 5


class PlanValidator:
    """Validates that an LLM-generated plan is safe to execute.

    Checks:
    1. Step count within limit
    2. All agents in allowlist
    3. No execution task_types (only resolution allowed)
    4. Task_types valid for each agent
    5. No circular references
    """

    def validate(self, plan: AgentPlan, allowed_agents: set[str]) -> AgentPlan:
        if len(plan.steps) > MAX_PLAN_STEPS:
            raise PlanValidationError(
                f"Plan exceeds max {MAX_PLAN_STEPS} steps (got {len(plan.steps)})"
            )

        for i, step in enumerate(plan.steps):
            if step.agent not in allowed_agents:
                raise PlanValidationError(
                    f"Agent '{step.agent}' not in allowlist: {allowed_agents}"
                )

            if step.task_type.lower() in EXECUTION_BLOCKLIST:
                raise PlanValidationError(
                    f"Execution task_type '{step.task_type}' forbidden in resolution plan"
                )

            allowed_tasks = ALLOWED_TASKS_PER_AGENT.get(step.agent, set())
            if allowed_tasks and step.task_type not in allowed_tasks:
                raise PlanValidationError(
                    f"task_type '{step.task_type}' not allowed for agent '{step.agent}'. "
                    f"Allowed: {allowed_tasks}"
                )

            if step.input_from == f"step_{i}":
                raise PlanValidationError(
                    f"Circular reference: step_{i} references itself"
                )

        return plan
