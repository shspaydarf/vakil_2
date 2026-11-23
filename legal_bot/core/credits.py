"""Compatibility facade for case-credit callers.

New code should depend on EntitlementService directly. Keeping this facade
lets the Telegram adapter migrate without a flag day and without preserving
old persistence logic in the UI layer.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .entitlements import EntitlementService


class CreditService:
    def __init__(self, entitlement: Optional[EntitlementService] = None):
        self.entitlement = entitlement or EntitlementService()

    def status(self, user_id: int) -> Optional[Dict[str, Any]]:
        status = self.entitlement.status(int(user_id))
        if not status:
            return None
        # Preserve the old CreditService status shape for Telegram/UI code.
        return {**(status.get("credits") or {}), "source": status.get("source"),
                "subscription_active": status.get("subscription_active", False),
                "case": status.get("case"), "ai_question": status.get("ai_question")}

    def reserve_case(self, user_id: int) -> Tuple[bool, str]:
        return self.entitlement.reserve(int(user_id), "case")

    def refund_case(self, user_id: int, reservation: str) -> bool:
        return self.entitlement.refund(int(user_id), reservation)

    def commit(self, user_id: int, reservation: str) -> bool:
        return self.entitlement.commit(int(user_id), reservation)
