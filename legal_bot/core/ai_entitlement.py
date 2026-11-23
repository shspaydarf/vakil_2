"""Compatibility facade for AI-question entitlement.

New code should depend on EntitlementService directly.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .entitlements import EntitlementService
from ..config import CREDIT_AI_QUESTION_COST


class AIEntitlementService:
    def __init__(self, entitlement: Optional[EntitlementService] = None):
        self.entitlement = entitlement or EntitlementService()
        # Compatibility for callers that previously read repo.question_cost.
        self.repo = self.entitlement.repo

    def status(self, user_id: int) -> Optional[Dict[str, Any]]:
        status = self.entitlement.status(int(user_id))
        if not status:
            return None
        ai = status.get("ai_question", {})
        result = {"kind": status.get("source"), **ai, "credits": status.get("credits")}
        if status.get("source") == "credit" and status.get("credits"):
            # Legacy callers treated AI remaining as the shared credit balance.
            result["remaining"] = int(status["credits"].get("remaining") or 0)
        return result

    def reserve_question(self, user_id: int) -> Tuple[bool, str]:
        return self.entitlement.reserve(int(user_id), "ai_question")

    def commit(self, user_id: int, reservation: str) -> bool:
        return self.entitlement.commit(int(user_id), reservation)

    def refund(self, user_id: int, reservation: str) -> bool:
        return self.entitlement.refund(int(user_id), reservation)

    @property
    def question_cost(self) -> int:
        return int(CREDIT_AI_QUESTION_COST)
