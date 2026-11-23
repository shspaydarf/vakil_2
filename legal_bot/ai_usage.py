"""Privacy-minimal provider usage ledger for AI calls.

Stores token counts, feature, model, status and latency only. Never stores
prompts, completions, user IDs, case IDs, file names or document text.
"""
from __future__ import annotations
import os, sqlite3, threading
from datetime import datetime, timezone, timedelta
from .config import DB_PATH

_LOCK = threading.Lock()
_ENABLED = os.getenv("AI_USAGE_LEDGER_ENABLED", "1").lower() in {"1", "true", "yes", "on"}


def _safe_int(value):
    try: return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError): return None


def _connect():
    c=sqlite3.connect(str(DB_PATH), timeout=15)
    c.row_factory=sqlite3.Row
    return c


def init_ai_usage_tables():
    if not _ENABLED: return
    with _LOCK, _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS ai_usage_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            feature TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            usage_reported INTEGER NOT NULL DEFAULT 0,
            prompt_chars INTEGER, estimated_prompt_tokens INTEGER, compacted_chars_saved INTEGER NOT NULL DEFAULT 0
        )""")
        existing={row[1] for row in c.execute("PRAGMA table_info(ai_usage_events)")}
        for name, declaration in (("prompt_chars", "INTEGER"), ("estimated_prompt_tokens", "INTEGER"), ("compacted_chars_saved", "INTEGER NOT NULL DEFAULT 0")):
            if name not in existing:
                c.execute(f"ALTER TABLE ai_usage_events ADD COLUMN {name} {declaration}")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage_events(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_feature_created ON ai_usage_events(feature,created_at)")


def record_ai_usage(*, feature="unspecified", provider="openai-compatible", model="unknown", usage=None, latency_ms=0, status="success", prompt_chars=None, estimated_prompt_tokens=None, compacted_chars_saved=0):
    if not _ENABLED: return False
    try:
        init_ai_usage_tables()
        usage=usage if isinstance(usage,dict) else {}
        def integer(value):
            try:
                n=int(value)
                return max(0,n)
            except (TypeError,ValueError): return None
        prompt=integer(usage.get("prompt_tokens"))
        completion=integer(usage.get("completion_tokens"))
        total=integer(usage.get("total_tokens"))
        if total is None and prompt is not None and completion is not None:
            total=prompt+completion
        with _LOCK, _connect() as c:
            c.execute("""INSERT INTO ai_usage_events
                (created_at,feature,provider,model,prompt_tokens,completion_tokens,total_tokens,latency_ms,status,usage_reported,prompt_chars,estimated_prompt_tokens,compacted_chars_saved)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(),str(feature or "unspecified")[:60],str(provider or "unknown")[:40],str(model or "unknown")[:100],prompt,completion,total,max(0,int(latency_ms or 0)),str(status)[:20],int(any(x is not None for x in (prompt,completion,total))),_safe_int(prompt_chars),_safe_int(estimated_prompt_tokens),max(0,_safe_int(compacted_chars_saved) or 0)))
        return True
    except Exception:
        # Accounting must never break legal work.
        return False


def usage_report(days=30):
    init_ai_usage_tables()
    days=max(1,min(365,int(days)))
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    with _connect() as c:
        summary=dict(c.execute("""SELECT COUNT(*) calls,
            SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) successful_calls,
            SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) failed_calls,
            SUM(prompt_tokens) prompt_tokens,SUM(completion_tokens) completion_tokens,
            SUM(total_tokens) total_tokens,
            SUM(usage_reported) usage_reported_calls,
            ROUND(AVG(latency_ms)) avg_latency_ms
            FROM ai_usage_events WHERE created_at>=?""",(cutoff,)).fetchone())
        rows=c.execute("""SELECT feature,COUNT(*) calls,
            SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) successful_calls,
            SUM(prompt_tokens) prompt_tokens,SUM(completion_tokens) completion_tokens,
            SUM(total_tokens) total_tokens,SUM(usage_reported) usage_reported_calls,
            ROUND(AVG(latency_ms)) avg_latency_ms
            FROM ai_usage_events WHERE created_at>=? GROUP BY feature ORDER BY COALESCE(SUM(total_tokens),0) DESC, calls DESC""",(cutoff,)).fetchall()
        models=c.execute("""SELECT provider,model,COUNT(*) calls,SUM(total_tokens) total_tokens
            FROM ai_usage_events WHERE created_at>=? GROUP BY provider,model ORDER BY calls DESC""",(cutoff,)).fetchall()
    input_rate=os.getenv("AI_INPUT_PRICE_PER_1M", "").strip()
    output_rate=os.getenv("AI_OUTPUT_PRICE_PER_1M", "").strip()
    currency=os.getenv("AI_PRICE_CURRENCY", "provider_units").strip() or "provider_units"
    try: input_rate_value=float(input_rate) if input_rate else None
    except ValueError: input_rate_value=None
    try: output_rate_value=float(output_rate) if output_rate else None
    except ValueError: output_rate_value=None
    def estimate(row):
        if input_rate_value is None or output_rate_value is None: return None
        pt=row.get("prompt_tokens") or 0; ct=row.get("completion_tokens") or 0
        return round((pt*input_rate_value+ct*output_rate_value)/1_000_000,8)
    with _connect() as c:
        optimization = dict(c.execute("SELECT SUM(prompt_chars) prompt_chars, SUM(estimated_prompt_tokens) estimated_prompt_tokens, SUM(compacted_chars_saved) compacted_chars_saved FROM ai_usage_events WHERE created_at>=?", (cutoff,)).fetchone())
    summary.update(optimization)
    summary["estimated_cost"] = estimate(summary)
    feature_rows=[]
    for item in rows:
        row=dict(item); row["estimated_cost"]=estimate(row); feature_rows.append(row)
    result = {"days":days,"summary":summary,"by_feature":feature_rows,"by_model":[dict(x) for x in models],"pricing":{"configured":input_rate_value is not None and output_rate_value is not None,"currency_label":currency,"input_per_million":input_rate_value,"output_per_million":output_rate_value},"privacy":"prompt text, completion text, user IDs, case IDs and file names are not stored"}
    from .ai_optimizer import build_optimization_hints
    result["optimization_hints"] = build_optimization_hints(result)
    result["token_estimate_note"] = "estimated_prompt_tokens is a rough planning estimate; provider-reported usage is authoritative."
    return result
