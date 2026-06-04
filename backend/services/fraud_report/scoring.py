from __future__ import annotations


class FraudConfidenceScorer:
    """Rule-based confidence scoring from the fraud report specification."""

    def calculate(
        self,
        *,
        has_evidence: bool,
        transaction_found: bool,
        existing_reports_count: int,
        reason_text: str,
    ) -> dict:
        score = 50
        reasons = ["base_score:+50"]

        if has_evidence:
            score += 20
            reasons.append("has_evidence:+20")

        if transaction_found:
            score += 15
            reasons.append("verified_transaction:+15")
        else:
            score -= 20
            reasons.append("no_transaction:-20")

        if existing_reports_count:
            bonus = existing_reports_count * 10
            score += bonus
            reasons.append(f"existing_reports:+{bonus}")

        description = (reason_text or "").strip()
        if len(description) > 50:
            score += 10
            reasons.append("detailed_description:+10")
        elif len(description) < 20:
            score -= 10
            reasons.append("vague_description:-10")

        score = max(30, min(100, score))
        status = "VALIDATED" if score >= 80 else "SUBMITTED"

        return {
            "confidence_score": score,
            "status": status,
            "scoring_reasons": reasons,
        }
