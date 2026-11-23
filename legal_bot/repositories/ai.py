"""Compatibility facade for the old AI entitlement repository name.

The canonical implementation now lives in EntitlementRepository. This module
exists only so older imports do not break during the migration window.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .entitlements import EntitlementRepository
from ..config import CREDIT_AI_QUESTION_COST


class AIEntitlementRepository:
    def __init__(self, entitlement_repository: Optional[EntitlementRepository] = None):
        self.entitlements = entitlement_repository or EntitlementRepository()

    def quota(self, user_id: int) -> Optional[Dict[str, Any]]:
        status = self.entitlements.status(int(user_id))
        if not status:
            return None
        return status.get("ai_question")

    def reserve(self, user_id: int) -> Tuple[bool, str]:
        return self.entitlements.reserve(int(user_id), "ai_question")

    def commit(self, user_id: int, reservation: str) -> bool:
        return self.entitlements.commit(int(user_id), reservation)

    def refund(self, user_id: int, reservation: str) -> bool:
        return self.entitlements.refund(int(user_id), reservation)

    @property
    def question_cost(self) -> int:
        return int(CREDIT_AI_QUESTION_COST)
