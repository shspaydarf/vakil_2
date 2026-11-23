import sqlite3
from pathlib import Path


def test_ai_usage_ledger_records_only_usage_metadata(tmp_path, monkeypatch):
    from legal_bot import ai_usage
    db=tmp_path/"usage.db"
    monkeypatch.setattr(ai_usage,"DB_PATH",db)
    assert ai_usage.record_ai_usage(feature="legal_question",model="test-model",usage={"prompt_tokens":120,"completion_tokens":30,"total_tokens":150},latency_ms=321,status="success")
    report=ai_usage.usage_report(30)
    assert report["summary"]["calls"] == 1
    assert report["summary"]["total_tokens"] == 150
    assert report["by_feature"][0]["feature"] == "legal_question"
    assert "prompt" in report["privacy"]
    with sqlite3.connect(db) as conn:
        cols={x[1] for x in conn.execute("PRAGMA table_info(ai_usage_events)")}
    assert not ({"prompt","completion","user_id","case_id","file_name"} & cols)


def test_ai_usage_ledger_handles_missing_provider_usage(tmp_path, monkeypatch):
    from legal_bot import ai_usage
    monkeypatch.setattr(ai_usage,"DB_PATH",tmp_path/"usage.db")
    ai_usage.record_ai_usage(feature="contract_review",usage=None,status="success")
    report=ai_usage.usage_report(7)
    assert report["summary"]["calls"] == 1
    assert report["summary"]["usage_reported_calls"] == 0
    assert report["summary"]["total_tokens"] is None


def test_ai_usage_ledger_estimates_cost_only_when_rates_configured(tmp_path, monkeypatch):
    from legal_bot import ai_usage
    monkeypatch.setattr(ai_usage,"DB_PATH",tmp_path/"usage.db")
    monkeypatch.setenv("AI_INPUT_PRICE_PER_1M","1.0")
    monkeypatch.setenv("AI_OUTPUT_PRICE_PER_1M","2.0")
    monkeypatch.setenv("AI_PRICE_CURRENCY","USD")
    ai_usage.record_ai_usage(feature="legal_question",usage={"prompt_tokens":1000000,"completion_tokens":500000})
    report=ai_usage.usage_report(30)
    assert report["summary"]["estimated_cost"] == 2.0
    assert report["pricing"]["currency_label"] == "USD"


def test_ai_usage_admin_endpoint_is_present_and_token_guarded():
    import inspect
    from legal_bot.api import APIHandler
    source=inspect.getsource(APIHandler.do_GET)
    assert "/admin/ai-usage" in source
    assert "X-AI-Usage-Admin-Token" in source
    assert "compare_digest" in source


def test_shared_ai_call_records_provider_usage(tmp_path, monkeypatch):
    from legal_bot import ai, ai_usage
    monkeypatch.setattr(ai_usage, "DB_PATH", tmp_path / "usage.db")
    monkeypatch.setattr(ai, "AI_ENABLED", True)
    monkeypatch.setattr(ai, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(ai, "AI_EXTERNAL_DATA_CONSENT", True)

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"usage": {"prompt_tokens": 22, "completion_tokens": 8, "total_tokens": 30},
                    "choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: Response())
    assert ai._call_feature([{"role": "user", "content": "sensitive legal text"}], feature="unit_test_feature") == "ok"
    report=ai_usage.usage_report(30)
    assert report["summary"]["total_tokens"] == 30
    assert report["by_feature"][0]["feature"] == "unit_test_feature"


def test_shared_ai_call_records_failure_without_prompt_content(tmp_path, monkeypatch):
    from legal_bot import ai, ai_usage
    monkeypatch.setattr(ai_usage, "DB_PATH", tmp_path / "usage.db")
    monkeypatch.setattr(ai, "AI_ENABLED", True)
    monkeypatch.setattr(ai, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(ai, "AI_EXTERNAL_DATA_CONSENT", True)
    def fail(*a, **k): raise RuntimeError("provider unavailable")
    monkeypatch.setattr(ai.requests, "post", fail)
    try:
        ai._call_feature([{"role": "user", "content": "private case content"}], feature="unit_test_failure")
    except RuntimeError:
        pass
    else:
        raise AssertionError("provider failure should propagate")
    report=ai_usage.usage_report(30)
    assert report["summary"]["failed_calls"] == 1
    assert report["summary"]["total_tokens"] is None


def test_ai_prompt_optimizer_only_removes_formatting_noise():
    from legal_bot.ai_optimizer import compact_messages, estimate_tokens_from_chars
    messages=[{"role":"user","content":"متن حقوقی ۱۲۳  \n\n\n\n[صفحه ۲]\nماده ۱۰"}]
    compacted, stats=compact_messages(messages)
    assert compacted[0]["content"] == "متن حقوقی ۱۲۳\n\n[صفحه ۲]\nماده ۱۰"
    assert stats["saved_chars"] > 0
    assert "۱۲۳" in compacted[0]["content"] and "[صفحه ۲]" in compacted[0]["content"]
    assert estimate_tokens_from_chars(10) == 5


def test_usage_ledger_tracks_prompt_size_without_storing_prompt(tmp_path, monkeypatch):
    from legal_bot import ai_usage
    monkeypatch.setattr(ai_usage, "DB_PATH", tmp_path / "usage_opt.db")
    ai_usage.record_ai_usage(feature="case_summary", usage={"prompt_tokens": 50, "completion_tokens": 20},
                             prompt_chars=100, estimated_prompt_tokens=50, compacted_chars_saved=12)
    report=ai_usage.usage_report(30)
    assert report["summary"]["prompt_chars"] == 100
    assert report["summary"]["estimated_prompt_tokens"] == 50
    assert report["summary"]["compacted_chars_saved"] == 12
    with sqlite3.connect(tmp_path / "usage_opt.db") as conn:
        cols={x[1] for x in conn.execute("PRAGMA table_info(ai_usage_events)")}
        assert "prompt_chars" in cols and "compacted_chars_saved" in cols
        assert not ({"prompt", "completion", "case_id", "user_id"} & cols)


def test_shared_ai_call_sends_compacted_prompt_and_tracks_savings(tmp_path, monkeypatch):
    from legal_bot import ai, ai_usage
    monkeypatch.setattr(ai_usage, "DB_PATH", tmp_path / "usage_compact.db")
    monkeypatch.setattr(ai, "AI_ENABLED", True)
    monkeypatch.setattr(ai, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(ai, "AI_EXTERNAL_DATA_CONSENT", True)
    captured = {}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"usage":{"prompt_tokens":12,"completion_tokens":3},"choices":[{"message":{"content":"ok"}}]}
    def fake_post(*args, **kwargs):
        captured.update(kwargs["json"]); return Response()
    monkeypatch.setattr(ai.requests, "post", fake_post)
    ai._call_feature([{"role":"user","content":"متن\n\n\n\nماده ۱۰  "}], feature="compact_test")
    assert captured["messages"][0]["content"] == "متن\n\nماده ۱۰"
    report=ai_usage.usage_report(30)
    assert report["summary"]["compacted_chars_saved"] > 0
