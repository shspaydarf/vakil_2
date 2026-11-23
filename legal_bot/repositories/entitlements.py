"""Persistence boundary for unified entitlements and reservations.

The repository deliberately keeps the existing free-credit ledger and the
subscription tables as storage details. Callers get one reservation contract:
reserve -> commit OR refund.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .. import db
from ..config import CREDIT_AI_QUESTION_COST, CREDIT_CASE_COST, SUBSCRIPTION_AI_MONTHLY_LIMIT
from .credits import CreditRepository


class EntitlementRepository:
    """Coordinates free credits and paid subscription usage behind one API."""

    OPERATION_COSTS = {
        "case": CREDIT_CASE_COST,
        "ai_question": CREDIT_AI_QUESTION_COST,
    }

    def __init__(self, credit_repository: Optional[CreditRepository] = None):
        self.credits = credit_repository or CreditRepository()
        self.ensure_tables()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _period_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    @staticmethod
    def ensure_tables() -> None:
        with db.conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS entitlement_reservations(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reference_id TEXT NOT NULL UNIQUE,
                operation TEXT NOT NULL,
                source TEXT NOT NULL,
                cost INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                finalized_at TEXT,
                metadata TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS subscription_entitlement_usage(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                period_key TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, operation, period_key),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ent_res_user_status ON entitlement_reservations(user_id,status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ent_usage_user_op_period ON subscription_entitlement_usage(user_id,operation,period_key)")
            conn.commit()

    def _subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        s = db.subscription_status(int(user_id))
        if not s or not s.get("active"):
            return None
        return s

    def _migrate_legacy_ai_usage_locked(self, conn: sqlite3.Connection, user_id: int, period_key: str) -> int:
        """Seed the new AI usage row from the old monthly quota once.

        Existing installations keep their already-consumed paid AI questions;
        new reservations then use only the unified usage table.
        """
        existing = conn.execute(
            "SELECT used FROM subscription_entitlement_usage WHERE user_id=? AND operation='ai_question' AND period_key=?",
            (int(user_id), period_key),
        ).fetchone()
        if existing:
            return int(existing["used"])

        legacy_used = 0
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_question_quota'"
        ).fetchone()
        if table_exists:
            row = conn.execute(
                "SELECT used_questions FROM ai_question_quota WHERE user_id=? AND period_key=?",
                (int(user_id), period_key),
            ).fetchone()
            if row:
                legacy_used = max(0, int(row["used_questions"] or 0))

        now = self._now().isoformat()
        conn.execute(
            """INSERT INTO subscription_entitlement_usage
               (user_id,operation,period_key,used,created_at,updated_at)
               VALUES(?,?,?,?,?,?)""",
            (int(user_id), "ai_question", period_key, legacy_used, now, now),
        )
        return legacy_used

    def _record_reservation(self, conn: sqlite3.Connection, user_id: int,
                            operation: str, source: str, cost: int,
                            metadata: Optional[Dict[str, Any]] = None) -> str:
        ref = uuid.uuid4().hex
        meta_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata is not None else None
        conn.execute(
            """INSERT INTO entitlement_reservations
               (user_id,reference_id,operation,source,cost,status,created_at,metadata)
               VALUES(?,?,?,?,?,?,?,?)""",
            (int(user_id), ref, operation, source, int(cost), "reserved", self._now().isoformat(), meta_text),
        )
        return ref

    def reserve(self, user_id: int, operation: str,
                metadata: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        uid = int(user_id)
        operation = str(operation)
        if operation not in self.OPERATION_COSTS:
            return False, "unsupported_operation"
        user = db.get_user(uid)
        if not user:
            return False, "ابتدا /start را بزنید."
        if int(user.get("blocked") or 0):
            return False, "حساب شما مسدود است."

        cost = int(self.OPERATION_COSTS[operation])
        subscription = self._subscription(uid)

        # Free entitlements and the unified reservation are committed in the
        # same SQLite transaction. This prevents an orphaned credit hold if
        # the new reservation record cannot be written.
        if not subscription:
            with db.conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = self.credits._ensure_period_locked(conn, uid)
                if int(row["balance"]) < cost:
                    return False, "insufficient"
                ref = uuid.uuid4().hex
                now = self._now().isoformat()
                meta_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata is not None else None
                conn.execute("UPDATE credit_periods SET balance=balance-? WHERE id=?", (cost, int(row["id"])))
                conn.execute("""INSERT INTO credit_ledger
                    (user_id,period_id,reference_id,operation,cost,status,created_at,metadata)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (uid, int(row["id"]), ref, operation, cost, "reserved", now, meta_text))
                conn.execute("""INSERT INTO entitlement_reservations
                    (user_id,reference_id,operation,source,cost,status,created_at,metadata)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (uid, ref, operation, "credit", cost, "reserved", now, meta_text))
                conn.commit()
                return True, ref

        # Paid subscription reservations are backed by subscription usage.
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if operation == "case":
                row = conn.execute(
                    "SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",
                    (uid,),
                ).fetchone()
                if not row:
                    return False, "ابتدا /start را بزنید."
                used = int(row["used_cases"] or 0)
                limit = int(row["monthly_limit"] or 0)
                if used >= limit:
                    return False, "سهمیه پرونده اشتراک شما تمام شده است."
                conn.execute("UPDATE subscriptions SET used_cases=used_cases+1 WHERE id=?", (int(row["id"]),))
            else:
                period = self._period_key()
                used = self._migrate_legacy_ai_usage_locked(conn, uid, period)
                limit = int(SUBSCRIPTION_AI_MONTHLY_LIMIT)
                if used >= limit:
                    return False, "سهمیه AI اشتراک شما تمام شده است."
                now = self._now().isoformat()
                conn.execute(
                    "UPDATE subscription_entitlement_usage SET used=used+1,updated_at=? WHERE user_id=? AND operation=? AND period_key=?",
                    (now, uid, operation, period),
                )
            ref = self._record_reservation(conn, uid, operation, "subscription", cost, metadata)
            conn.commit()
            return True, ref

    def commit(self, user_id: int, reference_id: str) -> bool:
        uid = int(user_id)
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM entitlement_reservations WHERE user_id=? AND reference_id=? AND status='reserved'",
                (uid, str(reference_id)),
            ).fetchone()
            if not row:
                conn.rollback()
                return False

            # A credit reservation already reduced the current balance. Its
            # ledger row must also move to committed so the reservation and
            # the accounting ledger cannot drift apart. Subscription usage
            # was consumed at reserve-time, so there is no second mutation
            # needed here for subscription-backed operations.
            if row["source"] == "credit":
                ledger = conn.execute(
                    "SELECT id FROM credit_ledger WHERE user_id=? AND reference_id=? AND status='reserved'",
                    (uid, str(reference_id)),
                ).fetchone()
                if not ledger:
                    conn.rollback()
                    return False
                cur = conn.execute(
                    "UPDATE credit_ledger SET status='committed',finalized_at=? WHERE id=? AND status='reserved'",
                    (self._now().isoformat(), int(ledger["id"])),
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    return False

            cur = conn.execute(
                """UPDATE entitlement_reservations SET status='committed',finalized_at=?
                   WHERE user_id=? AND reference_id=? AND status='reserved'""",
                (self._now().isoformat(), uid, str(reference_id)),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return False
            conn.commit()
            return True

    def refund(self, user_id: int, reference_id: str) -> bool:
        uid = int(user_id)
        with db.conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM entitlement_reservations WHERE user_id=? AND reference_id=? AND status='reserved'",
                (uid, str(reference_id)),
            ).fetchone()
            if not row:
                return False

            if row["source"] == "credit":
                ledger = conn.execute(
                    "SELECT * FROM credit_ledger WHERE user_id=? AND reference_id=? AND status='reserved'",
                    (uid, str(reference_id)),
                ).fetchone()
                if not ledger:
                    conn.rollback()
                    return False
                conn.execute(
                    "UPDATE credit_periods SET balance=MIN(allowance,balance+?) WHERE id=?",
                    (int(ledger["cost"]), int(ledger["period_id"])),
                )
                conn.execute(
                    "UPDATE credit_ledger SET status='refunded',finalized_at=? WHERE id=? AND status='reserved'",
                    (self._now().isoformat(), int(ledger["id"])),
                )
            else:
                operation = str(row["operation"])
                if operation == "case":
                    cur = conn.execute(
                        "UPDATE subscriptions SET used_cases=MAX(0,used_cases-1) WHERE user_id=? AND used_cases>0",
                        (uid,),
                    )
                elif operation == "ai_question":
                    period = self._period_key()
                    cur = conn.execute(
                        "UPDATE subscription_entitlement_usage SET used=MAX(0,used-1),updated_at=? WHERE user_id=? AND operation=? AND period_key=? AND used>0",
                        (self._now().isoformat(), uid, operation, period),
                    )
                else:
                    conn.rollback()
                    return False
                if cur.rowcount != 1:
                    conn.rollback()
                    return False

            cur = conn.execute(
                "UPDATE entitlement_reservations SET status='refunded',finalized_at=? WHERE user_id=? AND reference_id=? AND status='reserved'",
                (self._now().isoformat(), uid, str(reference_id)),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return False
            conn.commit()
            return True

    @property
    def question_cost(self) -> int:
        return int(CREDIT_AI_QUESTION_COST)

    def status(self, user_id: int) -> Optional[Dict[str, Any]]:
        uid = int(user_id)
        if not db.get_user(uid):
            return None
        subscription = self._subscription(uid)
        if not subscription:
            credit = self.credits.status(uid) or {}
            return {
                "source": "credit",
                "subscription_active": False,
                "credits": credit,
                "case": {"allowed": int(credit.get("remaining", 0)) >= CREDIT_CASE_COST,
                         "cost": CREDIT_CASE_COST},
                "ai_question": {"allowed": int(credit.get("remaining", 0)) >= CREDIT_AI_QUESTION_COST,
                                "cost": CREDIT_AI_QUESTION_COST},
            }

        with db.conn() as conn:
            period = self._period_key()
            ai_used = self._migrate_legacy_ai_usage_locked(conn, uid, period)
            conn.commit()
        case_remaining = max(0, int(subscription.get("monthly_limit") or 0) - int(subscription.get("used_cases") or 0))
        ai_remaining = max(0, int(SUBSCRIPTION_AI_MONTHLY_LIMIT) - ai_used)
        return {
            "source": "subscription",
            "subscription_active": True,
            "subscription": subscription,
            "case": {"allowed": case_remaining > 0, "used": int(subscription.get("used_cases") or 0),
                     "limit": int(subscription.get("monthly_limit") or 0), "remaining": case_remaining,
                     "cost": CREDIT_CASE_COST},
            "ai_question": {"allowed": ai_remaining > 0, "used": ai_used,
                            "limit": int(SUBSCRIPTION_AI_MONTHLY_LIMIT), "remaining": ai_remaining,
                            "cost": CREDIT_AI_QUESTION_COST, "period": period},
        }
