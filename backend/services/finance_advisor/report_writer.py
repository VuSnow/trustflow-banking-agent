from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

REPORT_ROOT = Path(__file__).resolve().parents[3] / ".finance_reports"


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

        return {
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
            "report_id": f"{user_id}-{timestamp}",
        }
