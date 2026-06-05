from __future__ import annotations

import json
import logging
from datetime import datetime

from backend.agents.registry import AgentRegistry
from backend.agents.sub_agents.finance_advisor import (
    BudgetAnalyzerAgent,
    CategorizerAgent,
    ChatAgent,
    PatternDetectorAgent,
    SavingsOpportunityAgent,
    SubscriptionTrackerAgent,
)
from backend.models import AgentTask, DomainAgentOutput
from backend.prompts.finance_advice import FINANCE_CHAT_SYSTEM_PROMPT
from backend.services.finance_advisor import (
    FinanceReportWriter,
    FinanceTransactionStore,
    parse_lookback_days,
)

logger = logging.getLogger(__name__)


class FinanceAdvisorAgent:
    """Domain agent for FINANCE_ADVICE intent."""

    def __init__(self):
        self.registry = AgentRegistry()
        self.registry.register("categorizer", CategorizerAgent())
        self.registry.register("pattern_detector", PatternDetectorAgent())
        self.registry.register("subscription_tracker", SubscriptionTrackerAgent())
        self.registry.register("budget_analyzer", BudgetAnalyzerAgent())
        self.registry.register("savings_opportunity", SavingsOpportunityAgent())
        self.registry.register("chat_agent", ChatAgent())

        self.transaction_store = FinanceTransactionStore()
        self.report_writer = FinanceReportWriter()

    async def run(self, message: str, user_id: str, session_id: str, history: list[dict] | None = None, pipeline_context: dict | None = None) -> DomainAgentOutput:
        trace: list[str] = []
        lookback_days = parse_lookback_days(message, default_days=30)
        logger.info(
            "[FINANCE] start user=%s session=%s lookback_days=%s message=%r",
            user_id,
            session_id,
            lookback_days,
            message,
        )

        transactions = self.transaction_store.load_user_transactions(
            user_id=user_id,
            lookback_days=lookback_days,
        )
        trace.append("load_transactions")
        logger.info("[FINANCE] loaded transactions=%s", len(transactions))

        categorizer = self.registry.get("categorizer")
        pattern_detector = self.registry.get("pattern_detector")
        subscription_tracker = self.registry.get("subscription_tracker")
        budget_analyzer = self.registry.get("budget_analyzer")
        savings_opportunity = self.registry.get("savings_opportunity")
        chat_agent = self.registry.get("chat_agent")

        step_outputs: dict[str, dict] = {}

        categorization = await categorizer.execute_task(
            AgentTask(
                task_type="categorize_transactions",
                constraints={"transactions": transactions},
            )
        )
        trace.append("categorize_transactions")
        step_outputs["categorize_transactions"] = _safe_json(
            {
                "status": categorization.status,
                "confidence": categorization.confidence,
                "result": categorization.result,
            }
        )

        categorized_transactions = categorization.result.get("categorized_transactions", [])
        pattern_result = await pattern_detector.execute_task(
            AgentTask(
                task_type="detect_patterns",
                constraints={"categorized_transactions": categorized_transactions},
            )
        )
        trace.append("detect_patterns")
        step_outputs["detect_patterns"] = _safe_json(
            {
                "status": pattern_result.status,
                "confidence": pattern_result.confidence,
                "result": pattern_result.result,
            }
        )

        subscription_result = await subscription_tracker.execute_task(
            AgentTask(
                task_type="track_subscriptions",
                constraints={"categorized_transactions": categorized_transactions},
            )
        )
        trace.append("track_subscriptions")
        step_outputs["track_subscriptions"] = _safe_json(
            {
                "status": subscription_result.status,
                "confidence": subscription_result.confidence,
                "result": subscription_result.result,
            }
        )

        budget_result = await budget_analyzer.execute_task(
            AgentTask(
                task_type="analyze_budget",
                constraints={
                    "categorized_transactions": categorized_transactions,
                    "subscriptions": subscription_result.result.get("subscriptions", []),
                },
            )
        )
        trace.append("analyze_budget")
        step_outputs["analyze_budget"] = _safe_json(
            {
                "status": budget_result.status,
                "confidence": budget_result.confidence,
                "result": budget_result.result,
            }
        )

        savings_result = await savings_opportunity.execute_task(
            AgentTask(
                task_type="find_savings_opportunities",
                constraints={
                    "budget_analysis": budget_result.result,
                    "subscriptions": subscription_result.result.get("subscriptions", []),
                    "patterns": pattern_result.result.get("patterns", []),
                },
            )
        )
        trace.append("find_savings_opportunities")
        step_outputs["find_savings_opportunities"] = _safe_json(
            {
                "status": savings_result.status,
                "confidence": savings_result.confidence,
                "result": savings_result.result,
            }
        )

        analysis_bundle = {
            "lookback_days": lookback_days,
            "transaction_count": len(transactions),
            "income_total": categorization.result.get("income_total", 0),
            "income_total_label": categorization.result.get("income_total_label"),
            "expense_total": categorization.result.get("expense_total", 0),
            "expense_total_label": categorization.result.get("expense_total_label"),
            "spend_total": categorization.result.get("expense_total", 0),
            "spend_total_label": categorization.result.get("expense_total_label"),
            "net_cashflow": categorization.result.get("net_cashflow", 0),
            "net_cashflow_label": categorization.result.get("net_cashflow_label"),
            "transaction_summary": {
                "income_total": categorization.result.get("income_total", 0),
                "income_total_label": categorization.result.get("income_total_label"),
                "expense_total": categorization.result.get("expense_total", 0),
                "expense_total_label": categorization.result.get("expense_total_label"),
                "net_cashflow": categorization.result.get("net_cashflow", 0),
            },
            "top_categories": categorization.result.get("top_categories", []),
            "patterns": pattern_result.result.get("patterns", []),
            "top_counterparties": pattern_result.result.get("top_counterparties", []),
            "spike_flags": pattern_result.result.get("spike_flags", []),
            "subscriptions": subscription_result.result.get("subscriptions", []),
            "budget_analysis": budget_result.result,
            "savings_opportunities": savings_result.result.get("opportunities", []),
            "total_estimated_monthly_savings": savings_result.result.get(
                "total_estimated_monthly_savings", 0
            ),
            "analysis_timestamp": datetime.now().isoformat(timespec="seconds"),
        }

        chat_result = await chat_agent.execute_task(
            AgentTask(
                task_type="compose_advice",
                constraints={
                    "message": message,
                    "lookback_days": lookback_days,
                    "analysis": analysis_bundle,
                    "opportunities": savings_result.result.get("opportunities", []),
                },
            )
        )
        trace.append("compose_advice")
        step_outputs["compose_advice"] = _safe_json(
            {
                "status": chat_result.status,
                "confidence": chat_result.confidence,
                "result": chat_result.result,
            }
        )

        markdown_report = self._build_markdown_report(
            user_id=user_id,
            message=message,
            analysis=analysis_bundle,
            advisory_text=chat_result.result.get("advice", ""),
        )

        report_payload = {
            "markdown": markdown_report,
            "summary": {
                "user_id": user_id,
                "message": message,
                "analysis": analysis_bundle,
                "advisory_text": chat_result.result.get("advice", ""),
                "trace": trace,
            },
        }
        report_meta = self.report_writer.write(user_id, report_payload)

        trace_meta = self.report_writer.write_trace_pipeline(
            user_id=user_id,
            payload={
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
                "lookback_days": lookback_days,
                "trace": trace,
                "steps": step_outputs,
                "analysis": analysis_bundle,
                "final_output": {
                    "status": "info_response",
                    "advisory_text": chat_result.result.get("advice", ""),
                    "report": report_meta,
                },
            },
        )

        response_data = {
            "advisory_text": chat_result.result.get("advice", ""),
            "report": report_meta,
            "trace_pipeline": trace_meta,
            "analysis": analysis_bundle,
            "lookback_days": lookback_days,
            "transaction_count": len(transactions),
            "trace": trace,
            "prompt_reference": FINANCE_CHAT_SYSTEM_PROMPT.strip().splitlines()[0],
        }
        logger.info(
            "[FINANCE] complete report_id=%s trace_file=%s",
            report_meta["report_id"],
            trace_meta["trace_json_path"],
        )
        logger.info(
            "[FINANCE] pipeline output=%s",
            json.dumps(
                _safe_json(
                    {
                        "status": "info_response",
                        "advisory_text": chat_result.result.get("advice", ""),
                        "report_id": report_meta["report_id"],
                        "trace_file": trace_meta["trace_json_path"],
                    }
                ),
                ensure_ascii=False,
            ),
        )

        return DomainAgentOutput(
            status="info_response",
            info_response=chat_result.result.get("advice", ""),
            response_data=response_data,
            delegation_trace=trace,
        )

    def _build_markdown_report(
        self,
        user_id: str,
        message: str,
        analysis: dict,
        advisory_text: str,
    ) -> str:
        summary = analysis.get("transaction_summary", {})
        top_categories = analysis.get("top_categories", [])
        subscriptions = analysis.get("subscriptions", [])
        opportunities = analysis.get("savings_opportunities", [])
        budget_analysis = analysis.get("budget_analysis", {})

        lines = [
            f"# Finance Advice Report",
            "",
            f"- User: `{user_id}`",
            f"- Lookback window: `{analysis.get('lookback_days', 30)} days`",
            f"- Transaction count: `{analysis.get('transaction_count', 0)}`",
            f"- User request: {message}",
            "",
            "## Advisory Summary",
            advisory_text or "_No advisory text generated._",
            "",
            "## Transaction Summary",
            f"- Income: {summary.get('income_total_label', '0 VND')}",
            f"- Spend: {summary.get('expense_total_label', '0 VND')}",
            f"- Net cashflow: {summary.get('net_cashflow', 0)}",
            "",
            "## Top Categories",
        ]

        if top_categories:
            for item in top_categories[:5]:
                lines.append(
                    f"- {item.get('category')}: {item.get('amount_label')}"
                )
        else:
            lines.append("- No category data available.")

        lines.extend(
            [
                "",
                "## Patterns",
            ]
        )
        patterns = analysis.get("patterns", [])
        spike_flags = analysis.get("spike_flags", [])
        if patterns:
            for pattern in patterns:
                lines.append(f"- {pattern.get('message')}")
        else:
            lines.append("- No strong patterns detected.")

        if spike_flags:
            for spike in spike_flags:
                lines.append(f"- {spike.get('message')}")

        lines.extend(
            [
                "",
                "## Subscriptions",
            ]
        )
        if subscriptions:
            for item in subscriptions:
                lines.append(
                    f"- {item.get('name')} | {item.get('cadence')} | {item.get('average_amount_label')}"
                )
        else:
            lines.append("- No recurring subscriptions detected.")

        lines.extend(
            [
                "",
                "## Budget Pressure",
            ]
        )
        overspend_categories = budget_analysis.get("overspend_categories", [])
        if overspend_categories:
            for item in overspend_categories:
                lines.append(
                    f"- {item.get('category')}: over by {item.get('variance_label')}"
                )
        else:
            lines.append("- No categories are currently over the estimated budget.")

        lines.extend(
            [
                "",
                "## Savings Opportunities",
            ]
        )
        if opportunities:
            for item in opportunities:
                lines.append(
                    f"- {item.get('title')} | {item.get('estimated_monthly_savings_label')} | {item.get('action')}"
                )
        else:
            lines.append("- No specific savings opportunities identified.")

        lines.extend(
            [
                "",
                "## Raw Analysis Snapshot",
                "```json",
                json.dumps(analysis, ensure_ascii=False, indent=2),
                "```",
            ]
        )

        return "\n".join(lines)


def _safe_json(value):
    """Best-effort JSON-safe conversion for logging."""
    if isinstance(value, dict):
        return {k: _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
