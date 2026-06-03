"""Plan Executor — runs validated plan steps sequentially via AgentRegistry."""

import logging

from backend.agents.registry import AgentRegistry
from backend.models import AgentPlan, AgentTask, AgentTaskResult

logger = logging.getLogger(__name__)


class PlanExecutor:
    """Executes a validated AgentPlan by calling sub-agents in sequence.

    - Injects user_id from backend context (never trusts LLM-provided user_id)
    - Chains step outputs: if step.input_from == "step_0", merges step_0's result
    """

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    async def execute(self, plan: AgentPlan, context: dict) -> dict[str, AgentTaskResult]:
        """Execute plan steps sequentially.

        Args:
            plan: Validated AgentPlan
            context: {"user_id": str, "extraction": dict}

        Returns:
            Dict mapping "step_0", "step_1", ... to AgentTaskResult
        """
        results: dict[str, AgentTaskResult] = {}

        for i, step in enumerate(plan.steps):
            agent = self.registry.get(step.agent)
            if not agent:
                results[f"step_{i}"] = AgentTaskResult(
                    status="failed",
                    result={"error": f"Agent '{step.agent}' not found in registry"},
                )
                continue

            # Build constraints: step constraints + user_id from backend context
            task_constraints = {**step.constraints, "user_id": context["user_id"]}

            # Chain: if input_from references a previous step, merge its result
            if step.input_from and step.input_from.startswith("step_"):
                prev = results.get(step.input_from)
                if prev and prev.status == "success":
                    # Pass previous step's rows/result as evidence
                    task_constraints["evidence_rows"] = prev.result.get("rows", [])
                    # Also merge other result fields for flexibility
                    for k, v in prev.result.items():
                        if k not in task_constraints:
                            task_constraints[k] = v
                else:
                    # Previous step failed — skip this dependent step
                    logger.warning(
                        f"[PLAN] Skipping step_{i} because {step.input_from} "
                        f"status={prev.status if prev else 'missing'}"
                    )
                    results[f"step_{i}"] = AgentTaskResult(
                        status="failed",
                        result={"error": f"Dependency {step.input_from} did not succeed"},
                    )
                    continue

            task = AgentTask(task_type=step.task_type, constraints=task_constraints)
            logger.info(f"[PLAN] Executing step_{i}: {step.agent}.{step.task_type}")

            try:
                result = await agent.execute_task(task)
            except Exception as e:
                logger.error(f"[PLAN] step_{i} raised: {e}", exc_info=True)
                result = AgentTaskResult(
                    status="failed",
                    result={"error": str(e)},
                )

            results[f"step_{i}"] = result
            logger.info(f"[PLAN] step_{i} result: status={result.status}")

            # Early exit on clarification needed
            if result.status == "needs_clarification":
                logger.info(f"[PLAN] Early exit at step_{i}: needs_clarification")
                break

        return results
