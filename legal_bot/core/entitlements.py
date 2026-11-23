"""Canonical application-level entitlement contract.

All metered product operations use the same lifecycle:
    reserve -> commit
    reserve -> refund
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..repositories.entitlements import EntitlementRepository


class EntitlementService:
    """Single entry point for access, reservation, commit and refund."""

    def __init__(self, repository: Optional[EntitlementRepository] = None):
        self.repo = repository or EntitlementRepository()

    def status(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self.repo.status(int(user_id))

    def can_use(self, user_id: int, operation: str) -> bool:
        status = self.status(user_id)
        return bool(status and status.get(operation, {}).get("allowed"))

    def reserve(self, user_id: int, operation: str,
                metadata: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        return self.repo.reserve(int(user_id), operation, metadata)

    def commit(self, user_id: int, reservation_id: str) -> bool:
        return self.repo.commit(int(user_id), reservation_id)

    def refund(self, user_id: int, reservation_id: str) -> bool:
        return self.repo.refund(int(user_id), reservation_id)
