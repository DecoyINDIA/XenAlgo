from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from xenalgo.learning.analytics import LearningReport
from xenalgo.learning.memory import _validate_proposal


class ReviewClient(Protocol):
    def complete(self, prompt: str) -> dict[str, Any] | str:
        """Return a JSON-compatible proposal object. Tests use offline clients."""


@dataclass(frozen=True)
class Proposal:
    title: str
    sleeve: str
    insight: str
    evidence: list[dict[str, Any]]
    proposed_config: dict[str, Any]
    risk_notes: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "sleeve": self.sleeve,
            "insight": self.insight,
            "evidence": self.evidence,
            "proposed_config": self.proposed_config,
            "risk_notes": self.risk_notes,
            "confidence": self.confidence,
        }


class StaticReviewClient:
    """Deterministic offline client for tests and dry runs."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def complete(self, prompt: str) -> dict[str, Any]:
        return dict(self.response)


class AIProposalReviewer:
    """Turns deterministic analytics into schema-checked proposal drafts only."""

    def __init__(self, client: ReviewClient) -> None:
        self.client = client

    def review(self, report: LearningReport) -> Proposal:
        prompt = self._prompt(report)
        response = self.client.complete(prompt)
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError as exc:
                raise ValueError("AI review response must be valid JSON") from exc
        proposal = _validate_proposal(response)
        return Proposal(
            title=proposal["title"],
            sleeve=proposal["sleeve"],
            insight=proposal["insight"],
            evidence=proposal["evidence"],
            proposed_config=proposal["proposed_config"],
            risk_notes=proposal["risk_notes"],
            confidence=proposal["confidence"],
        )

    def _prompt(self, report: LearningReport) -> str:
        payload = report.as_dict()
        return (
            "You are reviewing XenAlgo post-trade analytics. "
            "Return one strict JSON proposal with title, sleeve, insight, "
            "evidence, proposed_config, risk_notes, and confidence. "
            "This is proposal-only; never claim that live orders or risk limits changed.\n"
            + json.dumps(payload, sort_keys=True)
        )
