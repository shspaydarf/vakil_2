"""Persistence boundary for credits and subscription entitlements."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from .. import db
from ..config import CREDIT_CASE_COST, FREE_WEEKLY_CREDITS
from ..db import FREE_CASE_LIMIT


class CreditRepository:
    """Owns credit/entitlement persistence; policy belongs to CreditService."""

    def _now(self):
        return datetime.now(timezone.utc)

    def _ensure_period_locked(self, conn, user_id: int, now=None) -> Dict[str, Any]:
        now = now or self._now()
        row = conn.execute(
            "SELECT * FROM credit_periods WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if row:
            end = datetime.fromisoformat(row["period_end"])
            if now < end:
                return dict(row)
        start = now
        end = now + timedelta(days=7)
        conn.execute(
            """INSERT INTO credit_periods
               (user_id,period_start,period_end,allowance,balance,created_at)
               VALUES(?,?,?,?,?,?)""",
            (int(user_id), start.isoformat(), end.isoformat(),
             FREE_WEEKLY_CREDITS, FREE_WEEKLY_CREDITS, now.isoformat()),
        )
        return dict(conn.execute(
            "SELECT * FROM credit_periods WHERE id=last_insert_rowid()"
        ).fetchone())

    def status(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not db.get_user(int(user_id)):
            return None
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._ensure_period_locked(conn, int(user_id))
            conn.commit()
        end = datetime.fromisoformat(row["period_end"])
        remaining = max(0, int((end - self._now()).total_seconds()))
        return {
            "period_id": int(row["id"]),
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "allowance": int(row["allowance"]),
            "remaining": int(row["balance"]),
            "seconds_until_refresh": remaining,
        }

    def reserve(self, user_id: int, cost: int, operation: str,
                metadata: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        cost = int(cost)
        if cost <= 0:
            return False, "هزینه اعتبار نامعتبر است."
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute(
                "SELECT * FROM users WHERE user_id=?", (int(user_id),)
            ).fetchone()
            if not user:
                return False, "ابتدا /start را بزنید."
            if int(user["blocked"] or 0):
                return False, "حساب شما مسدود است."
            row = self._ensure_period_locked(conn, int(user_id))
            if int(row["balance"]) < cost:
                return False, "insufficient"
            ref = uuid.uuid4().hex
            meta_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata is not None else None
            conn.execute(
                "UPDATE credit_periods SET balance=balance-? WHERE id=?",
                (cost, int(row["id"])),
            )
            conn.execute(
                """INSERT INTO credit_ledger
                   (user_id,period_id,reference_id,operation,cost,status,created_at,metadata)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (int(user_id), int(row["id"]), ref, operation, cost,
                 "reserved", self._now().isoformat(), meta_text),
            )
            conn.commit()
            return True, ref

    def commit(self, user_id: int, reference_id: str) -> bool:
        with db.conn() as conn:
            cur = conn.execute(
                """UPDATE credit_ledger SET status='committed', finalized_at=?
                   WHERE user_id=? AND reference_id=? AND status='reserved'""",
                (self._now().isoformat(), int(user_id), reference_id),
            )
            conn.commit()
            return cur.rowcount == 1

    def refund(self, user_id: int, reference_id: str) -> bool:
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM credit_ledger
                   WHERE user_id=? AND reference_id=? AND status='reserved'""",
                (int(user_id), reference_id),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                """UPDATE credit_periods SET balance=MIN(allowance,balance+?)
                   WHERE id=?""",
                (int(row["cost"]), int(row["period_id"])),
            )
            cur = conn.execute(
                """UPDATE credit_ledger SET status='refunded', finalized_at=?
                   WHERE id=? AND status='reserved'""",
                (self._now().isoformat(), int(row["id"])),
            )
            conn.commit()
            return cur.rowcount == 1

    def subscription(self, user_id: int) -> Dict[str, Any]:
        return db.ensure_subscription(int(user_id))

    def reserve_subscription_case(self, user_id: int) -> Tuple[bool, str]:
        sub = self.subscription(user_id)
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (int(user_id),),
            ).fetchone()
            if not row:
                return False, "ابتدا /start را بزنید."
            used = int(row["used_cases"] or 0)
            limit = int(row["monthly_limit"] or FREE_CASE_LIMIT)
            if used >= limit:
                return False, "سهمیه پرونده اشتراک شما تمام شده است."
            conn.execute(
                "UPDATE subscriptions SET used_cases=used_cases+1 WHERE id=?",
                (int(row["id"]),),
            )
            conn.commit()
            return True, "subscription"

    def refund_subscription_case(self, user_id: int) -> bool:
        with db.conn() as conn:
            cur = conn.execute(
                """UPDATE subscriptions SET used_cases=MAX(0,used_cases-1)
                   WHERE user_id=? AND active=1 AND used_cases>0""",
                (int(user_id),),
            )
            conn.commit()
            return cur.rowcount == 1
