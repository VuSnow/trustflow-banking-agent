from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path

REPORT_ROOT = Path(__file__).resolve().parents[3] / ".finance_reports"
logger = logging.getLogger(__name__)


class FinanceReportWriter:
    """Writes markdown and JSON finance advice reports to a gitignored folder."""

    def __init__(self, report_root: Path | None = None):
        self.report_root = report_root or REPORT_ROOT

    def write(self, user_id: str, report: dict) -> dict:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_dir = self.report_root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        markdown_path = user_dir / f"finance_advice_{timestamp}.md"
        json_path = user_dir / f"finance_advice_{timestamp}.json"

        markdown_path.write_text(report["markdown"], encoding="utf-8")
        json_path.write_text(
            json.dumps(report["summary"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "[FINANCE][report_writer] wrote markdown=%s json=%s",
            markdown_path,
            json_path,
        )

        return {
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
            "report_id": f"{user_id}-{timestamp}",
        }

    def write_trace_pipeline(self, user_id: str, payload: dict) -> dict:
        """Write detailed per-step pipeline output for debugging and audit."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_dir = self.report_root / "trace_pipeline"
        trace_dir.mkdir(parents=True, exist_ok=True)

        trace_json_path = trace_dir / f"{user_id}_{timestamp}.json"
        trace_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "trace_json_path": str(trace_json_path),
            "trace_report_id": f"{user_id}-{timestamp}",
        }
